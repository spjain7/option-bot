"""Stock-futures data quality (STOCK-DQ-001, 28-Oct-2026): corporate actions, OI validation, shadow log.

Data fixes only – the live Stock OI BUY rule (thresholds, entry, stop, trail, exits) is unchanged.

1. Corporate actions (Angel's continuous futures history is NOT adjusted for splits / bonus / demergers):
   * verified events live in alerts/corporate_actions.json (ratio + ex-date + source).
   * split / bonus: applied only when the data shows the matching gap at the ex-date (|observed/factor − 1| ≤ GAP_TOL);
     if the data already looks adjusted (observed ≈ 1) nothing is applied; anything else = mismatch -> HOLD.
   * demerger: no official futures price factor exists -> history before the ex-date is dropped (signals stay suppressed
     until enough post-event history exists).
   * a large gap in the data with no verified event -> HOLD (signals suppressed, reason logged) until it is verified.
2. OI validation for the signal day (no rejection on size alone – a genuine big OI change passes):
   missing · non-finite · negative · zero baseline · corporate-action day · corrupt baseline (the previous day's reading
   jumped ×3 or more and today's reading is back within 10 % of the day before it – an isolated bad tick, demonstrated by
   its reversal). A disagreement with the live quote OI and an extreme unconfirmed change are logged as FLAGS only.
3. Shadow log: every live OI-breakout BUY is recorded with its OI change, the "+2–4 %" shadow label, entry / activation /
   exit prices and times, estimated costs and missing-data flags. The label never changes a live call.
"""
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

CA_FILE = Path(__file__).resolve().parent / "corporate_actions.json"
GAP_LO, GAP_HI = 0.72, 1.35          # gap size that needs an explanation (detection only, never a rejection by itself)
GAP_TOL = 0.08                       # observed gap vs verified factor (normal market move on the ex-date is allowed)
SPIKE_X = 3.0                        # isolated OI spike size that, WITH a reversal, marks the baseline reading as corrupt
REVERT_TOL = 0.10
QUOTE_TOL = 0.05
SHADOW_BAND = (0.02, 0.04)           # STOCK-OI-BUY-001 candidate E1, shadow label only
SHADOW_MAX = 1000


# ─────────────── corporate actions ───────────────
def load_registry(path=CA_FILE):
    try:
        ev = json.loads(Path(path).read_text())["events"]
    except Exception as e:                                   # registry unreadable -> no adjustment, gaps will HOLD
        print("corporate-action registry not readable:", e)
        return {}
    out = {}
    for e in ev:
        out.setdefault(e["symbol"], []).append(dict(e, ex=pd.Timestamp(e["ex_date"])))
    return out


REGISTRY = load_registry()


def detect_gaps(d):
    """Daily bars -> [(day, open / previous close)] for gaps outside GAP_LO..GAP_HI."""
    if d is None or len(d) < 2:
        return []
    r = (d["open"].astype(float) / d["close"].astype(float).shift(1)).values
    return [(pd.Timestamp(d["time"].iat[i]).normalize(), float(r[i])) for i in range(1, len(d))
            if np.isfinite(r[i]) and not (GAP_LO <= r[i] <= GAP_HI)]


def _scale(df, before, f):
    df = df.copy()
    m = df["time"].dt.normalize() < before
    for c in ("open", "high", "low", "close"):
        if c in df:
            df[c] = df[c].astype(float); df.loc[m, c] = df.loc[m, c] * f
    if "volume" in df:
        df["volume"] = df["volume"].astype(float); df.loc[m, "volume"] = df.loc[m, "volume"] / f
    if "oi" in df:
        df["oi"] = df["oi"].astype(float); df.loc[m, "oi"] = df.loc[m, "oi"] / f
    return df


def reconcile(name, d, h=None, registry=None):
    """-> (daily, hourly, info). info: applied [(ex, factor)], truncated ex or None, holds [reason], ca_days {day}."""
    reg = REGISTRY if registry is None else registry
    info = dict(applied=[], truncated=None, holds=[], ca_days=set(), skipped=[])
    if d is None or d.empty:
        return d, h, info
    first, last = pd.Timestamp(d["time"].iat[0]).normalize(), pd.Timestamp(d["time"].iat[-1]).normalize()
    gaps = dict(detect_gaps(d))
    explained = set()
    for e in sorted(reg.get(name, []), key=lambda x: x["ex"]):
        ex = e["ex"]
        if not (first < ex <= last):
            continue
        days = d["time"].dt.normalize()
        idx = np.flatnonzero(days.values == np.datetime64(ex))
        if not len(idx):
            info["holds"].append(f"{e['type']} {ex.date()}: ex-date not in the data"); continue
        i = int(idx[0])
        obs = float(d["open"].iat[i]) / float(d["close"].iat[i - 1])
        explained.add(ex)
        if e["type"] == "market":
            continue
        info["ca_days"].add(ex)
        if e.get("price_factor") is None:                    # demerger: no official factor -> drop pre-event history
            d = d[days >= ex].reset_index(drop=True)
            h = h[h["time"].dt.normalize() >= ex].reset_index(drop=True) if h is not None else None
            info["truncated"] = ex
            continue
        f = float(e["price_factor"])
        if abs(obs / f - 1) <= GAP_TOL:
            d = _scale(d, ex, f)
            h = _scale(h, ex, f) if h is not None else None
            info["applied"].append((ex, f))
        elif abs(obs - 1) <= GAP_TOL:
            info["skipped"].append(f"{ex.date()}: data already adjusted (gap ×{obs:.3f})")
        else:
            info["holds"].append(f"{e['type']} {ex.date()}: data gap ×{obs:.3f} does not match the verified factor ×{f}")
    tr = info["truncated"]
    for day, r in gaps.items():
        if day in explained or (tr is not None and day <= tr):
            continue
        info["holds"].append(f"unexplained price gap ×{r:.3f} on {day.date()} – verify a corporate action")
    # continuity check after adjustment: no remaining unexplained jump at an applied ex-date
    for ex, f in info["applied"]:
        days = d["time"].dt.normalize()
        i = int(np.flatnonzero(days.values == np.datetime64(ex))[0])
        r = float(d["open"].iat[i]) / float(d["close"].iat[i - 1])
        if not (1 - GAP_TOL <= r <= 1 + GAP_TOL):
            info["holds"].append(f"{ex.date()}: price not continuous after adjustment (×{r:.3f})")
    return d, h, info


# ─────────────── OI validation ───────────────
def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x


def oi_check(today, prev, prev2=None, quote_oi=None, ca_day=False):
    """-> (doi or None, reason or None, flags list). reason set = OI change must not confirm a call."""
    flags = []
    t, p, p2 = _num(today), _num(prev), _num(prev2)
    for lab, v in (("today", t), ("previous day", p)):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None, f"OI missing ({lab})", flags
        if not math.isfinite(v):
            return None, f"OI not finite ({lab})", flags
        if v < 0:
            return None, f"OI negative ({lab})", flags
    if p == 0:
        return None, "OI zero baseline (previous day 0)", flags
    if t == 0:
        return None, "OI zero today", flags
    if ca_day:
        return None, "corporate-action day (OI units change)", flags
    if p2 is not None and math.isfinite(p2) and p2 > 0:
        up = p / p2
        if (up >= SPIKE_X or up <= 1 / SPIKE_X) and abs(t / p2 - 1) <= REVERT_TOL:
            return None, f"corrupt OI baseline: previous day ×{up:.2f} then back to the earlier level", flags
    doi = t / p - 1
    q = _num(quote_oi)
    if q is not None and math.isfinite(q) and q > 0 and abs(t / q - 1) > QUOTE_TOL:
        flags.append(f"daily OI differs from live quote OI by {(t / q - 1) * 100:+.1f}%")
    if q is None or not (math.isfinite(q) and q > 0):
        flags.append("no live quote OI to cross-check")
    if doi >= 1.0 or doi <= -0.5:                          # flag only – a genuine big change is NOT rejected
        flags.append(f"extreme OI change {doi * 100:+.0f}% (not confirmed by a reversal – kept)")
    return doi, None, flags


def validate_daily_oi(d, quote_oi=None, ca_days=()):
    """Adds columns doi (validated change of the LAST day only, NaN when invalid), oi_reason, oi_flags."""
    d = d.copy()
    d["doi"] = np.nan
    d["oi_reason"] = None
    d["oi_flags"] = None
    if "oi" not in d or len(d) < 2:
        d.loc[d.index[-1], "oi_reason"] = "OI missing"
        return d
    oi = d["oi"].values
    i = len(d) - 1
    day = pd.Timestamp(d["time"].iat[i]).normalize()
    doi, why, flags = oi_check(oi[i], oi[i - 1], oi[i - 2] if i >= 2 else None, quote_oi, day in set(ca_days))
    d.loc[d.index[i], "doi"] = doi if doi is not None else np.nan
    d.loc[d.index[i], "oi_reason"] = why
    d.at[d.index[i], "oi_flags"] = "; ".join(flags) if flags else ""
    return d


# ─────────────── shadow log (OI +2–4 % label, never used for live calls) ───────────────
def cost_per_unit(price, lot):
    """Round-trip cost per unit incl. slippage – same model as the research (research/search/stock_check.cost_frac)."""
    pct = 0.0002 + 2 * 0.0000173 + 0.00002 + 2 * 0.0003 + 0.18 * 2 * 0.0000173
    return pct * float(price) + 40 * 1.18 / float(lot or 1)


def shadow_add(st, *, key, name, sig, plan, lot, now, oi_flags=""):
    doi = sig.get("doi")
    lo, hi = SHADOW_BAND
    rec = dict(key=key, name=name, side=sig["side"], logged=str(now), signal_candle=sig["candle"],
               signal_close=sig["close"], doi=doi, ext=round((sig["close"] - sig["hh"]) / sig["atr"], 3) if sig.get("atr") else None,
               band_2_4=bool(doi is not None and lo <= doi <= hi), entry_plan=plan["entry"], stop=plan["sl"],
               risk=plan["risk_unit"], lot=lot, cost_est=round(cost_per_unit(plan["entry"], lot), 4),
               status="pending", flags=[f for f in (oi_flags or "").split("; ") if f])
    st.setdefault("shadow", []).append(rec)
    st["shadow"] = st["shadow"][-SHADOW_MAX:]
    return rec


def shadow_event(st, key, now, **kw):
    for r in st.get("shadow", []):
        if r["key"] == key:
            r.update(kw)
            if kw.get("status") == "closed" and r.get("entry_fill") is not None and kw.get("exit_price") is not None:
                s = 1 if r["side"] == "BUY" else -1
                gross = s * (float(kw["exit_price"]) - float(r["entry_fill"]))
                r["r_gross"] = round(gross / r["risk"], 3) if r.get("risk") else None
                r["r_net"] = round((gross - r["cost_est"]) / r["risk"], 3) if r.get("risk") else None
            r.setdefault("events", []).append(dict(time=str(now), **{k: v for k, v in kw.items() if k != "events"}))
            return r
    return None


def shadow_summary(st):
    """Baseline (all) vs the +2–4 % label on IDENTICAL signals: closed trades only, net R after estimated costs."""
    rows = [r for r in st.get("shadow", []) if r.get("status") == "closed" and r.get("r_net") is not None]
    out = {}
    for lab, g in (("baseline", rows), ("OI +2-4% label", [r for r in rows if r["band_2_4"]])):
        x = np.array([r["r_net"] for r in g], float)
        out[lab] = dict(n=len(x), exp_net=round(float(x.mean()), 3) if len(x) else None,
                        win=round(float((x > 0).mean() * 100), 1) if len(x) else None)
    out["open_or_pending"] = sum(1 for r in st.get("shadow", []) if r.get("status") in ("pending", "active"))
    out["cancelled"] = sum(1 for r in st.get("shadow", []) if r.get("status") == "cancelled")
    return out

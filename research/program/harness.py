"""STRATEGY-PROGRAM-001 (28-Oct-2026) – shared research harness for the index / MCX futures breakout rules.
Research only: no live code is imported for decisions, nothing is sent, no orders.

Datasets
  angel   : Angel front-month futures, 1-hour bars 2022→2026 (9 instruments) → 3h (S1), daily (S2), monthly-breakout (S3)
  nseidx  : NSE F&O bhavcopy index futures, daily 2011→2026 (NIFTY, BANKNIFTY) → S2, S3   (never used in earlier research)
  proxy   : Yahoo continuous international futures, daily 2005→2026 (GOLD, SILVER, CRUDEOIL, NATURALGAS, COPPER, ALUMINIUM)
            → S2, S3 price/volume behaviour only (not MCX itself; roll jumps not adjusted – limitation)

Execution (live-faithful, alerts/tradeplan.py):
  signal on a completed bar · entry = next bar open · cancelled (missed) if that open is more than 0.5 ATR beyond OR against
  the signal close (live chase / against rule) · stop k·ATR from the entry, target R·risk · stop-width cap per timeframe ·
  stop checked BEFORE target inside a bar (both crossed = loss) · gap through the stop fills at the open · exit at the
  last close before a contract switch · time exit after max bars · costs incl. slippage at 1× and 2×.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402
from research import instruments as INS  # noqa: E402
from research.search import strategy_search as SS  # noqa: E402
from research.search.sr_levels import levels as SRLV  # noqa: E402
from alerts import stats as ST  # noqa: E402
from alerts.stocks import nfo_expiry  # noqa: E402

LIVE = {"S1": dict(k=2.0, r=2.0, maxh=40, cap=2.5), "S2": dict(k=1.5, r=3.0, maxh=40, cap=4.0),
        "S3": dict(k=1.5, r=2.0, maxh=20, cap=4.0)}
CHASE = 0.5


# ─────────────── data ───────────────
def angel(name, exch):
    h = SS.load(exch, name, "ONE_HOUR")
    if h is None or h.empty:
        return {}
    sw = SS.switch_days(name, exch, h)
    out = {}
    for tf, df in (("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
        df = df.reset_index(drop=True)
        df["switch"] = [pd.Timestamp(x) in sw for x in df["time"].dt.normalize()]
        out[tf] = df
    return out


def nseidx(name):
    """Front-month continuous daily futures from the NSE bhavcopy. switch=True on the first session of a new contract."""
    fs = sorted((ROOT / "research/data/nse_fut/days").glob("*.csv"))
    rows = []
    for f in fs:
        d = pd.read_csv(f)
        d = d[d["symbol"] == name]
        if d.empty:
            continue
        d = d[pd.to_datetime(d["expiry"]) >= pd.to_datetime(d["date"])].sort_values("expiry")
        rows.append(d.iloc[0])
    df = pd.DataFrame(rows)
    df = df[(df["open"] > 0) & (df["close"] > 0)]
    df = pd.DataFrame(dict(time=pd.to_datetime(df["date"]), open=df["open"].astype(float), high=df["high"].astype(float),
                           low=df["low"].astype(float), close=df["close"].astype(float), volume=df["contracts"].astype(float),
                           oi=df["oi"].astype(float), expiry=df["expiry"].values)).reset_index(drop=True)
    df["switch"] = df["expiry"].ne(df["expiry"].shift(1)) & (df.index > 0)
    return df


def proxy(name):
    f = ROOT / "research/data/proxy" / f"{name}_1d.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, parse_dates=["time"])
    df = df[(df["open"] > 0) & (df["close"] > 0) & (df["high"] >= df["low"])].reset_index(drop=True)
    df["switch"] = False
    return df


def cost_series(name, df, dataset):
    """Round-trip cost incl. slippage in price units of this series."""
    if dataset == "proxy":                                  # charge the MCX cost FRACTION (proxy prices are USD)
        ang = angel(name, "MCX").get("1d")
        ref = float(ang["close"].median()) if ang is not None and len(ang) else None
        frac = INS.cost_points(name, ref, 1.0) / ref if ref else 0.0005
        return df["close"].values * frac
    return np.array([INS.cost_points(name, p, 1.0) for p in df["close"].values])


# ─────────────── features (known at the signal close) ───────────────
def features(df):
    f = df.copy()
    c, h, l, v = f["close"], f["high"], f["low"], f["volume"].astype(float)
    f["atr"] = I.atr(f, 14)
    f["atr50"] = I.atr(f, 50)
    f["ema200"] = I.ema(c, 200)
    f["adx"] = I.adx(f)
    f["rsi"] = I.rsi(c, 14)
    f["roc20"] = c / c.shift(20) - 1
    f["hh"] = h.shift(1).rolling(20).max()
    f["ll"] = l.shift(1).rolling(20).min()
    f["va"] = v.rolling(20).mean().shift(1)
    f["volx"] = v / f["va"]
    f["atrp"] = f["atr"] / c
    f["atrp_med"] = f["atrp"].rolling(250, min_periods=60).median()
    rng = (h - l).replace(0, np.nan)
    f["clv"] = (c - l) / rng
    f["body"] = (c - f["open"]).abs() / rng
    f["comp"] = (h.rolling(20).max() - l.rolling(20).min()) / f["atr"]
    f["comp_med"] = f["comp"].rolling(100, min_periods=40).median()
    f["hi120"] = h.shift(21).rolling(100).max()             # older resistance beyond the 20-bar box
    f["lo120"] = l.shift(21).rolling(100).min()
    return f


def bo_signal(f):
    up = (f["close"] > f["hh"]) & (f["volx"] > 1.5) & (f["close"] > f["ema200"])
    dn = (f["close"] < f["ll"]) & (f["volx"] > 1.5) & (f["close"] < f["ema200"])
    return np.where(up, 1, np.where(dn, -1, 0))


def monthly_signal(f):
    d = SRLV(f[["time", "open", "high", "low", "close", "volume"]].copy())
    c, pc = d["close"].values, d["close"].shift(1).values
    with np.errstate(invalid="ignore"):
        return np.where((c > d.pmh) & (pc <= d.pmh) & (d.wtr > 0) & (d.mtr > 0), 1,
                        np.where((c < d.pml) & (pc >= d.pml) & (d.wtr < 0) & (d.mtr < 0), -1, 0))


# ─────────────── candidate filters (pre-declared; each tested alone, side-aware) ───────────────
def F(f, s):
    """dict name -> boolean array for side s (+1 BUY / −1 SELL)."""
    ext = s * (f["close"] - np.where(s > 0, f["hh"], f["ll"])) / f["atr"]
    room = np.where(s > 0, f["hi120"] - f["close"], f["close"] - f["lo120"]) / f["atr"]
    return {
        "A1 trend ADX≥25": (f["adx"] >= 25).values,
        "A2 high volatility": (f["atrp"] > f["atrp_med"]).values,
        "A3 low volatility": (f["atrp"] <= f["atrp_med"]).values,
        "A4 vol expanding ATR14>ATR50": (f["atr"] > f["atr50"]).values,
        "A5 not stretched ≤3 ATR from EMA200": ((s * (f["close"] - f["ema200"]) / f["atr"]) <= 3).values,
        "A6 momentum ROC20 aligned": ((s * f["roc20"]) > 0).values,
        "B1 extension ≤1 ATR": (ext <= 1.0).values,
        "B2 close near extreme (CLV)": ((f["clv"] >= 0.7) if s > 0 else (f["clv"] <= 0.3)).values,
        "B3 strong body ≥50%": (f["body"] >= 0.5).values,
        "B4 prior compression": (f["comp"] <= f["comp_med"]).values,
        "B5 room ≥3 ATR to older level": (~np.isfinite(room) | (room >= 3) | (room < 0)),
        "C1 volume ≥2×": (f["volx"] >= 2.0).values,
        "C2 RSI not exhausted": ((f["rsi"] < 75) if s > 0 else (f["rsi"] > 25)).values,
    }


EXITS = {  # pre-declared exit set (stop ATR multiple, target R; None = live baseline for that strategy)
    "X0 live baseline": None,
    "X1 stop 2 ATR · target 1R": (2.0, 1.0), "X2 stop 2 ATR · target 0.75R": (2.0, 0.75), "X3 stop 2 ATR · target 0.5R": (2.0, 0.5),
    "X4 stop 3 ATR · target 0.5R": (3.0, 0.5), "X5 stop 1.5 ATR · target 2R": (1.5, 2.0), "X6 stop 2.5 ATR · target 3R": (2.5, 3.0),
    "X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R": ("swing", 2.0),
}


# ─────────────── simulation ───────────────
def simulate(f, sig, side, k, tgt_r, maxh, cap, cost, start=210, swing=False):
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    sw = f["switch"].values
    lo10, hi10 = f["low"].rolling(10).min().values, f["high"].rolling(10).max().values
    out, busy = [], -1
    for i in np.flatnonzero(sig == side):
        if i < start or i <= busy or i >= len(c) - 1 or sw[i] or sw[i + 1] or not a[i] > 0:
            continue
        rec = dict(i=i, time=f["time"].iat[i], side="BUY" if side > 0 else "SELL")
        mv = side * (o[i + 1] - c[i]) / a[i]
        if mv > CHASE or mv < -CHASE:
            out.append(dict(rec, status="invalidated", why="next open beyond the 0.5-ATR entry zone")); continue
        e0 = o[i + 1]
        if swing:
            st = (lo10[i] - 0.5 * a[i]) if side > 0 else (hi10[i] + 0.5 * a[i])
            R = side * (e0 - st)
            if not R > 0:
                out.append(dict(rec, status="invalidated", why="swing stop on the wrong side")); continue
        else:
            R = k * a[i]; st = e0 - side * R
        if cap and R / e0 * 100 > cap:
            out.append(dict(rec, status="invalidated", why=f"stop wider than {cap}%")); continue
        tp = e0 + side * tgt_r * R
        px = why = None; j = i + 1
        while j < len(c):
            if j > i + 1 and sw[j]:
                px, why, j = c[j - 1], "roll", j - 1; break
            if j > i + 1 and ((o[j] <= st) if side > 0 else (o[j] >= st)):
                px, why = o[j], "stop-gap"; break
            if j > i + 1 and ((o[j] >= tp) if side > 0 else (o[j] <= tp)):  # gap through the target fills at the open (VERIFY-EXITS, 29-Oct)
                px, why = o[j], "target-gap"; break
            if (l[j] <= st) if side > 0 else (h[j] >= st):
                px, why = st, "stop"; break
            if (h[j] >= tp) if side > 0 else (l[j] <= tp):
                px, why = tp, "target"; break
            if j - (i + 1) >= maxh:
                px, why = c[j], "time"; break
            j += 1
        if px is None:
            px, why, j = c[-1], "open-at-end", len(c) - 1
        r1 = (side * (px - e0) - cost[i]) / R
        out.append(dict(rec, status="trade", exit=why, bars=j - i, r1=r1, r2=(side * (px - e0) - 2 * cost[i]) / R,
                        cost_r=cost[i] / R))
        busy = j
    return out


# ─────────────── statistics ───────────────
def boot(g, col="r1", n=1500, seed=3):
    if len(g) < 8:
        return (np.nan, np.nan)
    m = pd.to_datetime(g["time"], format="mixed").dt.to_period("M")
    s = g.groupby(m)[col].agg(["sum", "size"]).values
    rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        x = s[rng.integers(0, len(s), len(s))].sum(0)
        out.append(x[0] / max(x[1], 1))
    return tuple(np.round(np.percentile(out, [2.5, 97.5]), 3))


def metrics(g):
    t = g[g["status"] == "trade"] if "status" in g else g
    n_inv = int((g["status"] == "invalidated").sum()) if "status" in g else 0
    if len(t) == 0:
        return dict(n=0, invalid=n_inv)
    r, r2 = t["r1"].values, t["r2"].values
    w, l_ = r[r > 0], r[r <= 0]
    seq = t.sort_values("time")["r1"].values
    eq = np.cumsum(seq); dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    ml = cur = 0
    for x in seq:
        cur = cur + 1 if x <= 0 else 0; ml = max(ml, cur)
    lo, hi = boot(t)
    return dict(n=len(t), invalid=n_inv, win=round(len(w) / len(r) * 100, 1), avg_w=round(w.mean(), 2) if len(w) else 0,
                avg_l=round(l_.mean(), 2) if len(l_) else 0, exp1=round(r.mean(), 3), exp2=round(r2.mean(), 3),
                ci=f"[{lo:+.2f},{hi:+.2f}]" if lo == lo else "n/a", pf=round(w.sum() / -l_.sum(), 2) if l_.sum() < 0 else np.nan,
                dd=round(dd, 1), max_losses=ml, tgt=round((t["exit"] == "target").mean() * 100, 1),
                stop=round(t["exit"].isin(["stop", "stop-gap"]).mean() * 100, 1),
                gap=round((t["exit"] == "stop-gap").mean() * 100, 1),
                warn="n<30" if len(t) < 30 else ("n<100" if len(t) < 100 else ""))

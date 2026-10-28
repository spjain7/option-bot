"""Runs STOCK-OI-BUY-001 (see stock_oi_buy.py for the pre-declared candidates).  python research/search/stock_oi_buy_run.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import stock_search as SR, strategy_search as SS, stock_check as SC  # noqa
from research.search import stock_oi_buy as X  # noqa
from research.search.oos_validate import nifty_regime, boot_ci  # noqa
from alerts.stocks import in_rollover_window, nfo_expiry  # noqa

OUT = ROOT / "research/search/results_stock_oi_buy"
P1, P2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")


def last_sessions(days):
    s = pd.Series(pd.to_datetime(days))
    exp = s.map(lambda d: nfo_expiry(d.year, d.month))
    out = np.zeros(len(s), bool)
    for e in exp.unique():
        cand = s[s <= e]
        if len(cand) and (e - cand.iloc[-1]).days <= 5:
            out[cand.index[-1]] = True
    return out


def load_stock(name, lot, adjust=True):
    f1, fo = SR.DATA / f"{name}_ONE_HOUR.csv", SR.DATA / f"{name}_OI_ONE_DAY.csv"
    if not (f1.exists() and fo.exists()):
        return None
    h = pd.read_csv(f1, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
    h = h.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    d0 = SS.daily_from(h).reset_index(drop=True)
    ev = X.corporate_actions(d0) if adjust else []
    if ev:
        h = X.adjust(h, ev); d0 = X.adjust(d0, ev)
    days = d0["time"].dt.normalize()
    oi, doi, why = X.oi_series(pd.read_csv(fo), days, ev if adjust else [])
    if not adjust:                                         # the earlier (unchecked) OI change, for comparison
        doi = pd.Series(oi).pct_change(fill_method=None).values
    f = X.features(d0, doi)
    roll = pd.Series([in_rollover_window(pd.Timestamp(x)) for x in days])
    hourly = {k: g.reset_index(drop=True) for k, g in h.groupby(h["time"].dt.normalize())}
    cost = lambda p: SC.cost_frac(p, lot)                  # noqa: E731  round trip incl. slippage, in price units
    return dict(f=f, roll=roll, last=last_sessions(days), hourly=hourly, cost=cost, why=why, events=ev,
                first_oi=days[np.isfinite(oi) & (oi > 0)].min())


def run_variant(S, sig, mode="open", side=1, zone=False):
    out, busy = [], -1
    f = S["f"]
    for i in np.flatnonzero(sig):
        if i < 210 or i <= busy or f["time"].iat[i] < S["first_oi"]:
            continue
        if zone and not X.open_zone_ok(f, i, side):
            out.append(dict(time=f["time"].iat[i], missed=True, why="cancelled at open (live ±0.5 ATR zone)")); continue
        t = X.simulate(f, i, S["last"], S["hourly"], S["cost"], mode=mode, side=side)
        if t is None:
            continue
        if t.get("missed"):
            out.append(dict(time=f["time"].iat[i], missed=True, why=t["why"])); continue
        t.update(doi=f["doi"].iat[i], ext=f["ext"].iat[i] if side > 0 else (f["ll"].iat[i] - f["close"].iat[i]) / f["atr"].iat[i])
        out.append(t)
        busy = i + t["held"]
    return out


def metrics(g):
    g = g[~g["missed"]] if "missed" in g else g
    if len(g) == 0:
        return dict(n=0)
    r, r2 = g["r1"].values, g["r2"].values
    w, l = r[r > 0], r[r <= 0]
    eq = np.cumsum(g.sort_values("time")["r1"].values)
    lo, hi = boot_ci(g)
    return dict(n=len(r), warn="n<30" if len(r) < 30 else ("n<100" if len(r) < 100 else ""), win=round(len(w) / len(r) * 100, 1),
                exp1=round(r.mean(), 3), exp2=round(r2.mean(), 3), ci=f"[{lo:+.2f}, {hi:+.2f}]" if lo == lo else "n/a",
                pf=round(w.sum() / -l.sum(), 2) if l.sum() < 0 else np.nan,
                dd=round(float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()), 1),
                cost_R=round(g["cost_r"].mean(), 3))


def diff_ci(cand, base, n=2000, seed=11):
    """95 % month-block bootstrap of mean R(candidate) − mean R(baseline) (same resampled months)."""
    c = cand.assign(m=pd.to_datetime(cand["time"]).dt.to_period("M"))
    b = base.assign(m=pd.to_datetime(base["time"]).dt.to_period("M"))
    months = sorted(set(b["m"]))
    cs = c.groupby("m")["r1"].agg(["sum", "size"]).reindex(months).fillna(0).values
    bs = b.groupby("m")["r1"].agg(["sum", "size"]).reindex(months).fillna(0).values
    rng = np.random.default_rng(seed); ds = []
    for _ in range(n):
        idx = rng.integers(0, len(months), len(months))
        cc, bb = cs[idx].sum(0), bs[idx].sum(0)
        if cc[1] and bb[1]:
            ds.append(cc[0] / cc[1] - bb[0] / bb[1])
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return f"[{lo:+.2f}, {hi:+.2f}]"


def period(t):
    return np.where(t < P1, "a: Nov23–Jun24", np.where(t < P2, "b: Jul24–Jun25", "c: Jul25–Oct26"))


def tab(G, by):
    rows = []
    for k, g in G.groupby(by, sort=True):
        rows.append({**dict(zip(by if isinstance(by, list) else [by], k if isinstance(k, tuple) else [k])), **metrics(g)})
    return pd.DataFrame(rows)


def md(df):
    return df.to_markdown(index=False) if len(df) else "_none_"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mkt = nifty_regime()
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    rows, audit = [], dict(stocks=0, ca_events=[], oi_days=0, oi_invalid={}, base_sig_raw=0, base_sig_valid=0)
    for rr in man.itertuples():
        S = load_stock(rr.name, rr.lot)
        if S is None:
            continue
        audit["stocks"] += 1
        audit["ca_events"] += [(rr.name, str(e.date()), round(fct, 3)) for e, fct in S["events"]]
        f, roll = S["f"], S["roll"]
        after = (f["time"] >= S["first_oi"]).values
        audit["oi_days"] += int(after.sum())
        for k, v in S["why"][after].value_counts().items():
            audit["oi_invalid"][k] = audit["oi_invalid"].get(k, 0) + int(v)
        base = X.base_buy(f, roll)
        variants = {"B1 baseline (corrected data)": base}
        for lab, (lo, hi) in X.OI_BANDS.items():
            if hi is not None:
                variants[lab] = base & X.oi_band(f, lo, hi)
        for mx in X.EXT_MAX:
            variants[f"E2 ext ≤{mx}"] = base & X.ext_cap(f, mx)
        for lab, sig in variants.items():
            rows += [dict(t, var=lab, name=rr.name, side="BUY") for t in run_variant(S, sig, "open")]
        rows += [dict(t, var="B1 + live open-zone check", name=rr.name, side="BUY") for t in run_variant(S, base, "open", zone=True)]
        rows += [dict(t, var="B1 exit before rollover window (OOS model)", name=rr.name, side="BUY")
                 for t in run_variant(dict(S, last=X.last_before_window(roll)), base, "open")]
        rows += [dict(t, var="E3 confirmation entry", name=rr.name, side="BUY") for t in run_variant(S, base, "confirm")]
        rows += [dict(t, var="SELL baseline (reference)", name=rr.name, side="SELL") for t in run_variant(S, X.base_sell(f, roll), "open", -1)]
        # uncorrected data (no corporate-action adjustment, unchecked OI) – shows the effect of the data fixes
        U = load_stock(rr.name, rr.lot, adjust=False)
        rows += [dict(t, var="B0 baseline (uncorrected data)", name=rr.name, side="BUY") for t in run_variant(U, X.base_buy(U["f"], U["roll"]), "open")]
    T = pd.DataFrame(rows)
    T["missed"] = T["missed"].fillna(False).astype(bool)
    T["time"] = pd.to_datetime(T["time"]); T["year"] = T["time"].dt.year; T["period"] = period(T["time"])
    T["market"] = [mkt.get(pd.Timestamp(x).normalize(), "n/a") for x in T["time"]]
    T.to_csv(OUT / "trades.csv.gz", index=False)
    F = T[~T.missed]
    B = F[F["var"] == "B1 baseline (corrected data)"]
    order = ["B0 baseline (uncorrected data)", "B1 baseline (corrected data)", "B1 + live open-zone check",
             "B1 exit before rollover window (OOS model)", "E1 2–3%", "E1 2–4%", "E1 2–5%",
             *[f"E2 ext ≤{m}" for m in X.EXT_MAX], "E3 confirmation entry", "SELL baseline (reference)"]
    L = ["# STOCK-OI-BUY-001 – generated tables (EXPLORATORY: all dates examined before)\n",
         "R = stop distance (2 ATR). exp1/exp2 = mean R per trade after 1× / 2× costs (incl. slippage). ci = 95 % month-block "
         "bootstrap. Δ vs B1 = candidate − baseline mean R, same bootstrap. cost_R = round-trip cost in R. warn: n<30 / n<100.\n",
         "## Data audit\n",
         f"- stocks with price + OI: {audit['stocks']} · sessions with OI: {audit['oi_days']}",
         f"- OI-change validity: {audit['oi_invalid']}",
         f"- corporate actions adjusted ({len(audit['ca_events'])}): " + ", ".join(f"{a} {b} ×{c}" for a, b, c in audit["ca_events"]) + "\n"]
    summ = []
    for v in order:
        g = F[F["var"] == v]
        m = metrics(g)
        miss = int(T[(T["var"] == v) & T.missed].shape[0])
        d = diff_ci(g, B) if v not in ("B1 baseline (corrected data)", "SELL baseline (reference)", "B0 baseline (uncorrected data)") and len(g) else ""
        dm = round(g.r1.mean() - B.r1.mean(), 3) if d else ""
        summ.append(dict(variant=v, removed=(len(B) - len(g)) if v.startswith(("E1", "E2")) else "", missed=miss or "", **m,
                         d_vs_B1=dm, d_ci=d))
    L.append("## Summary – all periods\n" + md(pd.DataFrame(summ)) + "\n")
    for by in ("period", "year", "market"):
        L.append(f"## By {by}\n")
        x = tab(F[F["var"].isin(order)], ["var", by])
        x["var"] = pd.Categorical(x["var"], order); L.append(md(x.sort_values(["var", by])) + "\n")
    L.append("## By stock (positive stocks / stocks with trades; top and bottom contributors)\n")
    for v in order:
        g = F[F["var"] == v].groupby("name")["r1"].agg(["size", "sum", "mean"])
        if len(g):
            L.append(f"- **{v}**: {(g['mean'] > 0).sum()}/{len(g)} stocks positive · best {', '.join(f'{i} {r['sum']:+.1f}R' for i, r in g.nlargest(3, 'sum').iterrows())}"
                     f" · worst {', '.join(f'{i} {r['sum']:+.1f}R' for i, r in g.nsmallest(3, 'sum').iterrows())}")
    # removed trades (E1/E2) – what the filter took out
    L.append("\n## Trades removed by each filter (baseline trades not in the candidate)\n")
    rr_ = []
    for v in [o for o in order if o.startswith(("E1", "E2"))]:
        g = F[F["var"] == v]
        rem = B[~B.set_index(["name", "time"]).index.isin(g.set_index(["name", "time"]).index)]
        rr_.append(dict(variant=v, **{f"removed_{k}": val for k, val in metrics(rem).items() if k in ("n", "win", "exp1", "ci")}))
    L.append(md(pd.DataFrame(rr_)) + "\n")
    # diagnostics for root-cause hypotheses (baseline trades)
    L.append("## Diagnostics on baseline B1 trades\n")
    Bd = B.assign(oi_b=pd.cut(B["doi"], [0.02, 0.03, 0.04, 0.05, 0.08, 10], include_lowest=True).astype(str),
                  ext_b=pd.cut(B["ext"], [0, 0.25, 0.5, 0.75, 1.0, 1.5, 99], include_lowest=True).astype(str),
                  gap_b=pd.cut(B["gap_atr"], [-99, -0.5, 0, 0.25, 0.5, 99]).astype(str),
                  hold_b=pd.cut(B["held"], [0, 2, 5, 10, 99]).astype(str))
    for by, lab in (("oi_b", "OI change bucket"), ("ext_b", "extension (ATR) bucket"), ("gap_b", "next-open gap (ATR)"),
                    ("why", "exit reason"), ("hold_b", "sessions held")):
        L.append(f"### {lab}\n" + md(tab(Bd, by)) + "\n")
    L.append(f"- OI change vs extension correlation (baseline): {B['doi'].corr(B['ext']):+.2f}\n")
    E3 = T[T["var"] == "E3 confirmation entry"]
    L.append(f"## E3 execution\n- signals {len(E3)} · filled {int((~E3.missed).sum())} · missed {int(E3.missed.sum())} "
             f"({E3[E3.missed]['why'].value_counts().to_dict()})\n")
    (OUT / "tables.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()

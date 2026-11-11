"""Cycle 3 · 1 – is the relative-volume filter on the CONTINUATION BUY genuine? Kept as its own research version
CONT-BUY-B1-RVOL2-v1 (base B1 = RSI(14) crosses to >= 75, BUY next open, structure stop, 2R, costs per market; the filter:
the signal bar's volume >= 2x the average of the previous 20 bars). Nothing is tuned here; the thresholds 1.5 / 2.5 / 3
are shown only as a dose-response check.
For every market x timeframe of cycle 2: base vs filtered by period, by calendar year, by regime at the decision bar
(market up = MCX: >= 4 of 7 commodities above their daily EMA50, previous day; NSE: EW market above its EMA200; plus the
instrument's own close vs EMA200), and by instrument (how many instruments improve). Multiple testing: Holm and BH over
the 18 (market x tf x 2 targets) primary tests of filtered-vs-excluded OOS trades, and a permutation test (filter labels
shuffled within each year, 2,000 draws) for the pooled OOS difference.
Forward evidence: none yet – this version is not in a shadow ledger (an intraday shadow engine would be needed for MCX 1h).
python -m research.cycle3.rvol  ->  results/rvol.json, results/rvol_cells.csv"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.rsirev import run as RR  # noqa: E402
from research.cycle2 import common as C, cont_buy as CB  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
RNG = np.random.default_rng(31)
THR = (1.5, 2.0, 2.5, 3.0)


def market_pool(m, tf, cs):
    frames = CB.cash_frames(tf, cs) if m == "cash" else getattr(RR, m)(tf)
    ctxs = CB.mcx_ctx(frames, tf) if m == "mcx" else None
    pool = E.Pool(); reg_mkt, reg_own = [], []
    for i, f in enumerate(frames):
        b = f["b"].reset_index(drop=True)
        ev, risk, _ = C.base_events(b)
        v = b["volume"].astype(float); rv = (v / v.rolling(20).mean().shift(1)).values
        c = b["close"].astype(float)
        live = np.asarray(f["live"], bool); e = ev["B1"] & live
        S = {("B1", "x", "x", 1): e}
        for t in THR:
            S[(f"B1+rvol{t}", "x", "x", 1)] = e & np.nan_to_num(rv >= t)
        pool.add(b, S, risk["structure"], f["grp"], f["costf"], f["expid"], f["name"])
        if m == "mcx":
            reg_mkt.append(ctxs[i]["mcx_breadth"])
        elif m == "index":
            reg_mkt.append(CB.index_ctx(b["time"].values, tf, cs)["mkt_up"])
        else:
            reg_mkt.append(CB.stock_ctx(f["name"], b["time"].values, tf, cs)["mkt_up"])
        reg_own.append((c > c.ewm(span=200, adjust=False).mean()).values)
    pool.freeze(); pool.reg_mkt = np.concatenate(reg_mkt); pool.reg_own = np.concatenate(reg_own)
    return pool


def st(r):
    r = np.asarray(r, float)
    return dict(n=int(len(r)), R=round(float(r.mean()), 3) if len(r) else None)


def main():
    cs = C.cash_context()
    cells, out = [], {}
    pooled_oos = []
    for m, tfs in CB.TFS.items():
        for tf, hold in tfs:
            cuts = RR.MARKETS[m][2].get(tf, RR.MARKETS[m][2].get("*"))
            P = market_pool(m, tf, cs)
            for R in (2.0, 3.0):
                Tb = P.run(("B1", "x", "x", 1), R, hold)
                if len(Tb) < 30:
                    continue
                Tb["year"] = pd.to_datetime(Tb.entry).dt.year
                Tb["mkt_up"] = P.reg_mkt[Tb.i.values - 1]; Tb["own_up"] = P.reg_own[Tb.i.values - 1]
                Tb["period"] = E.periods(Tb.entry.values, cuts)
                res = {}
                for t in THR:
                    kk = (f"B1+rvol{t}", "x", "x", 1)
                    Tf = P.run(kk, R, hold) if kk in P.idx else Tb.iloc[0:0].copy()
                    keyset = set(zip(Tf.name, Tf.entry))
                    Tb[f"in{t}"] = [(n_, e_) in keyset for n_, e_ in zip(Tb.name, Tb.entry)]
                    Tf["period"] = E.periods(Tf.entry.values, cuts)
                    res[t] = {p: st(Tf.netR[Tf.period == p]) for p, _ in cuts}
                    res[t]["all"] = st(Tf.netR)
                # the primary version: 2x. Trades of the base that the filter keeps vs drops (same trade outcomes)
                k = Tb["in2.0"]
                row = dict(market=CB.MKT[m], tf=tf, target_R=R, base_n=len(Tb), kept_share=round(float(k.mean()), 3))
                for p, _ in cuts:
                    a, b_ = Tb.netR[(Tb.period == p) & k], Tb.netR[(Tb.period == p) & ~k]
                    row[f"{p}_kept_R"], row[f"{p}_dropped_R"], row[f"{p}_kept_n"] = (round(float(a.mean()), 3) if len(a) else np.nan,
                                                                                    round(float(b_.mean()), 3) if len(b_) else np.nan, len(a))
                    row[f"{p}_version_R"] = res[2.0][p]["R"]; row[f"{p}_base_R"] = round(float(Tb.netR[Tb.period == p].mean()), 3)
                oos = Tb[Tb.period == "OOS"]
                a, b_ = oos.netR[oos["in2.0"]], oos.netR[~oos["in2.0"]]
                row["oos_t"] = round(float(C.welch(a, b_)), 2) if np.isfinite(C.welch(a, b_)) else np.nan
                yrs = Tb.groupby("year").apply(lambda g: g.netR[g["in2.0"]].mean() - g.netR[~g["in2.0"]].mean() if g["in2.0"].any() and (~g["in2.0"]).any() else np.nan)
                row["years_kept_better"] = f"{int((yrs > 0).sum())}/{int(yrs.notna().sum())}"
                for col in ("mkt_up", "own_up"):
                    for v in (True, False):
                        g = Tb[Tb[col] == v]
                        row[f"{col}={v}_kept_minus_dropped"] = round(float(g.netR[g["in2.0"]].mean() - g.netR[~g["in2.0"]].mean()), 3) if g["in2.0"].any() and (~g["in2.0"]).any() else np.nan
                inst = Tb.groupby("name").apply(lambda g: g.netR[g["in2.0"]].mean() - g.netR[~g["in2.0"]].mean() if g["in2.0"].sum() >= 3 and (~g["in2.0"]).sum() >= 3 else np.nan).dropna()
                row["instruments_kept_better"] = f"{int((inst > 0).sum())}/{len(inst)}"
                row["dose_response_all_R"] = " / ".join(f"{t}x:{res[t]['all']['R']}" for t in THR)
                cells.append(row)
                if R == 2.0:
                    pooled_oos.append(oos.assign(cell=f"{m}|{tf}")[["cell", "year", "netR", "in2.0"]])
            print(m, tf, "done", flush=True)
    L = pd.DataFrame(cells)
    p = E.pvals(L.oos_t.fillna(0).values)
    L["p"] = np.where(L.oos_t.notna(), p, np.nan); L["HOLM5"] = False; L["BH10"] = C.bh(L.p.values)
    ok = L.p.notna()
    L.loc[ok, "HOLM5"] = E.holm(L.loc[ok, "p"].values)
    # pooled OOS permutation (2R): shuffle kept / dropped labels within each cell-year
    Q = pd.concat(pooled_oos, ignore_index=True)
    real = Q.netR[Q["in2.0"]].mean() - Q.netR[~Q["in2.0"]].mean()
    grp = Q.groupby(["cell", "year"]).indices; sims = []
    lab = Q["in2.0"].values.copy(); r = Q.netR.values
    for _ in range(2000):
        x = lab.copy()
        for ix in grp.values():
            x[ix] = RNG.permutation(x[ix])
        sims.append(r[x].mean() - r[~x].mean())
    out["pooled_oos_2R"] = dict(trades=len(Q), kept=int(Q["in2.0"].sum()), kept_minus_dropped_R=round(float(real), 3),
                               permutation_p=round(float((np.array(sims) >= real).mean()), 4))
    out["cells_holm_pass"] = int(L.HOLM5.sum()); out["cells_bh_pass"] = int(L.BH10.sum())
    L.to_csv(OUT / "rvol_cells.csv", index=False)
    json.dump(out, open(OUT / "rvol.json", "w"), indent=1, default=str)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    print(L.drop(columns=[c for c in L if c.endswith("_n")]).to_string(index=False)); print(out)


if __name__ == "__main__":
    main()

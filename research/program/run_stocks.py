"""STRATEGY-PROGRAM-001 · stock futures: S4 OI breakout (BUY and SELL) and S5 bearish engulfing SELL.
Data: Angel stock futures (prices 2022→, OI Nov-2023→), corporate actions adjusted and bad OI rejected
(research/search/stock_oi_buy.py). Baselines use the live exits (S4: stop 2 ATR, 3-ATR trail moved only when it gains
> 0.25 ATR, expiry-day close; S5: stop 1.5 ATR, target 1R, 10 sessions). Candidates: the 13 harness entry filters (one at a
time, live exits) and the high-accuracy exits (stop 2/3 ATR, target 0.5R; expiry-day exit kept).
Split: train < 2024-07-01 ≤ validation < 2025-07-01 ≤ test.   python research/program/run_stocks.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H  # noqa: E402
from research.search import stock_oi_buy as X, stock_oi_buy_run as RN, stock_search as SR  # noqa: E402
from research.search.candle_rev import pats  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
T1, T2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")


def one(rr):
    name, lot = rr
    S = RN.load_stock(name, lot)
    if S is None:
        return []
    f0, roll = S["f"], S["roll"]
    feat = H.features(f0[["time", "open", "high", "low", "close"]].assign(volume=f0["close"] * 0 + 1))
    # harness features need volume – take it from the stock frame (va / volx already in f0)
    for c in ("volx", "va"):
        feat[c] = f0[c].values
    sw = np.zeros(len(f0), bool); sw[1:] = S["last"][:-1]          # first session after an expiry = contract switch
    feat["switch"] = sw
    cost = np.array([S["cost"](p) for p in f0["close"].values])
    rows = []
    sigs = {"S4": {1: X.base_buy(f0, roll), -1: X.base_sell(f0, roll)}}
    cl = f0["close"]; e20 = I.ema(cl, 20); r5 = cl.pct_change(5)
    be = (pats(f0[["time", "open", "high", "low", "close"]].assign(volume=0))["bear_engulf"] & (cl > e20) & (r5 > 0)
          & (f0["volx"] > 1.5) & ~roll).fillna(False).values
    sigs["S5"] = {-1: be}
    for st, by in sigs.items():
        for side, sig in by.items():
            flt = {"none": np.ones(len(f0), bool), **{k: np.asarray(v, bool) for k, v in H.F(feat, side).items()}}
            for fl, m in flt.items():
                s2 = np.asarray(sig, bool) & m
                if st == "S4":                                   # live exits (trail, expiry) – research module
                    for t in RN.run_variant(S, s2, "open", side=side, zone=True):
                        rows.append(dict(t, status="invalidated" if t.get("missed") else "trade", variant=f"live + {fl}",
                                         strat=st, side="BUY" if side > 0 else "SELL", name=name,
                                         exit=t.get("why"), r1=t.get("r1"), r2=t.get("r2")))
                else:
                    rows += [dict(t, variant=f"live + {fl}", strat=st, name=name)
                             for t in H.simulate(feat, np.where(s2, side, 0), side, 1.5, 1.0, 10, 6.0, cost, 30)]
                if fl in ("none", "C2 RSI not exhausted", "B4 prior compression", "A3 low volatility"):
                    for xl, (k, r) in {"HA 2ATR/0.5R": (2.0, 0.5), "HA 3ATR/0.5R": (3.0, 0.5)}.items():
                        rows += [dict(t, variant=f"{xl} + {fl}", strat=st, name=name)
                                 for t in H.simulate(feat, np.where(s2, side, 0), side, k, r, 40 if st == "S4" else 10, 6.0, cost, 210 if st == "S4" else 30)]
    for r in rows:
        r.setdefault("side", "BUY" if r.get("side", 1) == 1 else r.get("side"))
    return rows


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    with Pool(8) as p:
        rows = [r for x in p.map(one, list(zip(man["name"], man["lot"]))) for r in x]
    T = pd.DataFrame(rows)
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = np.where(T["time"] < T1, "1-train", np.where(T["time"] < T2, "2-valid", "3-test"))
    T["year"] = T["time"].dt.year
    T.to_csv(OUT / "stocks_trades.csv.gz", index=False)
    L = ["# STRATEGY-PROGRAM-001 – stock futures (generated)\n"]
    res = []
    for (st, side), G in T.groupby(["strat", "side"]):
        B = G[G["variant"] == "live + none"]
        L.append(f"\n## {st} · {side}\n### Baseline (live rules)\n" + pd.DataFrame(
            [dict(split=sp, **H.metrics(B[B.split == sp])) for sp in ("1-train", "2-valid", "3-test")] + [dict(split="ALL", **H.metrics(B))]).to_markdown(index=False))
        bt = B[B.status == "trade"]
        L.append("\nby year: " + "; ".join(f"{y}: n{len(g)} {g.r1.mean():+.2f}R w{(g.r1 > 0).mean() * 100:.0f}%" for y, g in bt.groupby("year")))
        for v, V in G.groupby("variant"):
            if v == "live + none":
                continue
            r = dict(strat=st, side=side, variant=v)
            for sp in ("1-train", "2-valid", "3-test"):
                m = H.metrics(V[V.split == sp]); b = B[(B.split == sp) & (B.status == "trade")]
                c = V[(V.split == sp) & (V.status == "trade")]
                r.update({f"{sp[2:]}_n": m.get("n", 0), f"{sp[2:]}_win": m.get("win"), f"{sp[2:]}_exp2": m.get("exp2"),
                          f"{sp[2:]}_pf": m.get("pf"), f"{sp[2:]}_d": round(c.r1.mean() - b.r1.mean(), 3) if len(c) and len(b) else np.nan})
            imp = [r["train_n"] >= 20 and (r["train_d"] or -1) > 0 and (r["train_exp2"] or -1) > 0,
                   r["valid_n"] >= 10 and (r["valid_d"] or -1) > 0 and (r["valid_exp2"] or -1) > 0,
                   r["test_n"] >= 10 and (r["test_d"] or -1) > 0 and (r["test_exp2"] or -1) > 0]
            ha = [r[f"{s}_n"] >= (20 if s == "train" else 10) and (r[f"{s}_win"] or 0) >= 75 and (r[f"{s}_exp2"] or -1) > 0
                  and (r[f"{s}_pf"] or 0) >= 1.2 for s in ("train", "valid", "test")]
            r["improves_baseline"] = "PASS all 3" if all(imp) else "train+valid" if imp[0] and imp[1] else "train" if imp[0] else "fail"
            r["high_accuracy_gate"] = "PASS all 3" if all(ha) else "train+valid" if ha[0] and ha[1] else "train" if ha[0] else "fail"
            res.append(r)
    R = pd.DataFrame(res)
    R.to_csv(OUT / "stocks_candidates.csv", index=False)
    L.append("\n## Candidates\n" + R.to_markdown(index=False))
    (OUT / "stocks_tables.md").write_text("\n".join(L))
    pd.set_option("display.width", 250)
    print("\n".join(L[:12]))
    print(R[(R.improves_baseline != "fail") | (R.high_accuracy_gate != "fail")].to_string())


if __name__ == "__main__":
    main()

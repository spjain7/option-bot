"""Trade-level extraction for chosen MCXE configurations + matched RANDOM-entry control (same commodity, timeframe, side,
entry / stop / exit). python research/program/mcx_engine_trades.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_engine as E, mcx_disc as MD  # noqa: E402

CFG = [("SILVER", "15m", "CMP", "FLAG", 1), ("SILVER", "60m", "MS", "BOS", 1), ("SILVER", "60m", "TL", "BRK", 1),
       ("GOLD", "60m", "SWEEP", "BOS", 1), ("GOLD", "30m", "MS", "BRK", 1), ("SILVER", "30m", "SWEEP", "BOS", 1),
       ("SILVER", "30m", "MS", "BOS", -1)]
EXEC = [(0, 0, 0.0), (0, 1, 0.0), (1, 0, 0.0), (0, 0, -1.0), (0, 0, 2.0), (1, 0, 2.0)]


def trades(name, tf, fam, sub, side, P, seeds=10):
    d5, f15, f30, f60, dd, sw = P
    o, h, l, c = (d5[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
    t5 = d5.time.values
    eod_day = d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1])
    cost = np.array([MD.real_cost(name, p) for p in c])
    f = {"15m": f15, "30m": f30, "60m": f60}[tf].reset_index(drop=True)
    S = pd.DataFrame(E.detect(f, tf, dd, sw), columns=["fam", "sub", "side", "end", "trig", "inv", "atr", "volx", "i"])
    out = []
    for kind, D in (("SIGNAL", S[(S.fam == fam) & (S["sub"] == sub) & (S.side == side)]), ("RANDOM", S[(S.fam == "RND") & (S.side == side)])):
        D = D.copy(); D["act"] = np.searchsorted(t5, D.end.values); D = D[D.act < len(d5)]
        D["day"] = d5.day.values[D.act.values]
        D = D[D.day.isin(eod_day.index) & (pd.to_datetime(D.end).dt.normalize() == D.day)]
        D["eod"] = D.day.map(eod_day).astype(int); D = D[D.act < D.eod]
        D["last_entry"] = np.minimum(D.act + 3 * E.TFS[tf] // 5 - 1, D.eod - 1)
        a = [D.act.values.astype(np.int64), D.side.values.astype(np.int64), D.trig.values.astype(np.float64), D.inv.values.astype(np.float64),
             D.atr.values.astype(np.float64), D.eod.values.astype(np.int64), D.last_entry.values.astype(np.int64)]
        for en, sp, ex in EXEC:
            r = E.sim(o, h, l, c, *a, en, sp, ex, cost)
            m = ~np.isnan(r[:, 0])
            X = D[m].assign(gross=r[m, 0], costR=r[m, 1], ex=f"{('NXT', 'STP')[en]}/{('STR', 'ATR')[sp]}/{ {0.0: 'EOD', -1.0: 'TRL', 2.0: '2R'}[ex] }", kind=kind)
            out.append(X)
    T = pd.concat(out); T["net"] = T.gross - T.costR
    T["per"] = np.where(T.day < MD.Y0, "hist", np.where(T.day < MD.DEV_END, "dev", "valid"))
    return T


if __name__ == "__main__":
    P = {}
    rows = []
    allT = []
    for name, tf, fam, sub, side in CFG:
        if name not in P:
            P[name] = MD.prep(name)
        T = trades(name, tf, fam, sub, side, P[name])
        T["cfg"] = f"{name} {tf} {fam}-{sub} {'BUY' if side > 0 else 'SELL'}"
        allT.append(T)
        for ex, g in T.groupby("ex"):
            s, r = g[g.kind == "SIGNAL"], g[g.kind == "RANDOM"]
            row = dict(cfg=T.cfg.iat[0], exec=ex)
            for p in ("dev", "valid", "hist"):
                row[f"sig_{p}"] = round(s[s.per == p].net.mean(), 3); row[f"rnd_{p}"] = round(r[r.per == p].net.mean(), 3)
                row[f"n_{p}"] = int((s.per == p).sum())
            R = s.net.values
            row["drop5"] = round(R[R < np.quantile(R, 0.95)].mean(), 3) if len(R) > 20 else np.nan
            row["years_pos"] = f"{int((s.groupby(s.day.dt.year).net.mean() > 0).sum())}/{s.day.dt.year.nunique()}"
            rows.append(row)
    S = pd.DataFrame(rows)
    pd.concat(allT).to_csv(ROOT / "research/program/results/mcxe_candidate_trades.csv.gz", index=False)
    S.to_csv(ROOT / "research/program/results/mcxe_candidates.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    print(S.to_string(index=False))

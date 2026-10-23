"""EMA-X-001 – see REGISTRY_EMA.md.  python -m research.search.ema_search [STOCKS|INDEX|MCX]"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import stock_check as SC, stock_search as SR, strategy_search as SS  # noqa
from research.search.intraday_search import prep, SPLIT  # noqa
from alerts.stocks import in_rollover_window  # noqa

PAIRS = [(5, 13), (9, 21), (20, 50)]
FLAGS = ["vol", "oi", "trend", "dtrend", "adx", "rsi", "body", "confirm"]
OUT = ROOT / "research" / "search" / "results_ema"


def trades_for(name, h, lot, oi, kind):
    g = prep(h, oi)
    g["e200"] = I.ema(g["close"], 200)
    g["adx"] = I.adx(g, 14)
    O, H, L, C = (g[c].values for c in ("open", "high", "low", "close"))
    A, day = g["atr"].values, g["day"].values
    n = len(g)
    last_idx = g.groupby("day").cumcount(ascending=False).values      # candles left in the day
    roll = np.array([in_rollover_window(pd.Timestamp(x)) for x in g["day"]]) if kind == "STOCKS" else np.zeros(n, bool)
    rows = []
    for f, s_ in PAIRS:
        ef, es = I.ema(g["close"], f).values, I.ema(g["close"], s_).values
        diff = np.sign(ef - es)
        cross = np.where((diff > 0) & (np.roll(diff, 1) < 0), 1, np.where((diff < 0) & (np.roll(diff, 1) > 0), -1, 0))
        cross[:210] = 0
        for i in np.nonzero(cross)[0]:
            s = int(cross[i])
            if i + 2 >= n or np.isnan(A[i]) or roll[i]:
                continue
            r = g.iloc[i]
            rg = max(H[i] - L[i], 1e-9)
            fl = dict(vol=bool(r.volx > 1.5),
                      oi=bool((r.lb_y if s > 0 else r.sb_y)) if oi is not None else False,
                      trend=bool(s * (C[i] - r.e200) > 0), dtrend=bool(s * r.trend > 0), adx=bool(r.adx > 20),
                      rsi=bool(50 <= r.rsi <= 70) if s > 0 else bool(30 <= r.rsi <= 50),
                      body=bool((C[i] - L[i]) / rg >= 0.7) if s > 0 else bool((H[i] - C[i]) / rg >= 0.7),
                      confirm=bool((C[i + 1] > H[i]) if s > 0 else (C[i + 1] < L[i])) and day[i + 1] == day[i])
            j0 = i + 2 if fl["confirm"] else i + 1                # entry candle index
            if j0 >= n or day[j0] != day[i] and kind != "STOCKS":
                pass
            res = {}
            e0 = O[j0]
            a = A[i]
            # same-day exits
            for nm, sm, tm in (("X1", 1.5, 2.0), ("X2", 1.0, 1.0)):
                if day[j0] != day[i]:
                    res[nm] = None
                    continue
                st, tp = e0 - s * sm * a, e0 + s * tm * a
                px = None
                for k in range(j0, n):
                    if day[k] != day[i]:
                        px = C[k - 1]; break
                    if (L[k] <= st) if s > 0 else (H[k] >= st):
                        px = min(O[k], st) if s > 0 else max(O[k], st); break
                    if (H[k] >= tp) if s > 0 else (L[k] <= tp):
                        px = tp; break
                if px is None:
                    px = C[n - 1]
                res[nm] = (s * (px - e0), sm * a)
            if kind == "STOCKS":
                st = e0 - s * 2 * a
                px = None
                for k in range(j0, min(n, j0 + 35)):
                    if roll[k]:
                        px = O[k]; break
                    if (L[k] <= st) if s > 0 else (H[k] >= st):
                        px = min(O[k], st) if s > 0 else max(O[k], st); break
                    if s * (ef[k] - es[k]) < 0:
                        px = C[k]; break
                if px is None:
                    px = C[min(n, j0 + 35) - 1]
                res["X3"] = (s * (px - e0), 2 * a)
            cp = SC.cost_frac(e0, lot) if kind == "STOCKS" else INS.cost_points(name, e0)
            for nm, v in res.items():
                if v is None:
                    continue
                pnl, R = v
                rows.append(dict(name=name, pair=f"{f}/{s_}", ex=nm, time=g["time"].iat[i], side=s,
                                 r=(pnl - cp) / R, r2=(pnl - 2 * cp) / R, **fl))
    return rows


def evaluate(T, label):
    out = {}
    T["ho"] = T["time"] >= SPLIT
    fl = [f for f in FLAGS if T[f].any()]
    combos = [c for k in range(4) for c in itertools.combinations(fl, k)]
    for (pair, ex), F in T.groupby(["pair", "ex"]):
        for c in combos:
            m = np.ones(len(F), bool)
            for x in c:
                m &= F[x].values
            G = F[m]
            D, Hh = G[~G["ho"]], G[G["ho"]]
            if len(D) < 100:
                continue
            sd = SR.stats(D["r"])
            short = bool(sd["exp_r"] >= 0.05 and (sd["pf"] or 0) >= 1.1 and sd["p5"] > 0 and D["r2"].mean() > 0)
            row = dict(design=sd, shortlisted=short)
            if short:
                sh = SR.stats(Hh["r"])
                h2 = float(Hh["r2"].mean()) if len(Hh) else -9
                row.update(holdout=sh, holdout_2x=round(h2, 3), PASS=bool(sh.get("trades", 0) >= 60 and h2 > 0))
            out[f"{label}|{pair}|{ex}|{'+'.join(c) or 'none'}"] = row
    return out


def main():
    which = sys.argv[1:] or ["STOCKS", "INDEX", "MCX"]
    OUT.mkdir(parents=True, exist_ok=True)
    fres = OUT / "results.json"
    res = json.loads(fres.read_text()) if fres.exists() else {}
    for label in which:
        if label == "STOCKS":
            man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
            items = []
            for r in man.itertuples():
                f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
                if f.exists():
                    h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
                    items.append((r.name, h, r.lot, pd.read_csv(fo) if fo.exists() else None))
        elif label == "INDEX":
            items = [(n, SS.load("NFO", n, "ONE_HOUR"), None, None) for n in ("NIFTY", "BANKNIFTY")]
        else:
            items = [(n, SS.load("MCX", n, "ONE_HOUR"), None, None) for n in ("CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM")]
        rows = []
        for it in items:
            if it[1] is None:
                continue
            rows += trades_for(*it, label)
            print(label, it[0], flush=True)
        T = pd.DataFrame(rows)
        T.to_pickle(OUT / f"trades_{label}.pkl")
        r = evaluate(T, label)
        res.update(r)
        fres.write_text(json.dumps(res, indent=1, default=str))
        sl = {k: v for k, v in r.items() if v["shortlisted"]}
        print(label, "tested", len(r), "shortlisted", len(sl), "PASS", sum(v.get("PASS", False) for v in sl.values()))
        best = sorted(r.items(), key=lambda kv: -kv[1]["design"]["exp_r"])[:5]
        for k, v in best:
            print(" best design:", k, v["design"])
        for k, v in sorted(sl.items(), key=lambda kv: -kv[1]["holdout"].get("exp_r", -9))[:15]:
            print(" ", k, v["design"], "| HO", v["holdout"], v["holdout_2x"], "PASS" if v["PASS"] else "")


if __name__ == "__main__":
    main()

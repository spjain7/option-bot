"""Cycle 2 · 4 – MCX: RSI CONTINUATION BUY and the 1-hour CONTINUATION SELL by OBJECTIVE daily trend, metals vs energy.
Trend (per commodity, from the PREVIOUS completed day; pre-registered): DOWN = daily close < EMA50 and EMA50 lower than
10 sessions earlier; UP = close > EMA50 and EMA50 higher than 10 sessions earlier; NEUTRAL = the rest. (EMA200 is not
used: MCX history starts 2023 and would lose a year to warm-up.)
Strategies: CONTINUATION BUY B1 (RSI crosses >= 75) and S10 (RSI >= 75 + ADX >= 25 + close > EMA50 + 20-bar breakout) on
1h / 3h / 1d; CONTINUATION SELL S9 (RSI <= 25 within 10 bars + close < prior 5-bar low + bearish candle) on 1h (3h as a
check). Exits: next open, structure stop, 2R and 3R, max 45 / 40 / 15 bars; trades never cross a contract switch;
real MCX fees + 1.5 ticks slippage per side.
Expiry / session realism: 'all' and 'no_expiry_week' (no signal in the last 3 sessions before the contract switch) and
'no_late_entry' (intraday: no entry bar starting after 22:30 IST).
Periods: DEV 2023–2024 · VALID 2025 · OOS 2026 (to 3-Nov). python -m research.cycle2.mcx_trend -> results/mcx_trend.csv"""
import numpy as np
import pandas as pd

from research.cycle2 import common as C
from research.rsidiv import engine as E
from research.rsirev import run as RR

CUTS = [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]
PLAN = {"1h": (45, ("B1", "S10", "S9")), "3h": (40, ("B1", "S10", "S9")), "1d": (15, ("B1", "S10"))}
SIDE = {"B1": 1, "S10": 1, "S9": -1}


def trend(b):
    t = pd.to_datetime(b["time"]); c = pd.Series(b["close"].astype(float).values, index=t)
    d = c.groupby(t.dt.normalize().values).last(); e = d.ewm(span=50, adjust=False).mean(); sl = e - e.shift(10)
    lab = pd.Series(np.where((d < e) & (sl < 0), "down", np.where((d > e) & (sl > 0), "up", "neutral")), index=d.index).shift(1)
    return t.dt.normalize().map(lab).fillna("neutral").values


def expiry_week(b):
    sw = b["sw"].fillna(False).astype(bool).values; day = pd.to_datetime(b["time"]).dt.normalize().values
    days = pd.Series(day).drop_duplicates().values; sw_days = set(pd.Series(day[sw]).values)
    out = np.zeros(len(b), bool); idx = {d: i for i, d in enumerate(days)}
    swi = sorted(idx[d] for d in sw_days)
    for k, d in enumerate(day):
        i = idx[d]; nxt = [s for s in swi if s > i]
        out[k] = bool(nxt) and nxt[0] - i <= 3
    return out


def main():
    rows = []
    for tf, (hold, strats) in PLAN.items():
        frames = RR.mcx(tf); pool = E.Pool()
        for f in frames:
            b = f["b"].reset_index(drop=True)
            s, conf, reg, risk = RR.strategies(b, 3)
            ev, _, _ = C.base_events(b)
            sig = {"B1": ev["B1"], "S10": s["S10"], "S9": s["S9"]}
            tr = trend(b); xw = expiry_week(b)
            hm = (pd.to_datetime(b["time"]).dt.hour * 60 + pd.to_datetime(b["time"]).dt.minute).values
            late = np.r_[hm[1:] > 22 * 60 + 30, False] if tf != "1d" else np.zeros(len(b), bool)   # the NEXT bar is the entry bar
            S = {}
            for k in strats:
                for tl in ("all", "down", "up", "neutral"):
                    m = np.ones(len(b), bool) if tl == "all" else (tr == tl)
                    for real, rm in (("all", np.ones(len(b), bool)), ("no_expiry_week", ~xw), ("no_late_entry", ~late)):
                        S[(k, tl, real, SIDE[k])] = sig[k] & m & rm
            # one pool, two risk sides: structure stop
            pool.add(b, S, risk["structure"], f["grp"], f["costf"], f["expid"], f["name"])
        pool.freeze()
        for key in sorted(pool.idx):
            if key[0] not in SIDE:
                continue
            for R in (2.0, 3.0):
                T = pool.run(key, R, hold)
                for grp_name, msk in (("all", np.ones(len(T), bool)), ("metals", T.name.isin(C.METALS).values), ("energy", ~T.name.isin(C.METALS).values)):
                    X = T[msk]
                    lab = E.periods(X.entry.values, CUTS) if len(X) else np.array([])
                    row = dict(market="MCX", tf=tf, strategy=key[0], label="CONTINUATION BUY" if SIDE[key[0]] > 0 else "CONTINUATION SELL",
                               trend=key[1], realism=key[2], group=grp_name, target_R=R, n=len(X), R=round(float(X.netR.mean()), 3) if len(X) else np.nan)
                    for p, _ in CUTS:
                        r = X.netR.values[lab == p] if len(X) else np.array([])
                        row[f"{p}_n"], row[f"{p}_R"] = len(r), (round(float(r.mean()), 3) if len(r) else np.nan)
                        w = r > 0
                        row[f"{p}_PF"] = round(r[w].sum() / -r[~w].sum(), 2) if len(r) and (~w).any() else np.nan
                    if len(X) > 2:
                        dm = X.groupby(pd.to_datetime(X.entry).dt.normalize()).netR.mean()
                        row["t_day"] = round(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))), 2) if dm.std(ddof=1) > 0 else np.nan
                    row["per_commodity"] = "; ".join(f"{n}:{g.netR.mean():+.2f}({len(g)})" for n, g in X.groupby("name")) if len(X) else ""
                    row["PASS"] = bool(len(X) >= 100 and all(row[f"{p}_n"] >= 30 and row[f"{p}_R"] > 0 and (row[f"{p}_PF"] or 0) >= 1.2 for p, _ in CUTS))
                    rows.append(row)
        print(tf, "done", flush=True)
    L = pd.DataFrame(rows)
    p = E.pvals(L.t_day.fillna(0).values); L["FDR10"] = C.bh(np.where(L.t_day.notna(), p, np.nan))
    L.to_csv(C.OUT / "mcx_trend.csv", index=False)
    cols = ["tf", "strategy", "trend", "realism", "group", "target_R", "n", "DEV_R", "VAL_R", "OOS_R", "OOS_n", "t_day", "PASS", "FDR10"]
    print(L[(L.realism == "no_expiry_week") & (L.target_R == 2.0)][cols].to_string(index=False))


if __name__ == "__main__":
    main()

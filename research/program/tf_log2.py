"""TFLOG-002 (30-Oct-2026): 3-month trade logs for the proposed 4-hour rules vs the 5-hour rules and the live MCX 3h BUY, with
the move in favour BEFORE the stop-loss on losing trades and a 'stop to entry after +1R' comparison.
Rules: MCX 4h BUY (lookback 10, vol > 2×, stop 1.5 ATR, 3R) · STOCK 4h SELL (lookback 5, vol > 2×, 2 ATR, 2R) ·
MCX 5h BUY (5, 1.5×, 2.5 ATR, 2.5R) · STOCK 5h SELL (10, 2×, 2.5 ATR, 2.5R) · MCX 3h BUY live (10, 1.5×, 2 ATR, 2R)."""
import json, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from research.program.tf_nh import nhour  # noqa: E402
from research.search import stock_search as SR  # noqa: E402

MCX_PT = {"CRUDEOIL": 100, "NATURALGAS": 1250, "GOLD": 100, "SILVER": 30, "COPPER": 2500, "ZINC": 5000, "ALUMINIUM": 5000}
LOTS = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")["lot"].to_dict()
RULES = {"MCX 4h BUY": ("MCX", 4, 1, 10, 2.0, 1.5, 3.0, 2.5), "STOCK 4h SELL": ("STOCKS", 4, -1, 5, 2.0, 2.0, 2.0, 4.0),
         "MCX 5h BUY": ("MCX", 5, 1, 5, 1.5, 2.5, 2.5, 2.5), "STOCK 5h SELL": ("STOCKS", 5, -1, 10, 2.0, 2.5, 2.5, 4.0),
         "MCX 3h BUY (live)": ("MCX", 3, 1, 10, 1.5, 2.0, 2.0, 2.5)}
START = pd.Timestamp("2026-07-22")


def walk(o, h, l, c, sw, i, side, e0, st, tp, be_at=None):
    """-> exit px, j, why, best. be_at: move the stop to entry once price reached e0 + side*be_at."""
    best = e0; j = i + 1; moved = False
    while j < len(c):
        if j > i + 1 and sw[j]:
            return c[j - 1], j - 1, "contract roll", best
        if j > i + 1 and side * (o[j] - st) <= 0:
            return o[j], j, "stop (gap)" if not moved else "stop at entry (gap)", best
        if j > i + 1 and side * (o[j] - tp) >= 0:
            return o[j], j, "target (gap)", o[j] if side * (o[j] - best) > 0 else best
        if (l[j] <= st) if side > 0 else (h[j] >= st):
            best = max(best, h[j]) if side > 0 else min(best, l[j])
            return st, j, "stop" if not moved else "stop at entry", best
        best = max(best, h[j]) if side > 0 else min(best, l[j])
        if (h[j] >= tp) if side > 0 else (l[j] <= tp):
            return tp, j, "target", best
        if be_at is not None and not moved and side * (best - e0) >= be_at:
            st, moved = e0, True
        if j - (i + 1) >= 40:
            return c[j], j, "time (40 candles)", best
        j += 1
    return c[-1], len(c) - 1, "OPEN at data end", best


def trades(f, cost, side, N, vx, k, rr, cap, mult):
    f = H.features(f.reset_index(drop=True))
    hh = f.high.shift(1).rolling(N).max(); ll = f.low.shift(1).rolling(N).min()
    sig = np.where((f.close > hh) & (f.volx > vx) & (f.close > f.ema200), 1, np.where((f.close < ll) & (f.volx > vx) & (f.close < f.ema200), -1, 0))
    o, h, l, c, a, sw = (f[x].values for x in ("open", "high", "low", "close", "atr", "switch"))
    out, busy = [], -1
    for i in np.flatnonzero(sig == side):
        if i < 210 or i <= busy or i >= len(c) - 1 or sw[i] or sw[i + 1] or not a[i] > 0 or abs(o[i + 1] - c[i]) / a[i] > H.CHASE:
            continue
        e0 = o[i + 1]; R = k * a[i]
        if R / e0 * 100 > cap:
            continue
        st, tp = e0 - side * R, e0 + side * rr * R
        px, j, why, best = walk(o, h, l, c, sw, i, side, e0, st, tp)
        px2, j2, why2, _ = walk(o, h, l, c, sw, i, side, e0, st, tp, be_at=R)
        cs = 2 * float(cost[min(i, len(cost) - 1)])
        out.append(dict(entry_time=str(f.time.iat[i + 1]), exit_time=str(f.time.iat[j]), entry=float(e0), stop=float(st), target=float(tp),
                        exit=float(px), why=why, best=float(best), mfe_R=round(side * (best - e0) / R, 2),
                        pnl=round((side * (px - e0) - cs) * mult), best_rs=round(side * (best - e0) * mult),
                        best_pct=round(side * (best / e0 - 1) * 100, 2), risk_rs=round(R * mult),
                        pnl_be=round((side * (px2 - e0) - cs) * mult), why_be=why2))
        busy = j
    return out


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return []
    rows = []
    for seg, f0, od, cost in fr:
        market, tf0 = seg.split()[0], seg.split()[-1]
        if tf0 != "1h":
            continue
        for rule, (m, n, side, N, vx, k, rr, cap) in RULES.items():
            if m != market:
                continue
            mult = MCX_PT.get(job[1]) if m == "MCX" else LOTS.get(job[1])
            if not mult:
                continue
            f = nhour(f0, market, n)
            cst = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost)
            for t in trades(f, cst, side, N, vx, k, rr, cap, mult):
                if pd.Timestamp(t["entry_time"]) >= START:
                    rows.append(dict(rule=rule, name=job[1], side="BUY" if side > 0 else "SELL", lot=int(mult) if m != "MCX" else None, **t))
    return rows


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    rows.sort(key=lambda r: r["entry_time"])
    (ROOT / "research/program/results/tf_log2.json").write_text(json.dumps(rows))
    T = pd.DataFrame(rows)
    sl = T[T.why.str.startswith("stop")]
    S = T.groupby("rule").agg(calls=("pnl", "size"), wins=("pnl", lambda s: (s > 0).mean() * 100), pnl=("pnl", "sum"),
                              pnl_be=("pnl_be", "sum"), sl_hits=("why", lambda s: s.str.startswith("stop").sum()))
    S = S.join(sl.groupby("rule").agg(sl_best_med_pct=("best_pct", "median"), sl_best_med_rs=("best_rs", "median"),
                                      sl_reached_1R=("mfe_R", lambda s: (s >= 1).mean() * 100)))
    print(S.round(1).to_string())


if __name__ == "__main__":
    main()

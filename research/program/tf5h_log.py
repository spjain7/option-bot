"""TF5H-LOG (30-Oct-2026): trade-by-trade log, last 3 months of data, for the owner's review page.
Rules: MCX 5h BUY (lookback 5, vol > 1.5×, EMA200, stop 2.5 ATR, 2.5R) · STOCK 5h SELL (lookback 10, vol > 2×, below EMA200,
stop 2.5 ATR, 2.5R) · live MCX 3h BUY (lookback 10, vol > 1.5×, EMA200, stop 2 ATR, 2R) for comparison.
Entry next candle open (0.5-ATR chase rule), stop first inside a candle, gaps fill at the open, max 40 candles.
Per lot: MCX ₹ per point per lot (CRUDEOIL 100, GOLD 100, SILVER 30, COPPER 2500, ZINC / ALUMINIUM 5000), stocks = lot size.
Costs: 2× live costs. 'Best' = highest high after a BUY / lowest low after a SELL until the exit."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from research.program.tf5h import five_hour  # noqa: E402
from research.search import stock_search as SR  # noqa: E402

MCX_PT = {"CRUDEOIL": 100, "NATURALGAS": 1250, "GOLD": 100, "SILVER": 30, "COPPER": 2500, "ZINC": 5000, "ALUMINIUM": 5000}
LOTS = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")["lot"].to_dict()
RULES = {"MCX 5h BUY": ("MCX", "5h", 1, 5, 1.5, 2.5, 2.5, 2.5), "STOCK 5h SELL": ("STOCKS", "5h", -1, 10, 2.0, 2.5, 2.5, 4.0),
         "MCX 3h BUY (live)": ("MCX", "3h", 1, 10, 1.5, 2.0, 2.0, 2.5)}
START = pd.Timestamp("2026-07-22")


def trades(f, cost, side, N, vx, k, rr, cap):
    f = H.features(f.reset_index(drop=True)); 
    hh = f.high.shift(1).rolling(N).max(); ll = f.low.shift(1).rolling(N).min()
    sig = np.where((f.close > hh) & (f.volx > vx) & (f.close > f.ema200), 1, np.where((f.close < ll) & (f.volx > vx) & (f.close < f.ema200), -1, 0))
    o, h, l, c, a, sw = (f[x].values for x in ("open", "high", "low", "close", "atr", "switch"))
    out, busy = [], -1
    for i in np.flatnonzero(sig == side):
        if i < 210 or i <= busy or i >= len(c) - 1 or sw[i] or sw[i + 1] or not a[i] > 0:
            continue
        if abs(o[i + 1] - c[i]) / a[i] > H.CHASE:
            continue
        e0 = o[i + 1]; R = k * a[i]
        if R / e0 * 100 > cap:
            continue
        st, tp = e0 - side * R, e0 + side * rr * R
        best = e0; px = why = None; j = i + 1
        while j < len(c):
            if j > i + 1 and sw[j]:
                px, why, j = c[j - 1], "contract roll", j - 1; break
            if j > i + 1 and side * (o[j] - st) <= 0:
                px, why = o[j], "stop (gap)"; break
            if j > i + 1 and side * (o[j] - tp) >= 0:
                px, why = o[j], "target (gap)"; best = o[j] if side * (o[j] - best) > 0 else best; break
            if (l[j] <= st) if side > 0 else (h[j] >= st):
                best = max(best, h[j]) if side > 0 else min(best, l[j])
                px, why = st, "stop"; break
            best = max(best, h[j]) if side > 0 else min(best, l[j])
            if (h[j] >= tp) if side > 0 else (l[j] <= tp):
                px, why = tp, "target"; break
            if j - (i + 1) >= 40:
                px, why = c[j], "time (40 candles)"; break
            j += 1
        if px is None:
            px, why, j = c[-1], "OPEN at data end", len(c) - 1
        out.append(dict(i=i, sig_time=str(f.time.iat[i]), entry_time=str(f.time.iat[i + 1]), exit_time=str(f.time.iat[j]),
                        entry=float(e0), stop=float(st), target=float(tp), exit=float(px), why=why, best=float(best),
                        cost=float(cost[min(i, len(cost) - 1)]), volx=float(f.volx.iat[i]), level=float(hh.iat[i] if side > 0 else ll.iat[i])))
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
        for rule, (m, tf, side, N, vx, k, rr, cap) in RULES.items():
            if m != market:
                continue
            if tf == "5h" and tf0 == "1h":
                f = five_hour(f0, market)
                cst = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost)
            elif tf == "3h" and tf0 == "3h":
                f, cst = f0, cost
            else:
                continue
            name = job[1]
            mult = MCX_PT.get(name) if m == "MCX" else LOTS.get(name)
            if not mult:
                continue
            for t in trades(f, cst, side, N, vx, k, rr, cap):
                if pd.Timestamp(t["entry_time"]) < START:
                    continue
                pnl = (side * (t["exit"] - t["entry"]) - 2 * t["cost"]) * mult
                rows.append(dict(rule=rule, name=name, side="BUY" if side > 0 else "SELL", lot=int(mult) if m != "MCX" else None,
                                 rs_pt=mult, **{k_: v for k_, v in t.items() if k_ != "i"},
                                 pnl=round(pnl), best_rs=round(side * (t["best"] - t["entry"]) * mult),
                                 best_pct=round(side * (t["best"] / t["entry"] - 1) * 100, 2),
                                 risk_rs=round(abs(t["entry"] - t["stop"]) * mult)))
    return rows


def main():
    from multiprocessing import Pool
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    rows.sort(key=lambda r: r["entry_time"])
    (ROOT / "research/program/results/tf5h_log.json").write_text(json.dumps(rows))
    T = pd.DataFrame(rows)
    print(T.groupby("rule").agg(n=("pnl", "size"), win=("pnl", lambda s: (s > 0).mean() * 100), pnl=("pnl", "sum"),
                                best_med=("best_pct", "median"), first=("entry_time", "min"), last=("entry_time", "max")).round(1).to_string())


if __name__ == "__main__":
    main()

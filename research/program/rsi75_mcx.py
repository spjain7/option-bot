"""RSI75-MCX (28-Oct-2026): owner's question – after RSI(14) rises above 75 (SELL idea), with volume support, what does the
price of NATURALGAS / SILVER / CRUDEOIL / COPPER actually do next? 15-minute, 1-hour, 3-hour and 4-hour candles.

Signal: RSI(14) closes above 75 for the FIRST time (previous bar ≤ 75). "+ volume": that bar's volume ≥ 1.5× its 20-bar
average. Entry reference = next bar's OPEN (when a SELL could be placed). Moves are measured from there:
  move after N bars (close), best fall (lowest low) and worst rise (highest high) within N bars, in % of price.
Comparison: the same measures from EVERY bar (what price does on average) – a signal is only useful if it beats this.
Signals whose window crosses a contract switch are dropped. OI: MCX OI history is not available (Angel does not serve it,
15-minute files have no OI) – the OI condition cannot be tested on past data.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import strategy_search as SS  # noqa: E402
from alerts import stats as ST  # noqa: E402
from research.program.reversal import rsi  # noqa: E402

NAMES = ["NATURALGAS", "SILVER", "CRUDEOIL", "COPPER"]
HOR = {"15m": 8, "1h": 6, "3h": 4, "4h": 3}            # look-ahead ≈ 2 h, 6 h, 12 h, 12 h


def four_hour(h):
    d = h.copy(); d["day"] = d["time"].dt.normalize(); d["k"] = d.groupby("day").cumcount() // 4
    g = d.groupby(["day", "k"])
    return pd.DataFrame(dict(time=g["time"].first(), open=g["open"].first(), high=g["high"].max(), low=g["low"].min(),
                             close=g["close"].last(), volume=g["volume"].sum())).reset_index(drop=True)


def frames(name):
    h = SS.load("MCX", name, "ONE_HOUR")
    sw = SS.switch_days(name, "MCX", h)
    out = {"1h": h.reset_index(drop=True), "3h": ST.three_hour_generic(h).reset_index(drop=True), "4h": four_hour(h)}
    for k in out:
        out[k]["sw"] = out[k]["time"].dt.normalize().isin(sw)
    p = ROOT / "research/data/obuy_mcx" / f"fut_{name}.csv"
    if p.exists():
        m = pd.read_csv(p, parse_dates=["time"]).sort_values("time").drop_duplicates("time").reset_index(drop=True)
        m["sw"] = False
        out["15m"] = m
    return out


def measure(f, N, idx):
    o, h, l, c, sw = (f[x].values for x in ("open", "high", "low", "close", "sw"))
    rows = []
    for i in idx:
        if i + N >= len(c) or sw[i + 1:i + N + 1].any():
            continue
        e = o[i + 1]
        rows.append(dict(time=f["time"].iat[i], move=(c[i + N] / e - 1) * 100, best_fall=(l[i + 1:i + N + 1].min() / e - 1) * 100,
                         worst_rise=(h[i + 1:i + N + 1].max() / e - 1) * 100))
    return pd.DataFrame(rows)


def summ(m):
    if len(m) == 0:
        return dict(n=0)
    return dict(n=len(m), fell_pct=round((m.move < 0).mean() * 100, 1), avg_move=round(m.move.mean(), 2),
                median_move=round(m.move.median(), 2), avg_best_fall=round(m.best_fall.mean(), 2),
                avg_worst_rise=round(m.worst_rise.mean(), 2),
                fall_beats_rise=round((m.best_fall.abs() > m.worst_rise).mean() * 100, 1))


def main():
    rows = []
    for name in NAMES:
        for tf, f in frames(name).items():
            N = HOR[tf]
            r = rsi(f["close"]).values
            v = f["volume"].astype(float); vx = (v / v.rolling(20).mean().shift(1)).values
            first = (r > 75) & (np.r_[np.nan, r[:-1]] <= 75)
            sig = np.flatnonzero(first & (np.arange(len(r)) > 30))
            sigv = np.flatnonzero(first & (vx >= 1.5) & (np.arange(len(r)) > 30))
            base = measure(f, N, np.arange(30, len(f)))
            yrs = f"{f['time'].iat[0]:%b-%y}→{f['time'].iat[-1]:%b-%y}"
            for lab, idx in (("every bar (baseline)", None), ("RSI > 75", sig), ("RSI > 75 + volume ≥ 1.5×", sigv)):
                m = base if idx is None else measure(f, N, idx)
                rows.append(dict(name=name, tf=tf, data=yrs, look_ahead=f"{N} bars", signal=lab, **summ(m)))
    T = pd.DataFrame(rows)
    out = ROOT / "research/program/results/rsi75_mcx.csv"
    T.to_csv(out, index=False)
    pd.set_option("display.width", 250)
    print(T.to_string(index=False))


if __name__ == "__main__":
    main()

"""STOCK-CHECK-001 – the LIVE volume-breakout rule (alerts/breakout.py, unchanged) on NSE stock futures (lot < 3000).
Stocks were NOT used to choose the rule, so this is a genuine out-of-sample test of it.
Pre-registered PASS (pooled over all stocks, per timeframe): ≥ 100 trades, ≥ +0.10R, PF ≥ 1.20, bootstrap p5 > 0,
> 0 at 2× costs, positive in both halves (before / after Jul-2024).
Costs per round trip: ₹40 brokerage per lot + 18% GST, STT 0.02% (sell), exchange 0.00173% ×2, stamp 0.002% (buy),
slippage 0.03% per side. Entries: next candle open; stop 2 ATR, 3-ATR trailing on closes, max 40 candles; no entry on
the first session after a monthly expiry and every trade closed before it (no roll gap in P&L).
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import breakout as BO, engine as E, stocks as STK  # noqa
from crude import indicators as I  # noqa

DATA = ROOT / "research" / "data" / "angel" / "NFO_STK"
SPLIT = pd.Timestamp("2024-07-01")


def cost_frac(price, lot, cx=1.0):
    pct = 0.0002 + 2 * 0.0000173 + 0.00002 + 2 * 0.0003 + 0.18 * 2 * 0.0000173
    return cx * (pct * price + 40 * 1.18 / lot)


def signals(df):
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
    hh, ll = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    va = v.rolling(20).mean().shift(1)
    e = I.ema(c, 200)
    return np.where((c > hh) & (v > 1.5 * va) & (c > e), 1, np.where((c < ll) & (v > 1.5 * va) & (c < e), -1, 0))


def run(df, lot, roll_days):
    df = df.reset_index(drop=True)
    sig = signals(df)
    a = I.atr(df, 14).values
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    day = df["time"].dt.normalize()
    rd = day.isin(roll_days).values
    nx = np.r_[rd[1:], False] & (day.values != np.r_[day.values[1:], day.values[-1]])
    out, pos = [], None
    for i in range(210, len(df) - 1):
        if pos is not None:
            s, e0, st, risk, k0, best = pos
            px = None
            if (o[i] <= st) if s > 0 else (o[i] >= st):
                px = o[i]
            elif (l[i] <= st) if s > 0 else (h[i] >= st):
                px = st
            elif nx[i] or i - k0 >= BO.CFG["max_candles"]:
                px = c[i] if nx[i] else o[i + 1]
            if px is not None:
                out.append((df["time"].iat[k0], s * (px - e0), cost_frac(e0, lot), risk))
                pos = None
            else:
                best = max(best, c[i]) if s > 0 else min(best, c[i])
                ns = best - s * BO.CFG["trail_atr"] * a[i]
                if s * (ns - st) > 0:
                    st = ns
                pos = (s, e0, st, risk, k0, best)
            continue
        if sig[i] == 0 or rd[i] or nx[i] or not a[i] > 0:
            continue
        s = int(sig[i]); e0 = o[i + 1]; risk = BO.CFG["stop_atr"] * a[i]
        pos = (s, e0, e0 - s * risk, risk, i + 1, e0)
    return out


def main():
    man = pd.read_csv(DATA / "manifest_stocks.csv")
    rows = []
    for r in man.itertuples():
        f = DATA / f"{r.name}_ONE_HOUR.csv"
        if not f.exists():
            continue
        h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        h = h[(h["time"].dt.hour >= 9)].reset_index(drop=True)
        days = pd.Series(pd.unique(h["time"].dt.normalize()))
        roll = set()
        for y in range(days.min().year, days.max().year + 1):
            for m in range(1, 13):
                e = STK.nfo_expiry(y, m)
                nxt = days[days > e]
                if len(nxt):
                    roll.add(nxt.iloc[0])
        far = pd.Timestamp("2100-01-01")
        f3 = E.positional_candles(h, "NFO", far)
        fd = BO.daily_candles(h, None)
        for tf, df in (("3h", f3), ("1d", fd)):
            for t0, g, cp, risk in run(df, r.lot, roll):
                rows.append((r.name, tf, pd.Timestamp(t0), (g - cp) / risk, (g - 2 * cp) / risk))
        print(r.name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "time", "r1", "r2"])
    T["half"] = np.where(T["time"] < SPLIT, "A", "B")
    res = {}
    rng = np.random.default_rng(7)
    for tf, g in T.groupby("tf"):
        r = g["r1"]; w, l = r[r > 0], r[r <= 0]
        p5 = float(np.percentile(rng.choice(r.values, (4000, len(r))).mean(axis=1), 5))
        halves = g.groupby("half")["r1"].mean().round(3).to_dict()
        by_year = g.groupby(g["time"].dt.year)["r1"].agg(["count", "mean"]).round(3).to_dict("index")
        per = g.groupby("name")["r1"].mean()
        cr = g.sort_values("time")["r1"].cumsum()
        m = dict(trades=int(len(r)), stocks=int(g["name"].nunique()), exp_r=round(float(r.mean()), 3), exp_2x=round(float(g["r2"].mean()), 3),
                 win=round(float((r > 0).mean() * 100), 1), pf=round(float(w.sum() / -l.sum()), 2), p5=round(p5, 3),
                 halves=halves, by_year=by_year, max_dd_r=round(float((cr - cr.cummax()).min()), 1),
                 stocks_positive_pct=round(float((per > 0).mean() * 100), 1),
                 best_stocks=per.sort_values(ascending=False).head(10).round(2).to_dict(),
                 worst_stocks=per.sort_values().head(10).round(2).to_dict())
        m["PASS"] = bool(m["trades"] >= 100 and m["exp_r"] >= 0.10 and m["pf"] >= 1.2 and m["p5"] > 0 and m["exp_2x"] > 0
                         and all(v > 0 for v in halves.values()) and len(halves) == 2)
        res[tf] = m
        print(tf, json.dumps(m, default=str)[:900], flush=True)
    out = ROOT / "research" / "search" / "results_stock"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    T.to_csv(out / "trades.csv.gz", index=False)


if __name__ == "__main__":
    main()

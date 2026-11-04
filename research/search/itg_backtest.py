"""ITG-001 (4-Nov-2026) – historical check of the owner's TradingView "ITG Scalper with Early Signals" (default inputs).

BUY  = MACD(12,26) crosses above its 9-SMA signal AND TEMA(14) rising;  SELL = cross below AND TEMA falling.
Entry at the next candle's open. Nothing tuned. Two ways of trading it are measured:
  A. fixed stop (1 or 2 x ATR14) -> +0.5R / +1R / +2R reached before the stop (costs 0.1R), vs RANDOM entries
  B. stop-and-reverse (how the script is drawn): hold until the opposite signal, exit next open; % return after costs
     (MCX / index 0.04 %, stocks 0.06 % round trip), win rate, profit factor.
Timeframes: MCX 5m and 15m (Jul-2023 ->, stitched front month, roll gaps removed), MCX / index / stocks 1h, 3h, 1d.

  python -m research.search.itg_backtest     -> research/search/results_itg/*
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_itg"
MAXH = {"5m": 48, "15m": 32, "1h": 40, "3h": 30, "1d": 30}
COST_PCT = {"MCX": 0.04, "IDX": 0.04, "STK": 0.06}
MCX7 = ("CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM")


def ema(x, n):
    return pd.Series(x, dtype=float).ewm(span=n, adjust=False).mean()


def itg(df):
    c = df["close"].astype(float)
    e1 = ema(c, 14); e2 = ema(e1, 14); e3 = ema(e2, 14)
    tema = 3 * (e1 - e2) + e3
    m = ema(c, 12) - ema(c, 26); s = m.rolling(9).mean()
    up = (m > s) & (m.shift() <= s.shift()) & (tema > tema.shift())
    dn = (m < s) & (m.shift() >= s.shift()) & (tema < tema.shift())
    sig = np.where(up, 1, np.where(dn, -1, 0))
    sig[:60] = 0
    return sig


def minute_sets():
    for name in MCX7:
        fs = sorted((ROOT / "research/data/angel/MCX").glob(f"{name}*_FIVE_MINUTE.csv"))
        if not fs:
            continue
        d = pd.read_csv(fs[-1], parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
        d = d.sort_values("time").drop_duplicates("time").iloc[:-1].reset_index(drop=True)
        d5 = d.copy(); d5["switch"] = H.mark_switch(d5, set(), split_gap=0.025)
        yield "MCX", "5m", name, d5
        g = d.set_index("time").resample("15min", label="left", closed="left")
        d15 = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()
        d15["switch"] = H.mark_switch(d15, set(), split_gap=0.025)
        yield "MCX", "15m", name, d15


def sar(df, sig, cost):
    """Stop-and-reverse on the indicator: returns list of (entry_index, side, net % return)."""
    o = df["open"].values; sw = df["switch"].values.astype(bool)
    out, pos, ei = [], 0, None
    for i in np.flatnonzero(sig):
        if i + 1 >= len(o):
            break
        s = sig[i]
        if pos != 0 and s != pos:
            blocked = sw[ei + 1:i + 2].any()
            if not blocked:
                out.append((ei, pos, pos * (o[i + 1] / o[ei + 1] - 1) * 100 - cost))
            pos = 0
        if pos == 0:
            pos, ei = s, i
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, srows = [], []
    import itertools
    for seg, tf, name, df in itertools.chain(minute_sets(), H.datasets()):
        df = df.reset_index(drop=True)
        sig = itg(df)
        F = H.features(df, "1d" if tf in ("1d",) else "1h") if tf in ("1h", "3h", "1d") else dict(
            a=H.I.atr(df, 14).values)
        for stop in ("1.0", "2.0"):
            for side in (1, -1):
                valid, res = H.outcomes(df, F, side, stop, MAXH[tf])
                for kind, mask in (("signal", sig == side), ("random", np.arange(len(df)) >= 60)):
                    idx = np.flatnonzero(mask & valid)
                    if kind == "random" and len(idx) > 4000:
                        idx = np.sort(np.random.default_rng(1).choice(idx, 4000, replace=False))
                    for i in idx:
                        rows.append((seg, tf, name, stop, "BUY" if side > 0 else "SELL", kind, df["time"].iloc[i],
                                     res[0.5]["win"][i], res[1.0]["win"][i], res[2.0]["win"][i], res[2.0]["r"][i]))
        for ei, s, r in sar(df, sig, COST_PCT[seg]):
            srows.append((seg, tf, name, "BUY" if s > 0 else "SELL", df["time"].iloc[ei], r))
        print(seg, tf, name, int((sig != 0).sum()), "signals", flush=True)
    t = pd.DataFrame(rows, columns=["seg", "tf", "name", "stop", "side", "kind", "time", "w05", "w1", "w2", "R2"])
    s = pd.DataFrame(srows, columns=["seg", "tf", "name", "side", "time", "ret"])
    t.to_csv(OUT / "fixed_stop.csv.gz", index=False); s.to_csv(OUT / "sar_trades.csv.gz", index=False)
    a = t.groupby(["seg", "tf", "stop", "kind"]).agg(n=("w1", "size"), w05=("w05", "mean"), w1=("w1", "mean"),
                                                     w2=("w2", "mean"), avgR=("R2", "mean")).round(3)
    a.to_csv(OUT / "fixed_stop_summary.csv")
    def pf(x):
        g, l = x[x > 0].sum(), -x[x < 0].sum()
        return round(g / l, 2) if l else np.nan
    b = s.groupby(["seg", "tf"]).agg(trades=("ret", "size"), win=("ret", lambda x: round((x > 0).mean(), 3)),
                                     avg_pct=("ret", lambda x: round(x.mean(), 3)), pf=("ret", pf))
    s["year"] = pd.to_datetime(s.time).dt.year
    by = s.groupby(["seg", "tf", "year"]).agg(trades=("ret", "size"), win=("ret", lambda x: round((x > 0).mean(), 3)),
                                              avg_pct=("ret", lambda x: round(x.mean(), 3)), pf=("ret", pf))
    b.to_csv(OUT / "sar_summary.csv"); by.to_csv(OUT / "sar_by_year.csv")
    pd.set_option("display.width", 200)
    print(a.to_string()); print(b.to_string()); print(by.to_string())


if __name__ == "__main__":
    main()

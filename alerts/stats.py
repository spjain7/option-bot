"""Historical check of the RSI-reversal alert rule on REAL Angel candles (research/data). Not used by the live alerts.

  python -m alerts.stats   -> alerts/STATS.md

For every alert: next-candle-open entry is NOT assumed – the alert's own plan is scored as sent (entry = signal close),
then also with a realistic fill at the next candle's open. SL checked before target inside a candle (conservative).
Outcome: SL, T1-then-cost (after T1 the SL moves to entry), T2, or time exit after 20 candles. Costs ≈ 0.1R per trade.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from alerts import signals as S  # noqa: E402
from crude import indicators as I  # noqa: E402

DATA = ROOT / "research" / "data" / "angel"
COST_R = 0.10


def front_file(exch, name, iv):
    man = pd.read_csv(DATA / "manifest.csv")
    r = man[(man["name"] == name) & (man["interval"] == iv) & (man["front_stitched"])]
    return None if r.empty else DATA / exch / f"{r.iloc[0]['symbol']}_{iv}.csv"


def three_hour_generic(h):
    d = h.copy()
    d["day"] = d["time"].dt.normalize()
    d["k"] = d.groupby("day").cumcount() // 3
    g = d.groupby(["day", "k"])
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"), n=("close", "size")).reset_index(drop=True)
    return out[out["n"] >= 2].reset_index(drop=True)


def score(df, max_hold=20, h1=None):
    df = df.reset_index(drop=True)
    r = I.rsi(df["close"], 14).values
    atr = I.atr(df, 14).values
    rows = []
    day = df["time"].dt.normalize().values
    for i in range(60, len(df) - 1):
        lo, hi = np.nanmin(r[i - 2:i + 1]), np.nanmax(r[i - 2:i + 1])
        if not (lo < S.RSI_BUY or hi > S.RSI_SELL):
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        bull, bear = S.patterns(df.iloc[i - 2:i + 1], a)
        for side, ok, pats in (("BUY", lo < S.RSI_BUY and bull, bull), ("SELL", hi > S.RSI_SELL and bear, bear)):
            if not ok:
                continue
            s = 1 if side == "BUY" else -1
            w = df.iloc[i - 2:i + 1]
            ext = w["low"].min() if s > 0 else w["high"].max()
            dist = max(s * (df.at[i, "close"] - (ext - s * S.SL_BUF_ATR * a)), S.SL_MIN_ATR * a)
            if dist > S.SL_MAX_ATR * a:
                continue
            win = df.iloc[max(0, i - 300):i + 1]
            hw = None if h1 is None else h1[h1["time"] <= df.at[i, "time"]].tail(200)
            ev = S.evaluate(win, "x", hw if hw is not None else win)
            passed = ev["kind"] == side
            entry = df.at[i + 1, "open"]                       # realistic: next candle's open
            sl, t1, t2 = entry - s * dist, entry + s * dist, entry + 2 * s * dist
            res, t1hit = None, False
            for j in range(i + 1, min(i + 1 + max_hold, len(df))):
                h, l = df.at[j, "high"], df.at[j, "low"]
                stop = entry if t1hit else sl
                if (l <= stop) if s > 0 else (h >= stop):
                    res = 0.5 if t1hit else -1.0                # half booked at T1, rest at cost
                    break
                if not t1hit and ((h >= t1) if s > 0 else (l <= t1)):
                    t1hit = True
                if (h >= t2) if s > 0 else (l <= t2):
                    res = 1.5                                   # half at 1R + half at 2R
                    break
            if res is None:
                last = df.at[min(i + max_hold, len(df) - 1), "close"]
                res = (0.5 + 0.5 * s * (last - entry) / dist) if t1hit else s * (last - entry) / dist
            rows.append(dict(time=df.at[i, "time"], side=side, pattern=pats[0].split(" (")[0], r=res - COST_R, t1=t1hit, passed=passed))
    return pd.DataFrame(rows)


def summarise(t):
    if t.empty:
        return dict(alerts=0)
    r = t["r"]
    w, l = r[r > 0], r[r <= 0]
    rng = np.random.default_rng(7)
    b = rng.choice(r.values, (3000, len(r))).mean(axis=1)
    return dict(alerts=len(t), t1_reached_pct=round(t["t1"].mean() * 100, 1), win_pct=round((r > 0).mean() * 100, 1),
                avg_r=round(r.mean(), 3), pf=round(w.sum() / -l.sum(), 2) if l.sum() < 0 else None,
                p5=round(float(np.percentile(b, 5)), 3), per_year=round(len(t) / max(1, (t["time"].max() - t["time"].min()).days / 365), 1))


def main():
    out = ["# RSI-reversal alert rule – historical check (real Angel candles)", "",
           "Entry at the next candle's open, SL checked first, half booked at T1 (SL to cost), rest at T2 or after 20 candles, "
           "costs ≈ 0.1R. Stitched front-month series (contract switches not removed – small distortion). Exploratory, not proof.", "",
           "| Instrument | TF | Alerts (after quality filter) | /year | T1 reached | Win % | Avg R | PF | Bootstrap p5 | BUY avg R | SELL avg R |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for exch, name in (("MCX", "CRUDEOIL"), ("MCX", "GOLD"), ("MCX", "SILVER"), ("MCX", "NATURALGAS"), ("MCX", "COPPER"),
                       ("NFO", "NIFTY"), ("NFO", "BANKNIFTY")):
        for tf, iv in (("15m", "FIFTEEN_MINUTE"), ("1h", "ONE_HOUR"), ("3h", "ONE_HOUR")):
            f = front_file(exch, name, iv)
            if f is None or not f.exists():
                continue
            d = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
            src = d
            h1 = d if iv == "ONE_HOUR" else d.groupby(d["time"].dt.floor("h")).agg(time=("time", "first"), open=("open", "first"),
                    high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)
            if tf == "3h":
                d = three_hour_generic(d)
            t_all = score(d, h1=h1)
            t = t_all[t_all["passed"]] if len(t_all) else t_all
            ma = summarise(t_all)
            out.append(f"| {name} | {tf} | ALL candidates (no quality filter) | {ma.get('alerts', 0)} | | | | {ma.get('avg_r', '–')} | {ma.get('pf', '–')} | {ma.get('p5', '–')} | | |")
            m = summarise(t)
            sb = {k: round(g["r"].mean(), 3) for k, g in t.groupby("side")} if len(t) else {}
            out.append(f"| {name} | {tf} | **filtered** {m.get('alerts', 0)} | {m.get('per_year', '–')} | {m.get('t1_reached_pct', '–')}% | {m.get('win_pct', '–')}% | "
                       f"{m.get('avg_r', '–')} | {m.get('pf', '–')} | {m.get('p5', '–')} | {sb.get('BUY', '–')} | {sb.get('SELL', '–')} |")
            print(out[-1], flush=True)
    (ROOT / "alerts" / "STATS.md").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

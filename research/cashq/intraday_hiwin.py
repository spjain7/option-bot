"""CASH INTRADAY high-win-rate (owner 18-Nov-2026): published high-hit-rate intraday ideas on Angel 5-minute NSE cash candles
(research/data/angel/NSE_EQ, ~218-360 liquid stocks, 2024-10 .. 2026-11). SURVIVORSHIP: the list is stocks liquid today ->
results are biased upward. Signal on a bar's close, entry at the NEXT bar's open, one trade per stock per day per setup,
square-off at the 15:15 bar's close. Costs 0.10 % per round trip (brokerage, STT, charges, slippage).
  GAPFILL_L  stock above its 50-day average, opens 1-4 % BELOW yesterday's close -> buy at 09:20; target yesterday's close
  GAPFILL_S  stock below its 50-day average, opens 1-4 % ABOVE yesterday's close -> short at 09:20; target yesterday's close
  VWAP_L     stock above its 20-day average, after 10:30 a 5-min close >= 1.2 % below VWAP -> buy; target VWAP
  VWAP_S     mirror (below the 20-day average, 1.2 % above VWAP) -> short; target VWAP
  RSI2_L     stock above its 50-day average, 15-min RSI(2) < 5 after 10:00 -> buy; exit 15-min close above its 5-bar average
  RSI2_S     mirror
  stops 1 % / 1.5 % / 2 % from entry (or none); all exits by 15:15.
Split: first half (2024-10 .. 2025-10) vs second half (2025-11 .. 2026-11).
python -m research.cashq.intraday_hiwin -> results/intraday_hiwin.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
COST = 0.0010
SPLIT = pd.Timestamp("2025-11-01")


@njit(cache=True)
def sim(o, h, l, c, day, sq, sig, side, tgt, exs, stop_pct):
    """sq[i]: True at the square-off bar (15:15) of each day. tgt: target price per signal bar (nan = none); exs: exit-signal
    per bar (close -> exit at that close). Returns entry idx, net return."""
    n = len(c); ei = np.empty(n, np.int64); rt = np.empty(n); m = 0; t = 0; done_day = -1
    while t < n - 1:
        if not sig[t] or day[t] == done_day or sq[t]:
            t += 1; continue
        e = t + 1
        if day[e] != day[t]:
            t += 1; continue
        px = o[e]; tg = tgt[t]; st = px * (1 - side * stop_pct) if stop_pct > 0 else np.nan
        j = e; out = np.nan
        while j < n and day[j] == day[e]:
            if stop_pct > 0 and ((side > 0 and l[j] <= st) or (side < 0 and h[j] >= st)):
                out = st if j > e or (side > 0 and o[j] > st) or (side < 0 and o[j] < st) else o[j]; break
            if not np.isnan(tg) and ((side > 0 and h[j] >= tg) or (side < 0 and l[j] <= tg)):
                out = max(o[j], tg) if side > 0 else min(o[j], tg); break
            if exs[j] or sq[j]:
                out = c[j]; break
            j += 1
        if np.isnan(out):
            out = c[j - 1]
        ei[m] = e; rt[m] = side * (out / px - 1) - COST; m += 1
        done_day = day[t]
        while t < n and day[t] == done_day:
            t += 1
    return ei[:m], rt[:m]


def rsi(x, n=2):
    d = np.diff(x, prepend=np.nan)
    up = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    dn = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + up / np.where(dn == 0, np.nan, dn))


def prep(sym):
    d = D.intraday(sym)
    if len(d) < 5000:
        return None
    t = d["time"]; day = t.dt.normalize(); mins = (t.dt.hour * 60 + t.dt.minute).values
    dd = d.groupby(day).agg(open=("open", "first"), close=("close", "last"))
    dd["pc"] = dd.close.shift(1); dd["sma50"] = dd.close.rolling(50).mean().shift(1); dd["sma20"] = dd.close.rolling(20).mean().shift(1)
    dd["pclose_up50"] = dd.pc > dd.sma50; dd["pclose_up20"] = dd.pc > dd.sma20
    m = dd.reindex(day.values)
    o, h, l, c, v = (d[x].values.astype(float) for x in ("open", "high", "low", "close", "volume"))
    tp = (h + l + c) / 3
    cum_pv = pd.Series(tp * v).groupby(day.values).cumsum().values; cum_v = pd.Series(v).groupby(day.values).cumsum().values
    vwap = cum_pv / np.where(cum_v == 0, np.nan, cum_v)
    dayid = pd.factorize(day)[0].astype(np.int64)
    sq = mins == 915
    # 15-minute RSI(2), known at the close of each 15-min block (bars ending at :25, :40, :55, :10 of the hour)
    blk = (mins - 555) // 15
    key = dayid * 100 + blk
    c15 = pd.Series(c).groupby(key).last()
    r15 = pd.Series(rsi(c15.values, 2), index=c15.index); s5 = c15.rolling(5).mean()
    last_in_blk = np.r_[key[1:] != key[:-1], True]
    R15 = np.where(last_in_blk, r15.reindex(key).values, np.nan)
    X15 = np.where(last_in_blk, (c15 > s5).reindex(key).values, False)
    X15s = np.where(last_in_blk, (c15 < s5).reindex(key).values, False)
    return dict(o=o, h=h, l=l, c=c, day=dayid, sq=sq, mins=mins, vwap=vwap, pc=m.pc.values, op=m.open.values, up50=m.pclose_up50.values.astype(bool),
                dn50=(~m.pclose_up50.values.astype(bool)) & np.isfinite(m.sma50.values), up20=m.pclose_up20.values.astype(bool),
                dn20=(~m.pclose_up20.values.astype(bool)) & np.isfinite(m.sma20.values), R15=R15, X15=X15.astype(bool), X15s=X15s.astype(bool),
                time=t.values)


def setups(P):
    mins = P["mins"]; gap = P["op"] / P["pc"] - 1; first = mins == 555
    S = {}
    nan = np.full(len(mins), np.nan); no = np.zeros(len(mins), bool)
    S["GAPFILL_L"] = (first & P["up50"] & (gap <= -0.01) & (gap >= -0.04), 1, P["pc"], no)
    S["GAPFILL_S"] = (first & P["dn50"] & (gap >= 0.01) & (gap <= 0.04), -1, P["pc"], no)
    late = (mins >= 630) & (mins <= 870)
    S["VWAP_L"] = (late & P["up20"] & (P["c"] <= P["vwap"] * (1 - 0.012)), 1, P["vwap"], no)
    S["VWAP_S"] = (late & P["dn20"] & (P["c"] >= P["vwap"] * (1 + 0.012)), -1, P["vwap"], no)
    r = P["R15"]; mid = (mins >= 600) & (mins <= 870)
    S["RSI2_L"] = (mid & P["up50"] & (r < 5), 1, nan, P["X15"])
    S["RSI2_S"] = (mid & P["dn50"] & (r > 95), -1, nan, P["X15s"])
    return S


def main():
    syms = D.intraday_symbols(); acc = {}
    for i, s in enumerate(syms):
        try:
            P = prep(s)
        except Exception:
            continue
        if P is None:
            continue
        for name, (sig, side, tgt, exs) in setups(P).items():
            sig = np.nan_to_num(sig.astype(float)).astype(bool)
            for sp in (0.0, 0.01, 0.015, 0.02):
                ei, rt = sim(P["o"], P["h"], P["l"], P["c"], P["day"], P["sq"], sig, side, np.asarray(tgt, float), exs, sp)
                if len(ei):
                    acc.setdefault((name, sp), []).append(np.c_[P["time"][ei].astype("datetime64[D]").astype(np.int64), rt])
        if i % 50 == 0:
            print(i, s, flush=True)
    rows = []
    for (name, sp), parts in acc.items():
        X = np.vstack(parts); t = pd.to_datetime(X[:, 0].astype("int64"), unit="D"); rt = X[:, 1]
        a, b = rt[t < SPLIT], rt[t >= SPLIT]
        rows.append(dict(setup=name, stop=f"{sp * 100:g} %" if sp else "none", trades=len(rt), per_day=round(len(rt) / max(len(np.unique(X[:, 0])), 1), 1),
                         win=round(100 * float((rt > 0).mean()), 1), avg_pct=round(100 * float(rt.mean()), 3), p5_pct=round(100 * float(np.percentile(rt, 5)), 2),
                         H1_n=len(a), H1_win=round(100 * float((a > 0).mean()), 1), H1_avg=round(100 * float(a.mean()), 3),
                         H2_n=len(b), H2_win=round(100 * float((b > 0).mean()), 1), H2_avg=round(100 * float(b.mean()), 3)))
    L = pd.DataFrame(rows).sort_values(["setup", "stop"]); OUT.mkdir(exist_ok=True); L.to_csv(OUT / "intraday_hiwin.csv", index=False)
    pd.set_option("display.width", 250); print(L.to_string(index=False))


if __name__ == "__main__":
    main()

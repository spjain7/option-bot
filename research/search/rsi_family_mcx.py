"""RSIFAM-001 (4-Nov-2026, registered before running) – the owner's RSI 75/25 strategy family, six distinct hypotheses,
each with FIXED rules (no parameter search), MCX 7 commodities, 1-hour candles, roll-adjusted front month Jul-2022 -> Oct-2026.

Disclosure: RSI-75/25 reversal ideas were already examined on this data (RSIREV-001, RSIPAT-001), so 2025-26 is NOT an
untouched period for hypotheses A/D/F. Rules below were written before this run and are not tuned on its output.

Common: RSI14 (Wilder), ATR14, EMA50/200, ADX14. Entry = next candle's open after the trigger candle closes.
Exit plan (same for all): half at T1, stop moves to entry; other half at T2, at the stop, or at the time stop (close).
A candle touching stop and target counts as stop (stop first). Costs 0.04 % of price per round trip, taken off in R.
Contract-switch / data-hole candles end the trade at the previous close.

A  range MR       ADX < 20; RSI touched >= 75 in the last 3 candles; trigger close < previous low. SL = 5-candle high + 0.1 ATR.
                  T1 1R, T2 2R, time 20.  (mirror: <= 25, close > previous high)
B  trend pullback ADX >= 22, c > EMA50 > EMA200; RSI >= 75 within the last 20 candles; RSI fell below 45 since; trigger
                  close > previous high with RSI rising. SL = 5-candle low - 0.1 ATR. T1 1R, T2 2R, time 30. (mirror)
C  sweep reversal high > 20-candle high, close back below it, RSI >= 70 on that candle. SL = its high + 0.1 ATR.
                  T1 1R, T2 2R, time 20. (mirror: low sweep, RSI <= 30)
D  divergence     confirmed swing highs (3 candles each side, known only 3 candles later): newer pivot higher, its RSI lower,
                  older pivot RSI >= 70; trigger on the confirmation candle if it closes below the pivot candle's low.
                  SL = newer pivot high + 0.1 ATR. T1 1R, T2 2R, time 30. (mirror)
E  compression BO ATR14 below 0.8 x its 100-candle median on each of the last 5 candles; close beyond the 20-candle high/low;
                  volume >= 1.5 x 20-candle average (contracts with no volume are skipped); RSI >= 60 (<= 40).
                  SL = 1.5 ATR. T1 1R, T2 2R, time 30.
F  small target   A without the ADX filter, T1 0.5R, T2 1R, time 10.
Baseline: random candles, both sides, SL 1.5 ATR, T1 1R, T2 2R, time 20 (same exit plan).
Report: T1 / T2 / stop hit rates, final profitable rate, avg win R, avg loss R, expectancy R, PF, max DD (R), longest
losing streak, avg bars held, by period (2022-24 / 2025-26), side and commodity.

  python -m research.search.rsi_family_mcx   -> research/search/results_rsifam/*
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_rsifam"
COST_PCT = 0.04
SPLIT = pd.Timestamp("2025-01-01")


def rma(x, n):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def ind(df):
    o, h, l, c, v = (df[k].astype(float) for k in ("open", "high", "low", "close", "volume"))
    d = c.diff()
    rsi = 100 - 100 / (1 + rma(d.clip(lower=0), 14) / rma((-d).clip(lower=0), 14).replace(0, np.nan))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = rma(tr, 14)
    up, dn = h.diff(), -l.diff()
    pdm = rma(pd.Series(np.where((up > dn) & (up > 0), up, 0.0)), 14); mdm = rma(pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0)), 14)
    pdi, mdi = 100 * pdm / atr.values, 100 * mdm / atr.values
    adx = rma(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
    e50, e200 = c.ewm(span=50, adjust=False).mean(), c.ewm(span=200, adjust=False).mean()
    return dict(o=o.values, h=h.values, l=l.values, c=c.values, v=v.values, rsi=rsi.values, atr=atr.values, adx=adx.values,
                e50=e50.values, e200=e200.values, atrmed=atr.rolling(100, min_periods=50).median().values,
                vavg=v.rolling(20).mean().shift(1).values, hh20=h.rolling(20).max().shift(1).values,
                ll20=l.rolling(20).min().shift(1).values, hh5=h.rolling(5).max().values, ll5=l.rolling(5).min().values)


def signals(X, n):
    """-> list of (i, side, stop, t1R, t2R, maxbars, family). Everything known at the close of candle i."""
    out = []
    r, a, adx, c, h, l = X["rsi"], X["atr"], X["adx"], X["c"], X["h"], X["l"]
    for i in range(260, n - 1):
        if not np.isfinite(a[i]) or a[i] <= 0 or not np.isfinite(r[i]):
            continue
        r3max, r3min = np.nanmax(r[i - 2:i + 1]), np.nanmin(r[i - 2:i + 1])
        # A / F
        if r3max >= 75 and c[i] < l[i - 1]:
            st = X["hh5"][i] + 0.1 * a[i]
            if adx[i] < 20:
                out.append((i, -1, st, 1.0, 2.0, 20, "A range MR"))
            out.append((i, -1, st, 0.5, 1.0, 10, "F small target"))
        if r3min <= 25 and c[i] > h[i - 1]:
            st = X["ll5"][i] - 0.1 * a[i]
            if adx[i] < 20:
                out.append((i, 1, st, 1.0, 2.0, 20, "A range MR"))
            out.append((i, 1, st, 0.5, 1.0, 10, "F small target"))
        # B
        w = r[i - 19:i + 1]
        if adx[i] >= 22 and c[i] > X["e50"][i] > X["e200"][i] and np.nanmax(w) >= 75:
            k = int(np.nanargmax(w))
            if np.nanmin(w[k:]) < 45 and c[i] > h[i - 1] and r[i] > r[i - 1]:
                out.append((i, 1, X["ll5"][i] - 0.1 * a[i], 1.0, 2.0, 30, "B trend pullback"))
        if adx[i] >= 22 and c[i] < X["e50"][i] < X["e200"][i] and np.nanmin(w) <= 25:
            k = int(np.nanargmin(w))
            if np.nanmax(w[k:]) > 55 and c[i] < l[i - 1] and r[i] < r[i - 1]:
                out.append((i, -1, X["hh5"][i] + 0.1 * a[i], 1.0, 2.0, 30, "B trend pullback"))
        # C
        if h[i] > X["hh20"][i] and c[i] < X["hh20"][i] and r[i] >= 70:
            out.append((i, -1, h[i] + 0.1 * a[i], 1.0, 2.0, 20, "C sweep reversal"))
        if l[i] < X["ll20"][i] and c[i] > X["ll20"][i] and r[i] <= 30:
            out.append((i, 1, l[i] - 0.1 * a[i], 1.0, 2.0, 20, "C sweep reversal"))
        # E
        med = X["atrmed"][i - 4:i + 1]
        if np.all(np.isfinite(med)) and np.all(a[i - 4:i + 1] < 0.8 * med) and np.isfinite(X["vavg"][i]) and X["vavg"][i] > 0 \
                and X["v"][i] >= 1.5 * X["vavg"][i]:
            if c[i] > X["hh20"][i] and r[i] >= 60:
                out.append((i, 1, c[i] - 1.5 * a[i], 1.0, 2.0, 30, "E compression BO"))
            if c[i] < X["ll20"][i] and r[i] <= 40:
                out.append((i, -1, c[i] + 1.5 * a[i], 1.0, 2.0, 30, "E compression BO"))
    # D – confirmed pivots: pivot at p is known at p+3
    k = 3
    piv_h, piv_l = [], []
    for i in range(260 + 2 * k, n - 1):
        p = i - k
        if h[p] == max(h[p - k:p + k + 1]) and h[p] > max(h[p - k:p]):
            if piv_h and h[p] > h[piv_h[-1]] and r[p] < r[piv_h[-1]] and r[piv_h[-1]] >= 70 and c[i] < l[p]:
                out.append((i, -1, h[p] + 0.1 * X["atr"][i], 1.0, 2.0, 30, "D divergence"))
            piv_h.append(p)
        if l[p] == min(l[p - k:p + k + 1]) and l[p] < min(l[p - k:p]):
            if piv_l and l[p] < l[piv_l[-1]] and r[p] > r[piv_l[-1]] and r[piv_l[-1]] <= 30 and c[i] > h[p]:
                out.append((i, 1, l[p] - 0.1 * X["atr"][i], 1.0, 2.0, 30, "D divergence"))
            piv_l.append(p)
    return out


def trade(X, sw, i, s, stop, t1r, t2r, maxb):
    o, h, l, c = X["o"], X["h"], X["l"], X["c"]
    n = len(c)
    e = o[i + 1]
    R = s * (e - stop)
    if not np.isfinite(R) or R <= 0 or R > 6 * X["atr"][i]:
        return None
    cost = COST_PCT / 100 * e / R
    t1, t2 = e + s * t1r * R, e + s * t2r * R
    half1 = None; st = stop; res = dict(t1=False, t2=False, stop=False, bars=0)
    for j in range(i + 1, min(i + 1 + maxb, n)):
        if sw[j] and j > i + 1:
            x = c[j - 1]; break
        hit_s = (l[j] <= st) if s > 0 else (h[j] >= st)
        if hit_s:
            px = (o[j] if ((s > 0 and o[j] < st) or (s < 0 and o[j] > st)) else st)
            if half1 is None:
                res.update(stop=True, bars=j - i)
                return dict(res, R=s * (px - e) / R - cost)
            res.update(bars=j - i, stop=st != e)   # breakeven stop after T1 is not a "stop hit"
            return dict(res, R=0.5 * half1 + 0.5 * s * (px - e) / R - cost)
        if half1 is None and ((h[j] >= t1) if s > 0 else (l[j] <= t1)):
            half1 = t1r; res["t1"] = True; st = e
        if half1 is not None and ((h[j] >= t2) if s > 0 else (l[j] <= t2)):
            res.update(t2=True, bars=j - i)
            return dict(res, R=0.5 * half1 + 0.5 * t2r - cost)
        x = c[j]
    res["bars"] = min(maxb, n - 1 - i)
    last = 0.5 * half1 + 0.5 * s * (x - e) / R if half1 is not None else s * (x - e) / R
    return dict(res, R=last - cost)


def summary(g):
    r = g.R.values
    if len(r) == 0:
        return pd.Series(dtype=float)
    eq = np.cumsum(r); dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0
    streak = best = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0; best = max(best, streak)
    win, loss = r[r > 0], r[r <= 0]
    return pd.Series(dict(n=len(r), t1_hit=g.t1.mean(), t2_hit=g.t2.mean(), stop_hit=g.stop.mean(), profitable=(r > 0).mean(),
                          avg_win=win.mean() if len(win) else np.nan, avg_loss=loss.mean() if len(loss) else np.nan,
                          exp_R=r.mean(), pf=win.sum() / -loss.sum() if loss.sum() < 0 else np.nan, max_dd_R=dd,
                          max_loss_streak=best, avg_bars=g.bars.mean())).round(3)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    rng = np.random.default_rng(11)
    for seg, tf, name, df in H.datasets():
        if seg == "STK":
            break
        if seg != "MCX" or tf != "1h":
            continue
        df = df.reset_index(drop=True)
        X = ind(df); sw = df["switch"].values.astype(bool); n = len(df)
        busy = {}
        for i, s, st, t1r, t2r, mb, fam in sorted(signals(X, n), key=lambda x: x[0]):
            if busy.get((fam, s), -1) >= i:
                continue                                   # one open trade per family / side / commodity
            t = trade(X, sw, i, s, st, t1r, t2r, mb)
            if t is None:
                continue
            busy[(fam, s)] = i + t["bars"]
            rows.append(dict(name=name, family=fam, side="BUY" if s > 0 else "SELL", time=df["time"].iat[i], **t))
        for i in rng.choice(np.arange(260, n - 31), size=min(600, n // 20), replace=False):
            s = 1 if rng.random() < 0.5 else -1
            t = trade(X, sw, i, s, X["c"][i] - s * 1.5 * X["atr"][i], 1.0, 2.0, 20)
            if t:
                rows.append(dict(name=name, family="Z random baseline", side="BUY" if s > 0 else "SELL", time=df["time"].iat[i], **t))
        print(name, "done", flush=True)
    T = pd.DataFrame(rows).sort_values("time")
    T["period"] = np.where(T.time < SPLIT, "2022-24", "2025-26")
    T.to_csv(OUT / "trades.csv.gz", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    A = T.groupby(["family", "period"]).apply(summary)
    B = T.groupby(["family", "side", "period"]).apply(summary)
    C = T[T.period == "2025-26"].groupby(["family", "name"]).apply(summary)
    A.to_csv(OUT / "by_family.csv"); B.to_csv(OUT / "by_family_side.csv"); C.to_csv(OUT / "by_family_name_2025_26.csv")
    print(A.to_string()); print(B.to_string())


if __name__ == "__main__":
    main()

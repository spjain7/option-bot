"""STRAT-SEARCH-004 – volume & other indicator families (pre-registered in the docstring; research only).
Entries (signal on a closed candle; long version shown, short is the mirror):
  VOLUME : vol_breakout   close > 20-candle high AND volume > 1.5× its 20-candle average
           obv_breakout   OBV at a 20-candle high AND close > EMA50
           mfi_rev        MFI(14) crosses up through 20 while close > EMA200
           cmf_trend      CMF(20) crosses above +0.10 while close > EMA50
           vwap_cross     (1h only) close crosses above the session VWAP, daily trend up
           vol_climax     volume > 3× average + candle closes in its top third after a down move (reversal)
  OTHER  : stoch_trend    Stochastic %K(14,3) crosses up through 20 while close > EMA200
           cci_trend      CCI(20) crosses up through −100 while close > EMA200
           keltner_bo     close > EMA20 + 2×ATR(10)
           squeeze_bo     Bollinger(20,2) was inside Keltner(20,1.5) and close breaks above the upper Bollinger band
           ichimoku       Tenkan crosses above Kijun with close above the cloud
           psar_flip      Parabolic SAR(0.02, 0.2) flips below price
           ha_trend       3 green Heikin-Ashi candles with no lower wick after a red one
           nr7_bo         close breaks the high of the most recent NR7 candle (narrowest range of 7)
Filters: none | daily trend agrees (previous day close vs daily EMA50).
Exits: "fixed" target 1.5 ATR / stop 1.5 ATR (win rate = pure signal quality) | "trail" stop 2 ATR, 3-ATR trailing.
Timeframes 1h, 3h, 1d. Fills, costs, roll handling and max hold (40) as STRAT-SEARCH-002.
QUALIFY = ≥ 40 trades in each half (before / after Jul-2024), expectancy > 0 at 2× costs in BOTH halves.
"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from crude import indicators as I  # noqa
from research.search import strategy_search as SS, combo_search as C  # noqa
from alerts import stats as ST  # noqa

ENT = ["vol_breakout", "obv_breakout", "mfi_rev", "cmf_trend", "vwap_cross", "vol_climax", "stoch_trend", "cci_trend",
       "keltner_bo", "squeeze_bo", "ichimoku", "psar_flip", "ha_trend", "nr7_bo"]


def cross_up(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_dn(a, b):
    return (a < b) & (a.shift(1) >= b.shift(1))


def psar(df, af0=0.02, mx=0.2):
    h, l = df["high"].values, df["low"].values
    n = len(h); tr = np.ones(n); sar = np.zeros(n)
    sar[0], ep, af, up = l[0], h[0], af0, True
    for i in range(1, n):
        sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
        if up:
            sar[i] = min(sar[i], l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar[i]:
                up, sar[i], ep, af = False, ep, l[i], af0
            elif h[i] > ep:
                ep, af = h[i], min(mx, af + af0)
        else:
            sar[i] = max(sar[i], h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar[i]:
                up, sar[i], ep, af = True, ep, h[i], af0
            elif l[i] < ep:
                ep, af = l[i], min(mx, af + af0)
        tr[i] = 1 if up else -1
    return pd.Series(tr, index=df.index)


def signals(df, f):
    c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"].astype(float)
    e50, e200, e20 = I.ema(c, 50), I.ema(c, 200), I.ema(c, 20)
    a10 = I.atr(df, 10)
    va = v.rolling(20).mean().shift(1)
    S = {}
    hh, ll = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    S["vol_breakout"] = np.where((c > hh) & (v > 1.5 * va), 1, np.where((c < ll) & (v > 1.5 * va), -1, 0))
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    S["obv_breakout"] = np.where((obv >= obv.rolling(20).max()) & (c > e50), 1, np.where((obv <= obv.rolling(20).min()) & (c < e50), -1, 0))
    tp = (h + l + c) / 3; mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0).rolling(14).sum(); neg = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    mfi = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    S["mfi_rev"] = np.where(cross_up(mfi, pd.Series(20, index=c.index)) & (c > e200), 1,
                            np.where(cross_dn(mfi, pd.Series(80, index=c.index)) & (c < e200), -1, 0))
    mfm = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    cmf = (mfm * v).rolling(20).sum() / v.rolling(20).sum()
    S["cmf_trend"] = np.where(cross_up(cmf, pd.Series(0.1, index=c.index)) & (c > e50), 1,
                              np.where(cross_dn(cmf, pd.Series(-0.1, index=c.index)) & (c < e50), -1, 0))
    day = df["time"].dt.normalize()
    vw = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum().replace(0, np.nan)
    S["vwap_cross"] = np.where(cross_up(c, vw) & (f["dtr"] == 1), 1, np.where(cross_dn(c, vw) & (f["dtr"] == -1), -1, 0))
    pos3 = (c - l) / (h - l).replace(0, np.nan)
    S["vol_climax"] = np.where((v > 3 * va) & (pos3 > 0.67) & (c.shift(1) < c.shift(6)), 1,
                               np.where((v > 3 * va) & (pos3 < 0.33) & (c.shift(1) > c.shift(6)), -1, 0))
    k = 100 * (c - l.rolling(14).min()) / (h.rolling(14).max() - l.rolling(14).min()).replace(0, np.nan)
    k = k.rolling(3).mean()
    S["stoch_trend"] = np.where(cross_up(k, pd.Series(20, index=c.index)) & (c > e200), 1,
                                np.where(cross_dn(k, pd.Series(80, index=c.index)) & (c < e200), -1, 0))
    cci = (tp - tp.rolling(20).mean()) / (0.015 * (tp - tp.rolling(20).mean()).abs().rolling(20).mean())
    S["cci_trend"] = np.where(cross_up(cci, pd.Series(-100, index=c.index)) & (c > e200), 1,
                              np.where(cross_dn(cci, pd.Series(100, index=c.index)) & (c < e200), -1, 0))
    S["keltner_bo"] = np.where(cross_up(c, e20 + 2 * a10), 1, np.where(cross_dn(c, e20 - 2 * a10), -1, 0))
    m, sd = c.rolling(20).mean(), c.rolling(20).std()
    sq = ((m + 2 * sd) < (e20 + 1.5 * a10)) & ((m - 2 * sd) > (e20 - 1.5 * a10))
    S["squeeze_bo"] = np.where(sq.shift(1).fillna(False).astype(bool) & (c > m + 2 * sd), 1,
                               np.where(sq.shift(1).fillna(False).astype(bool) & (c < m - 2 * sd), -1, 0))
    ten = (h.rolling(9).max() + l.rolling(9).min()) / 2; kij = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa = ((ten + kij) / 2).shift(26); sb = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    top, bot = np.maximum(sa, sb), np.minimum(sa, sb)
    S["ichimoku"] = np.where(cross_up(ten, kij) & (c > top), 1, np.where(cross_dn(ten, kij) & (c < bot), -1, 0))
    ps = psar(df)
    S["psar_flip"] = np.where((ps == 1) & (ps.shift(1) == -1), 1, np.where((ps == -1) & (ps.shift(1) == 1), -1, 0))
    hc = (o + h + l + c) / 4
    ho = hc.copy(); ho.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2
    hov = ho.to_numpy(copy=True); hcv = hc.to_numpy()
    for i in range(1, len(hov)):
        hov[i] = (hov[i - 1] + hcv[i - 1]) / 2
    ho = pd.Series(hov, index=c.index)
    hl = np.minimum(l, np.minimum(ho, hc)); hh_ = np.maximum(h, np.maximum(ho, hc))
    g = (hc > ho) & (np.minimum(ho, hc) <= hl + 1e-9)          # green, no lower wick
    r = (hc < ho) & (np.maximum(ho, hc) >= hh_ - 1e-9)         # red, no upper wick
    S["ha_trend"] = np.where(g & g.shift(1, fill_value=False) & g.shift(2, fill_value=False) & (hc.shift(3) < ho.shift(3)), 1,
                             np.where(r & r.shift(1, fill_value=False) & r.shift(2, fill_value=False) & (hc.shift(3) > ho.shift(3)), -1, 0))
    rng = h - l
    nr7 = rng <= rng.rolling(7).min()
    nh = h.where(nr7).ffill().shift(1); nl = l.where(nr7).ffill().shift(1)
    recent = nr7.shift(1).rolling(3).max().fillna(0).astype(bool)
    S["nr7_bo"] = np.where(recent & cross_up(c, nh), 1, np.where(recent & cross_dn(c, nl), -1, 0))
    return {k: np.asarray(v_, dtype=float) for k, v_ in S.items()}


def run(f, sig, swd, nx, flt, ex, cost):
    o, h, l, c, a = f["o"], f["h"], f["l"], f["c"], f["atr"]
    out, pos = [], None
    for i in range(210, len(c) - 1):
        if pos is not None:
            s, e0, st, tp, risk, k0, best = pos
            px = None
            if (o[i] <= st) if s > 0 else (o[i] >= st):
                px = o[i]
            elif (l[i] <= st) if s > 0 else (h[i] >= st):
                px = st
            elif tp is not None and ((h[i] >= tp) if s > 0 else (l[i] <= tp)):
                px = tp
            elif nx[i] or i - k0 >= 40:
                px = c[i] if nx[i] else o[i + 1]
            if px is not None:
                out.append((f["t"][k0], s * (px - e0), cost[k0], risk))
                pos = None
            else:
                if ex == "trail":
                    best = max(best, c[i]) if s > 0 else min(best, c[i])
                    ns = best - s * 3 * a[i]
                    if s * (ns - st) > 0:
                        st = ns
                pos = (s, e0, st, tp, risk, k0, best)
            continue
        s = int(sig[i]) if np.isfinite(sig[i]) else 0
        if s == 0 or swd[i] or nx[i] or not a[i] > 0 or (flt == "daily" and f["dtr"][i] != s):
            continue
        e0 = o[i + 1]
        if ex == "fixed":
            pos = (s, e0, e0 - s * 1.5 * a[i], e0 + s * 1.5 * a[i], 1.5 * a[i], i + 1, e0)
        else:
            pos = (s, e0, e0 - s * 2 * a[i], None, 2 * a[i], i + 1, e0)
    return out


def main():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR")
        sw = SS.switch_days(name, exch, h)
        for tf, df in (("1h", h), ("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True)
            f = C.features(df, h)
            sigs = signals(df, f)
            day = f["day"]; swd = np.array([pd.Timestamp(x) in sw for x in day])
            nx = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in f["c"]])
            for e, flt, ex in itertools.product(ENT, ["none", "daily"], ["fixed", "trail"]):
                if e == "vwap_cross" and tf != "1h":
                    continue
                for t0, g, cp, risk in run(f, sigs[e], swd, nx, flt, ex, cost):
                    rows.append((name, tf, e, flt, ex, t0, g, cp, risk))
        print(name, "done", flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "entry", "filter", "exit", "time", "gross", "cost", "risk"])
    T["time"] = pd.to_datetime(T["time"])
    T["r1"] = (T["gross"] - T["cost"]) / T["risk"]; T["r2"] = (T["gross"] - 2 * T["cost"]) / T["risk"]
    T["win"] = (T["gross"] - T["cost"]) > 0
    T["half"] = np.where(T["time"] < pd.Timestamp("2024-07-01"), "A", "B")
    T["combo"] = T["tf"] + "|" + T["entry"] + "|" + T["filter"] + "|" + T["exit"]
    g = T.groupby(["combo", "half"]).agg(n=("r1", "size"), win=("win", "mean"), e1=("r1", "mean"), e2=("r2", "mean")).unstack()
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    g = g.dropna()
    big = g[(g["n_A"] >= 40) & (g["n_B"] >= 40)].copy()
    big["win_all"] = T.groupby("combo")["win"].mean().reindex(big.index)
    q = big[(big["e2_A"] > 0) & (big["e2_B"] > 0)].copy()
    q["worst_e2"] = q[["e2_A", "e2_B"]].min(axis=1)
    out = ROOT / "research/search/results_004"; out.mkdir(parents=True, exist_ok=True)
    big.round(3).to_csv(out / "combos.csv")
    cols = ["n_A", "n_B", "win_A", "win_B", "e1_A", "e1_B", "e2_A", "e2_B"]
    print(f"\neligible combos: {len(big)} · profitable at 2× costs in BOTH halves: {len(q)}")
    print(q.sort_values("worst_e2", ascending=False)[cols].round(3).head(20).to_string())
    print("\nhighest win rates (any profitability):")
    print(big.sort_values("win_all", ascending=False)[cols].round(3).head(10).to_string())
    fam = big.groupby(big.index.str.split("|").str[1]).apply(lambda x: pd.Series(dict(combos=len(x), both_pos_2x=int(((x.e2_A > 0) & (x.e2_B > 0)).sum()),
                                                                                       avg_e1=round(float(((x.e1_A + x.e1_B) / 2).mean()), 3))))
    print("\nby indicator family:\n" + fam.sort_values("avg_e1", ascending=False).to_string())
    (out / "summary.json").write_text(json.dumps(dict(eligible=len(big), qualifying=q.round(3).reset_index().to_dict("records"),
                                                      families=fam.reset_index().to_dict("records")), indent=1, default=str))


if __name__ == "__main__":
    main()

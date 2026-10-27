"""INST-PAT-001 – see REGISTRY_INST.md.  python -m research.search.inst_patterns"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from crude import indicators as I  # noqa
from research.search import strategy_search as SS, combo_search as C  # noqa
from research.search.exit_test import run  # noqa
from alerts import stats as ST  # noqa

K = 3
EXITS = {"3h": (2.0, 3.0, True, True, None), "1d": (1.5, 3.0, False, False, "e20")}


def pivots(h, l):
    n = len(h); ph = np.zeros(n, bool); pl = np.zeros(n, bool)
    for i in range(K, n - K):
        ph[i] = h[i] == h[i - K:i + K + 1].max(); pl[i] = l[i] == l[i - K:i + K + 1].min()
    return ph, pl


def signals(df, f):
    o, h, l, c, a = f["o"], f["h"], f["l"], f["c"], f["atr"]
    v = df["volume"].astype(float).values; va = pd.Series(v).rolling(20).mean().shift(1).values
    n = len(c); ph, pl = pivots(h, l)
    S = {k: np.zeros(n, int) for k in ("double", "hs", "flag", "squeeze", "week", "pivot")}
    lows, highs = [], []                      # confirmed pivots (index) known at time i
    for i in range(30, n):
        j = i - K
        if pl[j]: lows.append(j)
        if ph[j]: highs.append(j)
        if not a[i] > 0: continue
        # P1 double bottom / top
        if len(lows) >= 2:
            l1, l2 = lows[-2], lows[-1]
            hb = [x for x in highs if l1 < x < l2]
            if hb and l2 - l1 >= 5 and abs(l[l1] - l[l2]) <= 0.5 * a[i] and i - l2 <= 30:
                neck = max(h[x] for x in hb)
                if c[i] > neck >= c[i - 1]: S["double"][i] = 1
        if len(highs) >= 2:
            h1, h2 = highs[-2], highs[-1]
            lb = [x for x in lows if h1 < x < h2]
            if lb and h2 - h1 >= 5 and abs(h[h1] - h[h2]) <= 0.5 * a[i] and i - h2 <= 30:
                neck = min(l[x] for x in lb)
                if c[i] < neck <= c[i - 1]: S["double"][i] = -1
        # P2 inverse head & shoulders / head & shoulders
        if len(lows) >= 3:
            a1, b1, c1 = lows[-3], lows[-2], lows[-1]
            if l[b1] < l[a1] and l[b1] < l[c1] and abs(l[a1] - l[c1]) <= a[i] and i - c1 <= 30:
                hb = [x for x in highs if a1 < x < c1]
                if hb:
                    neck = max(h[x] for x in hb)
                    if c[i] > neck >= c[i - 1]: S["hs"][i] = 1
        if len(highs) >= 3:
            a1, b1, c1 = highs[-3], highs[-2], highs[-1]
            if h[b1] > h[a1] and h[b1] > h[c1] and abs(h[a1] - h[c1]) <= a[i] and i - c1 <= 30:
                lb = [x for x in lows if a1 < x < c1]
                if lb:
                    neck = min(l[x] for x in lb)
                    if c[i] < neck <= c[i - 1]: S["hs"][i] = -1
        # P3 flag
        for m in range(3, 9):
            s0 = i - m                              # pause = candles s0..i-1, impulse ends at s0-1
            if s0 - 6 < 0: break
            imp = c[s0 - 1] - c[s0 - 6]
            ph_hi, ph_lo = h[s0:i].max(), l[s0:i].min()
            if ph_hi - ph_lo > 1.5 * a[i]: continue
            if imp >= 3 * a[i] and ph_lo > c[s0 - 6] + imp / 2 and c[i] > ph_hi: S["flag"][i] = 1; break
            if imp <= -3 * a[i] and ph_hi < c[s0 - 6] + imp / 2 and c[i] < ph_lo: S["flag"][i] = -1; break
        # P4 squeeze breakout
        hh, ll = h[i - 10:i].max(), l[i - 10:i].min()
        if hh - ll <= 2.5 * a[i] and v[i] > 1.5 * va[i]:
            S["squeeze"][i] = 1 if c[i] > hh else -1 if c[i] < ll else 0
    return S


def add_daily_levels(df, f, S):
    d = df.copy(); d["wk"] = d["time"].dt.to_period("W")
    w = d.groupby("wk").agg(hi=("high", "max"), lo=("low", "min"))
    pwh = d["wk"].map(w["hi"].shift(1)).values; pwl = d["wk"].map(w["lo"].shift(1)).values
    v = d["volume"].astype(float).values; va = pd.Series(v).rolling(20).mean().shift(1).values
    c, h, l = f["c"], f["h"], f["l"]
    pp = (np.r_[np.nan, h[:-1]] + np.r_[np.nan, l[:-1]] + np.r_[np.nan, c[:-1]]) / 3
    r1, s1 = 2 * pp - np.r_[np.nan, l[:-1]], 2 * pp - np.r_[np.nan, h[:-1]]
    with np.errstate(invalid="ignore"):
        S["week"] = np.where((c > pwh) & (np.r_[np.nan, c[:-1]] <= pwh) & (v > 1.5 * va), 1,
                             np.where((c < pwl) & (np.r_[np.nan, c[:-1]] >= pwl) & (v > 1.5 * va), -1, 0))
        S["pivot"] = np.where((l <= s1) & (c > s1), 1, np.where((h >= r1) & (c < r1), -1, 0))


def main():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR"); sw = SS.switch_days(name, exch, h)
        mult = INS.REGISTRY[name]["mult"]
        for tf, df in (("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True); f = C.features(df, h)
            c, hi, lo, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
            day = f["day"]; swd = np.array([pd.Timestamp(x) in sw for x in day]); nx = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in f["c"]])
            e20 = I.ema(c, 20).values; f["e20"] = f["e20_s"] = e20
            S = signals(df, f)
            if tf == "1d": add_daily_levels(df, f, S)
            else: S.pop("week"); S["pivot"] = np.zeros(len(c), int)
            if tf == "3h": S.pop("pivot")
            va = v.rolling(20).mean().shift(1)
            bo = np.where((c > hi.shift(1).rolling(20).max()) & (v > 1.5 * va) & (c > f["e200"]), 1,
                          np.where((c < lo.shift(1).rolling(20).min()) & (v > 1.5 * va) & (c < f["e200"]), -1, 0))
            pat = np.zeros(len(c), int)
            for k in ("double", "hs", "flag", "squeeze"):
                x = pd.Series(S[k]).replace(0, np.nan).ffill(limit=10).fillna(0).values
                pat = np.where(pat == 0, x, pat)
            rules = {}
            for k, sg in S.items():
                rules[k] = sg
                rules[k + "+ema200"] = np.where(sg * np.sign(f["c"] - f["e200"]) > 0, sg, 0)
            rules["LIVE_breakout"] = bo
            rules["breakout+pattern"] = np.where(bo * pat > 0, bo, 0)
            sk, tk, be, half, tx = EXITS[tf]
            for rn, sg in rules.items():
                for t0, g, cp, r in run(f, sg, swd, nx, sk, tk, be, half, cost, tx):
                    rows.append((name, tf, rn, t0, (g - cp) * mult, (g - 2 * cp) * mult))
        print(name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "rule", "time", "rs", "rs2"])
    T["per"] = np.where(pd.to_datetime(T.time) < pd.Timestamp("2024-07-01"), "design", "holdout")
    out = []
    for (tf, rn), g in T.groupby(["tf", "rule"]):
        D, H = g[g.per == "design"], g[g.per == "holdout"]
        pos = int((H.groupby("name").rs.mean() > 0).sum())
        ok = len(D) >= 40 and len(H) >= 40 and D.rs2.mean() > 0 and H.rs2.mean() > 0 and pos >= 6
        out.append(dict(tf=tf, rule=rn, n_d=len(D), win_d=round((D.rs > 0).mean() * 100, 1), rs2_d=round(D.rs2.mean()),
                        n_h=len(H), win_h=round((H.rs > 0).mean() * 100, 1), rs2_h=round(H.rs2.mean()), inst_pos_h=f"{pos}/9",
                        PASS=ok))
    R = pd.DataFrame(out).sort_values(["tf", "PASS", "rs2_h"], ascending=[True, False, False])
    d = ROOT / "research/search/results_inst"; d.mkdir(parents=True, exist_ok=True); R.to_csv(d / "summary.csv", index=False)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()

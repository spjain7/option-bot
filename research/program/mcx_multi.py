"""MCX-MULTI-001 (29-Oct-2026, owner: "commodities moved a lot and no trade – trial and error: RSI reversal with volume (+OI),
chart patterns, intraday 15-min calls, positional / higher timeframe, add ADX / ADR if needed").

Data: Angel MCX futures 1h Jul-2022 → Oct-2026 (CRUDEOIL, NATURALGAS, GOLD, SILVER, COPPER, ZINC, ALUMINIUM) -> 1h / 3h / 1d;
15-min Aug→Oct-2026 for COPPER / CRUDEOIL / NATURALGAS / SILVER (2 months – sanity check only).
OI: Angel serves NO MCX OI history (AB1012), so OI rules cannot be backtested – live / forward only.

Signal families (side-aware, known at the signal close):
  RSI30/25/35   RSI(14) crosses back above 30 (25/35) after being below (BUY); below 70 (75/65) after above (SELL)
  RSIDIV        price makes a new 20-bar low but RSI is higher than at the previous 20-bar low, RSI < 40 (bullish div.); mirror
  ENGULF        bullish / bearish engulfing at a 20-bar low / high
  PIN           hammer (BUY) / shooting star (SELL) at a 20-bar low / high
  DBL           double bottom / top: two pivot lows (highs) within 0.3 ATR, 5–40 bars apart, close breaks the neckline
  NR7           narrowest range of 7 bars, then a close beyond its high / low
  ORB           (intraday 1h / 15m) close beyond the first hour's high / low of the MCX session
  ADRGO         (intraday) price already ≥ 0.6 × ADR(14) from the day's open in the trade direction at the bar close (momentum)
Filters (all combinations): volume any / ≥1.5× / ≥2× · ADX any / <20 / <25 / ≥25 · trend any / with EMA200 / against ·
  ADR used (intraday) any / ≥0.8 / ≤0.8
Exits: P1 = stop beyond the signal bar (±0.1 ATR) · 1R · P2 = same stop · 2R · A15 = 1.5 ATR stop · 1.5R.
  Intraday timeframes (15m, 1h) exit at the session's last bar the same day; 3h max 20 bars; daily max 10 bars.
Execution: next-bar open, 0.5-ATR chase rule, stop first in a bar, gaps fill at the open, roll exit, stop cap (2.5 % intraday / 3h,
4 % daily), 2× costs, one trade at a time. Splits: train < 2024-07 ≤ valid < 2025-07 ≤ test (1h/3h/1d).
Selection: POOLED across the 7 commodities (more trades) – train AND valid exp2 > 0, n ≥ 40 / 25, BH-FDR 10 %; per-commodity results
reported for the pooled survivors and for each commodity's own best (exploratory).
python research/program/mcx_multi.py"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, bo1h_grid as G  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
CAP = {"15m": 2.5, "1h": 2.5, "3h": 2.5, "1d": 4.0}
MAXB = {"3h": 20, "1d": 10}
INTRA = ("15m", "1h")


def pivots(x, k=2):
    """Boolean pivot low (x smaller than k bars each side) – confirmed k bars later (shifted to the confirm bar)."""
    v = x.values; n = len(v); out = np.zeros(n, bool)
    for i in range(k, n - k):
        if v[i] == v[i - k:i + k + 1].min():
            out[i] = True
    return out


def signals(f, tf):
    c, o, h, l = (f[x].values.astype(float) for x in ("close", "open", "high", "low"))
    a = f["atr"].values
    rsi = I.rsi(f["close"], 14).values
    n = len(c)
    S = {}
    for lv in (25, 30, 35):
        up = (rsi > lv) & (np.r_[np.nan, rsi[:-1]] <= lv)
        dn = (rsi < 100 - lv) & (np.r_[np.nan, rsi[:-1]] >= 100 - lv)
        S[f"RSI{lv}"] = (up, dn)
    lo20 = f["low"].rolling(20).min().values; hi20 = f["high"].rolling(20).max().values
    lo20p = np.r_[np.nan, lo20[:-1]]; hi20p = np.r_[np.nan, hi20[:-1]]
    # divergence: new 20-bar low now; previous such low within 5-40 bars had lower RSI? -> bullish if RSI now > RSI then
    bdiv = np.zeros(n, bool); sdiv = np.zeros(n, bool)
    last_lo = last_hi = None
    for i in range(20, n):
        if l[i] <= lo20p[i]:
            if last_lo is not None and 5 <= i - last_lo <= 40 and rsi[i] > rsi[last_lo] and rsi[i] < 40 and c[i] > o[i]:
                bdiv[i] = True
            last_lo = i
        if h[i] >= hi20p[i]:
            if last_hi is not None and 5 <= i - last_hi <= 40 and rsi[i] < rsi[last_hi] and rsi[i] > 60 and c[i] < o[i]:
                sdiv[i] = True
            last_hi = i
    S["RSIDIV"] = (bdiv, sdiv)
    po, pc = np.r_[np.nan, o[:-1]], np.r_[np.nan, c[:-1]]
    at_lo = l <= lo20 + 0.25 * a; at_hi = h >= hi20 - 0.25 * a
    beng = (pc < po) & (c > o) & (c >= po) & (o <= pc) & at_lo
    seng = (pc > po) & (c < o) & (c <= po) & (o >= pc) & at_hi
    S["ENGULF"] = (beng, seng)
    rng = np.where(h - l > 0, h - l, np.nan); body = np.abs(c - o)
    lw = np.minimum(o, c) - l; uw = h - np.maximum(o, c)
    S["PIN"] = ((lw >= 2 * body) & (uw <= 0.3 * rng) & at_lo, (uw >= 2 * body) & (lw <= 0.3 * rng) & at_hi)
    # double bottom / top
    pl, ph = pivots(f["low"]), pivots(-f["high"])
    db = np.zeros(n, bool); dt = np.zeros(n, bool)
    lows = list(np.flatnonzero(pl)); highs = list(np.flatnonzero(ph))
    for arr, out, side in ((lows, db, 1), (highs, dt, -1)):
        for t_, j in enumerate(arr):
            for i0 in arr[max(0, t_ - 4):t_]:
                if not 5 <= j - i0 <= 40:
                    continue
                p0, p1 = (l[i0], l[j]) if side > 0 else (h[i0], h[j])
                if abs(p1 - p0) > 0.3 * a[j]:
                    continue
                neck = h[i0:j + 1].max() if side > 0 else l[i0:j + 1].min()
                for k in range(j + 3, min(j + 15, n)):          # pivot confirmed 2 bars later; break within ~12 bars
                    if (c[k] > neck) if side > 0 else (c[k] < neck):
                        out[k] = True; break
                    if (l[k] < min(p0, p1) - 0.1 * a[j]) if side > 0 else (h[k] > max(p0, p1) + 0.1 * a[j]):
                        break
                break
    S["DBL"] = (db, dt)
    r7 = pd.Series(h - l).rolling(7).min().values
    nr7 = (h - l) <= r7
    nr7p = np.r_[False, nr7[:-1]]
    hp, lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    S["NR7"] = (nr7p & (c > hp), nr7p & (c < lp))
    if tf in INTRA:
        day = f["time"].dt.normalize()
        first = f.groupby(day)["time"].transform("min")
        span = pd.Timedelta(minutes=60)
        in_or = (f["time"] < first + span).values
        orh = f["high"].where(in_or).groupby(day).transform("max").values
        orl = f["low"].where(in_or).groupby(day).transform("min").values
        after = ~in_or
        cprev = np.r_[np.nan, c[:-1]]
        S["ORB"] = (after & (c > orh) & ~(cprev > orh), after & (c < orl) & ~(cprev < orl))
        dopen = f.groupby(day)["open"].transform("first").values
        dd = f.groupby(day).agg(hi=("high", "max"), lo=("low", "min"))
        adr = day.map((dd["hi"] - dd["lo"]).rolling(14).mean().shift(1)).values
        mv = (c - dopen) / adr
        mvp = np.r_[np.nan, mv[:-1]]
        S["ADRGO"] = ((mv >= 0.6) & ~(mvp >= 0.6), (mv <= -0.6) & ~(mvp <= -0.6))
    return S, rsi


def run(job):
    kind, a_, b_ = job
    out = []
    try:
        if kind == "mi":
            fr = [(seg, f, cost) for seg, f, od, cost in EX.frames(job) if seg.startswith("MCX")]
            name = a_
        else:                                                   # 15-min files
            df = pd.read_csv(a_, parse_dates=["time"]).sort_values("time").drop_duplicates("time").reset_index(drop=True)
            df["switch"] = False
            name = b_
            cost = np.array([INS.cost_points(name, p, 1.0) for p in df["close"].values])
            fr = [("MCX 15m", df, cost)]
    except Exception as e:
        print("skip", job[:2], e); return []
    for seg, f0, cost in fr:
        tf = seg.split()[-1]
        if tf not in CAP or len(f0) < 300:
            continue
        f = H.features(f0.reset_index(drop=True)); f["switch"] = f0["switch"].values
        o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values
        e200 = I.ema(f["close"], 200).values
        adx = f["adx"].values
        volx = f["volx"].values
        day = f["time"].dt.normalize()
        last_i = f.groupby(day).cumcount(ascending=False).values == 0          # last bar of the day
        idx = np.arange(len(f))
        day_end = pd.Series(np.where(last_i, idx, np.nan)).bfill().values
        if tf in INTRA:
            dhi, dlo = f.groupby(day)["high"].cummax().values, f.groupby(day)["low"].cummin().values
            dd = f.groupby(day).agg(hi=("high", "max"), lo=("low", "min"))
            adr_i = day.map((dd["hi"] - dd["lo"]).rolling(14).mean().shift(1)).values
        S, rsi = signals(f, tf)
        start = 210 if tf != "15m" else 60
        for typ, (bu, se) in S.items():
            for side, ev in ((1, bu), (-1, se)):
                for i in np.flatnonzero(np.nan_to_num(ev, nan=0).astype(bool)):
                    if i < start or i >= len(c) - 2 or sw[i] or sw[i + 1] or not a[i] > 0:
                        continue
                    if tf in INTRA and last_i[i]:
                        continue                                   # no new intraday trade on the day's last bar
                    if abs(o[i + 1] - c[i]) / a[i] > H.CHASE:
                        continue
                    e0 = o[i + 1]
                    jend = int(day_end[i]) if tf in INTRA else min(len(c) - 1, i + 1 + MAXB[tf])
                    pst = (l[i] - 0.1 * a[i]) if side > 0 else (h[i] + 0.1 * a[i])
                    plans = {"A15": (1.5 * a[i], 1.5)}
                    Rp = side * (e0 - pst)
                    if Rp > 0.2 * a[i]:
                        plans["P1"] = (Rp, 1.0); plans["P2"] = (Rp, 2.0)
                    au = float((dhi[i] - dlo[i]) / adr_i[i]) if tf in INTRA and adr_i[i] > 0 else np.nan
                    for ex, (R, tr) in plans.items():
                        if R / e0 * 100 > CAP[tf]:
                            continue
                        st, tp = e0 - side * R, e0 + side * tr * R
                        px, j = trade_to(o, h, l, c, sw, i, side, st, tp, jend)
                        out.append((name, tf, typ, "BUY" if side > 0 else "SELL", f["time"].iat[i], float(volx[i]), float(adx[i]),
                                    int(side * (c[i] - e200[i]) > 0), au, float(rsi[i]), ex, int(j), int(i),
                                    (side * (px - e0) - cost[i]) / R, (side * (px - e0) - 2 * cost[i]) / R))
    return out


def trade_to(o, h, l, c, sw, i, side, st, tp, jend):
    e0 = o[i + 1]; j = i + 1
    while j < len(c):
        if j > i + 1 and sw[j]:
            return c[j - 1], j - 1
        if j > i + 1 and side * (o[j] - st) <= 0:
            return o[j], j
        if j > i + 1 and side * (o[j] - tp) >= 0:
            return o[j], j
        if (l[j] <= st) if side > 0 else (h[j] >= st):
            return st, j
        if (h[j] >= tp) if side > 0 else (l[j] <= tp):
            return tp, j
        if j >= jend:
            return c[j], j
        j += 1
    return c[-1], len(c) - 1


COLS = ["name", "tf", "type", "side", "time", "volx", "adx", "with_trend", "adr_used", "rsi", "exit", "j", "i", "r1", "r2"]


def filt(G_, vol, ad, tr, adr):
    m = np.ones(len(G_), bool)
    if vol != "any":
        m &= G_["volx"].values >= vol
    if ad == "<20":
        m &= G_["adx"].values < 20
    elif ad == "<25":
        m &= G_["adx"].values < 25
    elif ad == ">=25":
        m &= G_["adx"].values >= 25
    if tr == "with":
        m &= G_["with_trend"].values == 1
    elif tr == "against":
        m &= G_["with_trend"].values == 0
    if adr == ">=0.8":
        m &= G_["adr_used"].values >= 0.8
    elif adr == "<=0.8":
        m &= G_["adr_used"].values <= 0.8
    return G_[m]


def main():
    J = [j for j in EX.jobs() if j[0] == "mi" and j[2] == "MCX"]
    J += [("mcx15", str(p), p.stem[4:]) for p in sorted((ROOT / "research/data/obuy_mcx").glob("fut_*.csv"))]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(run, J) for r in x]
    T = pd.DataFrame(rows, columns=COLS)
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T = T.sort_values("time").reset_index(drop=True)
    T["split"] = np.where(T["time"] < G.T1, "train", np.where(T["time"] < G.T2, "valid", "test"))
    T.to_csv(OUT / "mcx_multi_events.csv.gz", index=False)
    grid = list(itertools.product(("any", 1.5, 2.0), ("any", "<20", "<25", ">=25"), ("any", "with", "against"), ("any", ">=0.8", "<=0.8")))
    res = []
    L = T[T["tf"] != "15m"]
    for (tf, typ, side, ex), Gx in L.groupby(["tf", "type", "side", "exit"]):
        for vol, ad, tr, adr in grid:
            if tf not in INTRA and adr != "any":
                continue
            g = G.nonoverlap(filt(Gx, vol, ad, tr, adr))
            if len(g) < 60:
                continue
            row = dict(tf=tf, type=typ, side=side, exit=ex, vol=vol, adx=ad, trend=tr, adr=adr)
            for sp in ("train", "valid", "test"):
                x = g[g["split"] == sp]
                row.update({f"n_{sp}": len(x), f"exp2_{sp}": x["r2"].mean() if len(x) else np.nan,
                            f"win_{sp}": (x["r1"] > 0).mean() * 100 if len(x) else np.nan})
            pos = g[g["split"] == "test"].groupby("name")["r2"].mean()
            row["names_test_pos"] = f"{int((pos > 0).sum())}/{len(pos)}"
            row["t_tv"] = G.tstat(g[g["split"] != "test"]["r2"])
            res.append(row)
    S = pd.DataFrame(res)
    from scipy.stats import norm
    S["p"] = 1 - norm.cdf(S["t_tv"])
    S = S.sort_values("p").reset_index(drop=True)
    S["bh"] = (S["p"] <= 0.10 * (np.arange(len(S)) + 1) / len(S))[::-1].cummax()[::-1]
    S["pass_tv"] = (S["n_train"] >= 40) & (S["n_valid"] >= 25) & (S["exp2_train"] > 0) & (S["exp2_valid"] > 0)
    S.to_csv(OUT / "mcx_multi_summary.csv.gz", index=False)
    pd.set_option("display.width", 280); pd.set_option("display.max_rows", 300)
    print("POOLED combos:", len(S), "| pass train+valid:", int(S["pass_tv"].sum()), "| + FDR 10%:", int((S["pass_tv"] & S["bh"]).sum()))
    cols = ["tf", "type", "side", "exit", "vol", "adx", "trend", "adr", "n_train", "exp2_train", "n_valid", "exp2_valid", "n_test",
            "exp2_test", "win_test", "names_test_pos", "p", "bh"]
    P = S[S["pass_tv"]]
    print("\nfamily summary (pass train+valid): count, positive in test, median test exp2")
    print(P.groupby(["tf", "type", "side"]).agg(n=("exp2_test", "size"), pos=("exp2_test", lambda x: int((x > 0).sum())),
                                                med=("exp2_test", "median")).round(3).to_string())
    print("\nstrongest 30:")
    print(P[cols].head(30).round(3).to_string(index=False))
    # baseline per family (no filter) – what does each idea do raw?
    print("\nraw families (no filter, exit P1 1R), exp2 by split:")
    B = L[L["exit"] == "P1"].groupby(["tf", "type", "side"])
    rows = []
    for k, g in B:
        g = G.nonoverlap(g)
        rows.append(dict(tf=k[0], type=k[1], side=k[2], n=len(g), **{sp: round(g[g["split"] == sp]["r2"].mean(), 3) for sp in ("train", "valid", "test")}))
    print(pd.DataFrame(rows).to_string(index=False))
    # 15-minute sanity (2 months, 4 commodities)
    M = T[T["tf"] == "15m"]
    print("\n15-min (Aug–Oct 2026, 4 commodities), exit P1/P2/A15, no filter and volume >= 1.5x:")
    rows = []
    for (typ, side, ex), g in M.groupby(["type", "side", "exit"]):
        for vol in ("any", 1.5):
            x = G.nonoverlap(filt(g, vol, "any", "any", "any"))
            if len(x) >= 15:
                rows.append(dict(type=typ, side=side, exit=ex, vol=vol, n=len(x), win=round((x["r1"] > 0).mean() * 100, 1), exp2=round(x["r2"].mean(), 3)))
    print(pd.DataFrame(rows).sort_values("exp2", ascending=False).head(25).to_string(index=False))


if __name__ == "__main__":
    main()

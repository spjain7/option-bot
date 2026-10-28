"""DCP-001 (28-Oct-2026) – owner's request: DAILY candle patterns on stock, index and MCX futures.
  BUY : hammer after a downtrend · bullish engulfing after a downtrend
  SELL: hanging man after an uptrend · bearish engulfing after an uptrend
Shapes (day i, closed):
  hammer / hanging man: lower wick ≥ 2× body, upper wick ≤ 0.3× range
  bullish engulfing: day i-1 red, day i green, open_i ≤ close_{i-1} and close_i ≥ open_{i-1} (body engulfs body)
  bearish engulfing: mirror
Trend before the pattern: T1 EMA20 < EMA50 and previous close < EMA50 (down) / mirror (up) · or none (pattern only).
Entry: E1 next day's open · E2 breakout: a day within the next 3 trades beyond the pattern's high (BUY) / low (SELL) → fill
       at that level, or the open if it gaps beyond; cancelled if the stop is hit first.
Stop:  0.05 ATR beyond the pattern's low (BUY) / high (SELL); engulfing uses the two-day low / high.
Target 1R / 2R / 3R · time exit after 20 days · gap through the stop or target fills at the open · inside a day the stop is
assumed first when both are touched · exit before a contract switch · costs 1× (and 2× stress). Option V: volume ≥ 1.5×.
Periods: Angel 2022-26 (train < Jul-24 ≤ valid < Jul-25 ≤ test); NSE index daily 2011-26 (train < 2019 ≤ valid < 2022 ≤ test).
Also writes a per-call log (E2 breakout, T1 trend, 2R) for the last 2 months and the last 10 calls per instrument.
"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, hammer as HM  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
TGT, MAXB = (1.0, 2.0, 3.0), 20
PATS = {1: ("hammer", "bull engulfing"), -1: ("hanging man", "bear engulfing")}


def patterns(f):
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    body = np.abs(c - o); rng = h - l
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    ham = (rng > 0) & (lw >= 2 * body) & (uw <= 0.3 * rng)
    po, pc = np.r_[np.nan, o[:-1]], np.r_[np.nan, c[:-1]]
    pl, ph = np.r_[np.nan, l[:-1]], np.r_[np.nan, h[:-1]]
    bull = (pc < po) & (c > o) & (o <= pc) & (c >= po)
    bear = (pc > po) & (c < o) & (o >= pc) & (c <= po)
    e20, e50 = I.ema(f["close"], 20).values, I.ema(f["close"], 50).values
    c1, e50p = np.r_[np.nan, c[:-1]], np.r_[np.nan, e50[:-1]]
    down, up = (e20 < e50) & (c1 < e50p), (e20 > e50) & (c1 > e50p)
    lo2, hi2 = np.fmin(l, pl), np.fmax(h, ph)
    return {("hammer", 1): (ham, l, h), ("bull engulfing", 1): (bull, lo2, h),
            ("hanging man", -1): (ham, h, l), ("bear engulfing", -1): (bear, hi2, l)}, {1: down, -1: up}


def trade(f, i, side, stop_ref, trig, entry, tgt, cost):
    """Returns dict or None. stop_ref = pattern low (BUY) / high (SELL); trig = breakout level."""
    o, h, l, c, a, sw = (f[x].values for x in ("open", "high", "low", "close", "atr", "switch"))
    n = len(c)
    st = stop_ref - side * 0.05 * a[i]
    if entry == "E1":
        j0 = i + 1
        if j0 >= n or sw[j0]:
            return None
        e0 = o[j0]
    else:
        j0 = None
        for j in range(i + 1, min(i + 4, n)):
            if sw[j]:
                break
            if side * (o[j] - trig) > 0:
                j0, e0 = j, o[j]; break
            if (l[j] <= st) if side > 0 else (h[j] >= st):
                break
            if (h[j] > trig) if side > 0 else (l[j] < trig):
                j0, e0 = j, trig; break
        if j0 is None:
            return None
    R = side * (e0 - st)
    if not R > 0:
        return None
    tp = e0 + side * tgt * R
    px, why, j = None, None, j0
    while j < n:
        if j > j0 and sw[j]:
            px, why, j = c[j - 1], "contract roll", j - 1; break
        if j > j0 and side * (o[j] - st) <= 0:
            px, why = o[j], "stop (gap)"; break
        if j > j0 and side * (o[j] - tp) >= 0:
            px, why = o[j], f"target {tgt:g}R (gap)"; break
        if (l[j] <= st) if side > 0 else (h[j] >= st):
            px, why = st, "stop"; break
        if (h[j] >= tp) if side > 0 else (l[j] <= tp):
            px, why = tp, f"target {tgt:g}R"; break
        if j - j0 >= MAXB - 1:
            px, why = c[j], "time (20 days)"; break
        j += 1
    if px is None:
        px, why, j = c[n - 1], "open (data ends)", n - 1
    # move after entry until the stop is touched (≤ 40 days); the open of the stop day counts, its high/low does not
    best, bt, wbb, worst, k, stop_t = e0, j0, e0, e0, j0, None
    while k < n and k - j0 < 40:
        if k > j0 and sw[k]:
            break
        if k > j0 and side * (o[k] - best) > 0:
            best, bt, wbb = o[k], k, worst
        if (l[k] <= st) if side > 0 else (h[k] >= st):
            stop_t = k; break
        fav, adv = (h[k], l[k]) if side > 0 else (l[k], h[k])
        if side * (adv - worst) < 0:
            worst = adv
        if side * (fav - best) > 0:
            best, bt, wbb = fav, k, worst
        k += 1
    g = side * (px - e0)
    return dict(j0=j0, j=j, e0=e0, st=st, tp=tp, R=R, px=px, why=why, r1=(g - cost[i]) / R, r2=(g - 2 * cost[i]) / R,
                gross=g, cost=cost[i], best=best, bt=bt, wbb=wbb, stop_t=stop_t)


def run(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return [], []
    name = job[1]
    rows, logs = [], []
    for seg, f, _od, cost in fr:
        if not seg.endswith(("1d", "2011-26")) or "proxy" in seg:
            continue
        f = f.reset_index(drop=True)
        if len(f) < 120:
            continue
        f["atr"] = I.atr(f, 14)
        v = f["volume"].astype(float); vx = (v / v.rolling(20).mean().shift(1)).values
        P, TR = patterns(f)
        tm = f["time"].values
        for (pat, side), (shape, sref, trig) in P.items():
            for trend in ("T1", "none"):
                for vol in (False, True):
                    sig = shape & (TR[side] if trend == "T1" else True) & ((vx >= 1.5) if vol else True)
                    for en in ("E1", "E2"):
                        for tg in TGT:
                            busy = -1
                            for i in np.flatnonzero(sig):
                                if i < 60 or i <= busy or i >= len(f) - 2 or f["switch"].iat[i] or not f["atr"].iat[i] > 0:
                                    continue
                                t = trade(f, i, side, sref[i], trig[i], en, tg, cost)
                                if t is None:
                                    continue
                                busy = t["j"]
                                rows.append((seg, name, pat, "BUY" if side > 0 else "SELL", trend, "V" if vol else "none", en,
                                             f"{tg:g}R", tm[i], t["r1"], t["r2"], (t["gross"]) / t["R"]))
                                if en == "E2" and trend == "T1" and not vol and tg == 2.0 and "NSE" not in seg:
                                    s = side
                                    logs.append(dict(
                                        segment=seg.split()[0], instrument=name, pattern=pat, call="BUY" if s > 0 else "SELL",
                                        pattern_day=tm[i], pat_open=f["open"].iat[i], pat_high=f["high"].iat[i],
                                        pat_low=f["low"].iat[i], pat_close=f["close"].iat[i], volume_x=round(float(vx[i]), 2),
                                        entry_day=tm[t["j0"]], entry=round(t["e0"], 2), stop=round(t["st"], 2),
                                        target_2R=round(t["tp"], 2), risk_pts=round(t["R"], 2),
                                        risk_pct=round(t["R"] / t["e0"] * 100, 2),
                                        best_after_entry=round(t["best"], 2), best_day=tm[t["bt"]],
                                        best_move_pts=round(s * (t["best"] - t["e0"]), 2),
                                        best_move_pct=round(s * (t["best"] - t["e0"]) / t["e0"] * 100, 2),
                                        best_move_R=round(s * (t["best"] - t["e0"]) / t["R"], 2),
                                        worst_before_best_R=round(s * (t["wbb"] - t["e0"]) / t["R"], 2),
                                        stop_touched_day=tm[t["stop_t"]] if t["stop_t"] is not None else None,
                                        reached_1R=s * (t["best"] - t["e0"]) >= t["R"], reached_2R=s * (t["best"] - t["e0"]) >= 2 * t["R"],
                                        reached_3R=s * (t["best"] - t["e0"]) >= 3 * t["R"],
                                        exit_day=tm[t["j"]], exit=round(t["px"], 2), exit_reason=t["why"],
                                        gross_pts=round(t["gross"], 2), cost_pts=round(t["cost"], 2),
                                        net_pts=round(t["gross"] - t["cost"], 2), net_R=round(t["r1"], 2),
                                        cost_as_R=round(t["cost"] / t["R"], 3)))
    return rows, logs


def jobs():
    return [j for j in EX.jobs() if j[0] in ("mi", "nse", "stk")]


def main():
    rows, logs = [], []
    with Pool(2) as p:
        for r, lg in p.imap_unordered(run, jobs(), chunksize=1):
            rows += r; logs += lg
    T = pd.DataFrame(rows, columns=["seg", "name", "pattern", "side", "trend", "vol", "entry", "target", "time", "r1", "r2", "gross"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    long_hist = T["seg"].str.contains("NSE")
    a = np.where(long_hist, np.datetime64("2019-01-01"), np.datetime64("2024-07-01"))
    b = np.where(long_hist, np.datetime64("2022-01-01"), np.datetime64("2025-07-01"))
    T["split"] = np.where(T["time"].values < a, "1-train", np.where(T["time"].values < b, "2-valid", "3-test"))
    T.to_csv(OUT / "dcp_trades.csv.gz", index=False)
    K = ["seg", "pattern", "side", "trend", "vol", "entry", "target"]
    st = T.groupby(K + ["split"]).agg(n=("r1", "size"), exp2=("r2", "mean"),
                                       gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum())).reset_index()
    st["pf"] = st["gw"] / st["gl"].replace(0, np.nan)
    W = st.pivot_table(index=K, columns="split", values=["n", "exp2", "pf"])
    W.columns = [f"{bb[2:]}_{aa}" for aa, bb in W.columns]
    W = W.reset_index()
    nmin = dict(train=30, valid=15, test=15)
    W["pass"] = [all((r.get(f"{s}_n") or 0) >= nmin[s] and (r.get(f"{s}_exp2") or -1) > 0 and (r.get(f"{s}_pf") or 0) >= 1.2
                     for s in nmin) for r in W.to_dict("records")]
    P = T.groupby(K).agg(n=("r1", "size"), win=("r1", lambda x: (x > 0).mean() * 100), gross=("gross", "mean"),
                         net1=("r1", "mean"), net2=("r2", "mean")).reset_index()
    W = W.merge(P, on=K)
    W.to_csv(OUT / "dcp_variants.csv", index=False)
    L = pd.DataFrame(logs).sort_values(["segment", "instrument", "pattern_day"])
    L.to_csv(OUT / "dcp_log_all.csv.gz", index=False)
    print("variants", len(W), "pass", int(W["pass"].sum()), "log", len(L))


if __name__ == "__main__":
    main()

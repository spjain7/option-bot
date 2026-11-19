"""IDX-SEARCH-001 (19-Nov-2026, owner: "find more strategy and do depth" -> index futures). NIFTY + BANKNIFTY futures,
1h / 2h / 3h / 4h / 1d candles 2022-26 (Angel, stitched front month, never through a roll, 2x costs) and the index daily
2011-26 ("1dL", 15 years). BUY and SELL. Same harness (sell_exits.run; BUY = mirrored prices).
Signal families:
  * the 33 TradingView / Chartink scripts (tv_scripts.signals – trend changes) on both sides
  * the 13 reversal indicators (rev_ind.tops – tops for SELL, mirrored for BUY bottoms)
  * the 13 TradingView bottom scripts (tv_buy.bottoms – BUY, mirrored for SELL tops)
  * index-specific: previous-day high / low break (1h close), first-hour range break, gap fade (first 1h candle reverses a
    >= 0.5 ATR gap), inside-day break, NR4 day break, 5-day high / low break
Filters: none · DT (with the daily trend) · CT (against it) · E200 (EMA200 side of the call). Exits: SL x target 1x1,
1.5x1.5, 1.5x2, 2x1, 2x2, 2x3 ATR/R and E_TR (2 ATR, half at 1R + stop to cost, trail 2 ATR).
PASS = R > 0 and above RANDOM (same side / tf / filter / exit) in each of the 3 periods with >= 15 trades each
(2022-24 / 2024-25 / 2025-26; 1dL: 2011-16 / 2017-21 / 2022-26), both instruments pooled.
python research/program/idx_search.py -> results/idx_search_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.rev_ind import tops, mirror  # noqa: E402
from research.program.tv_scripts import signals as tv_sell  # noqa: E402
from research.program.tv_buy import bottoms  # noqa: E402
from research.program.mom_buy import summarise  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = [("1x1", 1.0, 1.0, 0, 0, 0), ("1.5x1.5", 1.5, 1.5, 0, 0, 0), ("1.5x2", 1.5, 2.0, 0, 0, 0), ("2x1", 2.0, 1.0, 0, 0, 0),
         ("2x2", 2.0, 2.0, 0, 0, 0), ("2x3", 2.0, 3.0, 0, 0, 0), ("E_TR", 2.0, 99.0, 1.0, 1.0, 2.0)]


def idx_specific(C, tf):
    """BUY-direction signals on C (SELL = the same function on mirrored candles)."""
    o, h, l, c = (C[x].astype(float) for x in ("open", "high", "low", "close"))
    t = pd.to_datetime(C["time"]); day = t.dt.normalize()
    S = {}
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1); a = tr.ewm(alpha=1 / 14, adjust=False).mean()
    if tf in ("1h", "2h"):
        dh = h.groupby(day).max(); pdh = day.map(dh.shift(1))
        S["IDX prev-day high break"] = (c > pdh) & ~((c.shift(1) > pdh) & (day == day.shift(1)))
        first = t.dt.strftime("%H:%M") == "09:15"
        fh = h.where(first).groupby(day).transform("max")
        S["IDX first-hour high break"] = ~first & (c > fh) & ~((c.shift(1) > fh) & (day == day.shift(1)))
        pc = c.groupby(day).last().shift(1); gap = o - day.map(pc)
        ad = day.map(a.groupby(day).last().shift(1))
        S["IDX gap-down fade (first candle green)"] = first & (gap <= -0.5 * ad) & (c > o)
    if tf in ("1d", "1dL"):
        ins = (h.shift(1) <= h.shift(2)) & (l.shift(1) >= l.shift(2))
        S["IDX inside-day break"] = ins & (c > h.shift(1))
        rg = h - l
        S["IDX NR4 break"] = (rg.shift(1) <= rg.shift(1).rolling(4).min()) & (c > h.shift(1))
        S["IDX 5-day high break"] = (c > h.shift(1).rolling(5).max()) & (c.shift(1) <= h.shift(2).rolling(5).max())
    return {k: v.fillna(False).astype(bool).values for k, v in S.items()}


def buy_signals(C, tf):
    """All BUY-direction families on candles C."""
    S = {}
    for k, v in tops(mirror(C)).items():
        S["REV " + k] = v.values
    for k, v in bottoms(C).items():
        S["BOT " + k] = v.values
    for k, v in tv_sell(mirror(C), tf in ("1h", "2h")).items():
        if k != "RANDOM":
            S["TV " + k] = np.asarray(v, bool)
    S.update(idx_specific(C, tf))
    return S


def one(job):
    name = job[1]
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    frames = {}
    if job[0] == "mi":
        k1 = [s for s in seg if s.endswith("1h")][0]; kd = [s for s in seg if s.endswith(" 1d")][0]
        f1, c1 = seg[k1]; fd, cd = seg[kd]
        c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
        frames["1h"] = (f1, c1); frames["1d"] = (fd, cd)
        k3 = [s for s in seg if s.endswith("3h")]
        if k3:
            frames["3h"] = seg[k3[0]]
        for hrs, tf in ((2, "2h"), (4, "4h")):
            f1s = f1.copy()
            if "switch" not in f1s:
                f1s["switch"] = False
            C, first = anchored(f1s, hrs); frames[tf] = (C, c1[first[:len(C)]])
        daily = fd
    else:
        kd = [s for s in seg if "1d" in s][0]; fd, cd = seg[kd]; frames["1dL"] = (fd, cd); daily = fd
    dtr = SA.daily_trend(daily.reset_index(drop=True))
    acc = {}
    rng = np.random.default_rng(sum(map(ord, name)) + len(job[0]))
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        tt = pd.to_datetime(C["time"]); day = tt.dt.normalize()
        dser = day.map(dtr).values
        if tf == "1dL":
            split = np.where(tt.values < np.datetime64("2017-01-01"), 0, np.where(tt.values < np.datetime64("2022-01-01"), 1, 2))
        else:
            split = np.where(tt.values < SV.P1, 0, np.where(tt.values < SV.P2, 1, 2))
        maxh = 10 if tf in ("1d", "1dL") else SV.MAXH.get(tf, 40)
        for side, CC in (("BUY", C), ("SELL", mirror(C))):
            S = buy_signals(CC, tf)                                  # BUY-direction on CC = SELL on C when mirrored
            S["RANDOM"] = rng.random(len(C)) < 0.05
            M = mirror(CC)                                          # run() simulates SELL: SELL of mirrored = BUY of CC
            f = H.features(M); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
            o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
            sw = f["switch"].values.astype(np.bool_)
            cl = CC["close"].astype(float); e200 = (cl > cl.ewm(span=200, adjust=False).mean()).values
            dt = (dser > 0) if side == "BUY" else (dser < 0)
            ct = (dser < 0) if side == "BUY" else (dser > 0)
            for nm, s in S.items():
                s = np.asarray(s, bool)
                for flt, m in (("none", s), ("DT", s & dt), ("CT", s & ct), ("E200", s & e200)):
                    if m.sum() < 1:
                        continue
                    for en, k, r, half, be, trail in EXITS:
                        for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, k, r, maxh if en != "E_TR" else 2 * maxh, cost, half, be, trail, H.CHASE):
                            a = acc.setdefault((nm, side, tf, flt, en, int(split[i])), [0, 0.0, 0, 0]); a[0] += 1; a[1] += rr; a[2] += rr > 0; a[3] += why == 1
    return acc


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[1] in ("NIFTY", "BANKNIFTY")) or (j[0] == "nse")]
    acc = {}
    with Pool(2) as p:
        for a in p.imap_unordered(one, J):
            for k_, v in (a or {}).items():
                x = acc.setdefault(k_, [0, 0.0, 0, 0])
                for q in range(4):
                    x[q] += v[q]
    L = summarise(acc, ["fam", "side", "tf", "flt", "exit"], OUT / "idx_search_summary.csv")
    L["pass15"] = np.all([(L[f"p{s}_R"] > 0) & (L[f"p{s}_R"] > L[f"p{s}_rand"].fillna(-9)) & (L[f"p{s}_n"] >= 15) for s in (1, 2, 3)], axis=0) & (L.fam != "RANDOM")
    L.to_csv(OUT / "idx_search_summary.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 50)
    c = ["fam", "side", "tf", "flt", "exit", "n", "win", "sl", "R", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand", "pass", "pass15"]
    print("PASSED (>=15 per period):", int(L["pass15"].sum()), "of", len(L), "| >=30:", int(L["pass"].sum()))
    print(L[L["pass15"]].sort_values("minR", ascending=False)[c].head(60).to_string(index=False))


if __name__ == "__main__":
    main()

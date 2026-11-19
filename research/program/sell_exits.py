"""SELL-EXITS-001 (19-Nov-2026, owner: "try better for the sell side"). Same 6 live stock SELL rules and signals
(stk_call_audit.LIVE, SEARCH-V2 harness semantics: next-open entry, 0.5-ATR chase limit, gap fills, roll exits, 2x costs,
one trade at a time per rule), only the EXIT management changes:
  E0 live          stop k ATR, target r R (as live)
  E1 half1R        book half at 1R, stop -> cost, rest at the live target
  E2 half0.75R     book half at 0.75R, stop -> cost, rest at the live target
  E3 half0.5R      book half at 0.5R, stop -> cost, rest at the live target
  E4 half1R+trail  book half at 1R, stop -> cost, rest trails 1 ATR above the lowest low since entry
  E5 BE1R          no booking; stop -> cost once 1R is reached; live target
  E6 tgt1R         whole position at 1R
  E7 tgt1.5R       whole position at 1.5R
Reported: win % (R > 0), NO-LOSS % (R >= -0.05, i.e. profit or at cost), R per call, per period, and in the live gated
portfolio (one per stock, max 5 a day, 5-session cooldown after a full stop).
python research/program/sell_exits.py -> results/sell_exits_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.stk_call_audit import LIVE, PRI, portfolio, stats  # noqa: E402

OUT = ROOT / "research/program/results"
# name: (half_at_R or 0, be_at_R or 0, trail_atr or 0, target_R or -1 = live)
EXITS = {"E0 live": (0, 0, 0, -1), "E1 half1R": (1.0, 1.0, 0, -1), "E2 half0.75R": (0.75, 0.75, 0, -1), "E3 half0.5R": (0.5, 0.5, 0, -1),
         "E4 half1R+trail": (1.0, 1.0, 1.0, 99), "E5 BE1R": (0, 1.0, 0, -1), "E6 tgt1R": (0, 0, 0, 1.0), "E7 tgt1.5R": (0, 0, 0, 1.5)}


@njit(cache=True)
def run(o, h, l, c, a, sw, sig, k, tgt, maxh, cost, half, be, trail, chase):
    n = len(c); res = []
    busy = -1
    for i in range(210, n - 1):
        if not sig[i] or i <= busy or sw[i] or sw[i + 1] or not a[i] > 0:
            continue
        mv = -(o[i + 1] - c[i]) / a[i]
        if mv > chase or mv < -chase:
            continue
        e0 = o[i + 1]; R = k * a[i]; st = e0 + R; tp = e0 - tgt * R
        hp = e0 - half * R if half > 0 else -1e18
        bp = e0 - be * R if be > 0 else -1e18
        booked = False; bes = False; lowest = e0; px = np.nan; j = i + 1; why = 0; mfe = 0.0
        while j < n:
            if j > i + 1 and sw[j]:
                px = c[j - 1]; j = j - 1; why = 4; break
            if j > i + 1 and o[j] >= st:
                px = o[j]; why = 1; break
            if j > i + 1 and o[j] <= tp:
                px = o[j]; why = 2; break
            if h[j] >= st:
                px = st; why = 1; break
            mfe = max(mfe, (e0 - l[j]) / R)
            if half > 0 and not booked and l[j] <= hp:
                booked = True
            if be > 0 and not bes and l[j] <= bp:
                bes = True; st = min(st, e0)
            if l[j] <= tp:
                px = tp; why = 2; break
            lowest = min(lowest, l[j])
            if trail > 0 and bes:
                st = min(st, lowest + trail * a[i])
            if j - (i + 1) >= maxh:
                px = c[j]; why = 3; break
            j += 1
        if np.isnan(px):
            px = c[n - 1]; j = n - 1; why = 5
        g = (e0 - px) / R
        r = (0.5 * half + 0.5 * g) if booked else g
        r -= 2 * cost[i] / R
        res.append((i, j, r, why, mfe, booked))
        busy = j
    return res


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1 = seg["STOCKS 1h"]; fd = seg["STOCKS 1d"][0]
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    frames = {}
    if "STOCKS 3h" in seg:
        frames["3h"] = seg["STOCKS 3h"]
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C, cost) in frames.items():
        rules = [r for r in LIVE if r[1] == tf]
        if not rules or len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        sets = {(a, b, cc): (x, y) for a, b, cc, x, y in SV.signal_sets(f, dtr, tf)}
        sets.update({(a, b, cc): (x, y) for a, b, cc, x, y in SA.signal_sets(f, dtr)})
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_); t = pd.to_datetime(f["time"]).values
        cost = np.asarray(cost, float)
        if len(cost) != len(c):
            cost = np.interp(np.arange(len(c)), np.linspace(0, len(c) - 1, len(cost)), cost)
        for rid, _, fam, par, flt, k, r, _ in rules:
            if (fam, par, flt) not in sets:
                continue
            sig = (np.nan_to_num(np.asarray(sets[(fam, par, flt)][1], float)) > 0)
            for en, (half, be, trail, tg) in EXITS.items():
                for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, sig, k, (r if tg < 0 else tg), SV.MAXH[tf], cost, half, be, trail, H.CHASE):
                    rows.append((en, rid, tf, job[1], t[i], t[j], rr, "stop" if why == 1 and not booked else "other", mfe, booked))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        T = pd.DataFrame([r for x in p.imap_unordered(one, J, chunksize=2) if x for r in x],
                         columns=["exitm", "rule", "tf", "name", "t_in", "t_out", "r", "exit", "mfe", "booked"])
    T["day"] = pd.to_datetime(T.t_in).dt.normalize(); T["pri"] = T.rule.map(PRI)
    tv = T.t_in.values.astype("datetime64[ns]"); T["split"] = np.where(tv < SV.P1, "p1", np.where(tv < SV.P2, "p2", "p3"))
    nd = len(pd.bdate_range(T.day.min(), T.day.max()))
    rows = []
    for en, G in T.groupby("exitm"):
        for scope, X in (("all signals", G), ("live gate", portfolio(G, per_tf=False, cap=5, cooldown=5))):
            X = X.sort_values("t_in"); s = stats(X.r)
            row = dict(exit=en, scope=scope, calls_per_day=round(len(X) / nd, 2), n=s["n"], win=s["win"], no_loss=round(100 * (X.r >= -0.05).mean(), 1),
                       R=s["expR"], PF=s["PF"], totalR=s["totalR"], maxDD=s["maxDD_R"], lose_streak=s["lose_streak"])
            for sp in ("p1", "p2", "p3"):
                x = X[X.split == sp].r; row[f"{sp}_win"] = round(100 * (x > 0).mean(), 1); row[f"{sp}_noloss"] = round(100 * (x >= -0.05).mean(), 1)
                row[f"{sp}_R"] = round(x.mean(), 3)
            rows.append(row)
    L = pd.DataFrame(rows); L.to_csv(OUT / "sell_exits_summary.csv", index=False)
    pd.set_option("display.width", 260)
    print(L[L.scope == "live gate"].drop(columns="scope").to_string(index=False))
    print("\nall signals:"); print(L[L.scope == "all signals"].drop(columns="scope")[["exit", "n", "win", "no_loss", "R", "PF", "p1_R", "p2_R", "p3_R"]].to_string(index=False))
    # per rule, best exits
    P = T.groupby(["rule", "exitm"]).r.agg(n="size", win=lambda x: round(100 * (x > 0).mean(), 1), noloss=lambda x: round(100 * (x >= -0.05).mean(), 1), R="mean").round(3)
    print("\nper rule:"); print(P.to_string())
    T.to_csv(OUT / "sell_exits_trades.csv.gz", index=False)


if __name__ == "__main__":
    main()

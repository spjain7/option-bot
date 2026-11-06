"""EQ-INTRA-001 – NSE cash INTRADAY: ORB failure diagnosis + seven alternative intraday setups (actual CASH 5-minute prices).

Setups (long and short = intraday MIS; first event of each setup per stock per day; entries 09:30-14:00; square-off at the
15:10 bar close; stop checked first in every bar incl. the entry bar):
  ORB      break of the 15-minute opening range (baseline)            stop: other side of the range
  ORB_RET  after the break, price comes back to the range edge and the bar closes beyond it -> stop-entry beyond that bar
  PB1      first pull-back after the break (first bar with a lower low / higher high), entry on taking out the pull-back bar
  VWAP     VWAP reclaim (loss): >= 6 bars below (above) VWAP, then a close back above (below) with bar volume >= 1.5x
  RVOL     relative-volume expansion: bar volume >= 3x the same time-of-day 20-session average, strong close, body >= 50 %
  PDH      previous-day high (low) breakout                           stop: 0.3 x daily ATR beyond the level
  TREND    daily trend (prior close vs EMA20) + above VWAP and today's open, pull-back touching VWAP, bullish close
  FAIL     failed ORB: high above the range but the bar closes back inside within 2 bars -> sell below that bar (mirror)
  For all but ORB/PDH the stop is the signal bar's other extreme (risk 0.15-1.0 x daily ATR).
Exits: 1R, 2R, square-off only (EOD). Costs: eq_data.cost_frac('intraday') (0.163 % round trip incl. slippage).
Diagnostics per trade: gross R, cost in R, MFE / MAE (R) until exit / square-off, false break (back inside within 3 bars),
gap bucket, market direction (median stock move since the open at entry), entry minute.
python research/program/eq_intraday.py [m5|eq]"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_data as ED  # noqa: E402

OUT = ROOT / "research/program/results"
SETUPS = ("ORB", "ORB_RET", "PB1", "VWAP", "RVOL", "PDH", "TREND", "FAIL")
CF = ED.cost_frac("intraday")


def load(src):
    D = {}
    if src == "m5":
        for f in sorted((ROOT / "research/data/m5").glob("eq_*.csv")):
            D[f.stem[3:]] = ED.clean(pd.read_csv(f, parse_dates=["time"]), intraday=True)
    else:
        u = pd.read_csv(ED.EQ / "universe.csv")
        for s in u[u.fno].symbol:
            d = ED.load(s, "FIVE_MINUTE")
            if d is not None and len(d) > 2000:
                D[s] = d
    return D


def market_move(D):
    """median across stocks of (close / day open - 1) per 5-minute timestamp – market direction proxy at any bar."""
    parts = []
    for s, d in D.items():
        day = d.time.dt.normalize()
        o = d.groupby(day).open.transform("first")
        parts.append(pd.Series((d.close / o - 1).values, index=d.time.values, name=s))
    M = pd.concat(parts, axis=1)
    return M.median(axis=1)


def trade(H, L, C, O, j, side, e, st, k_end):
    """walk bars j..k_end; returns dict of outcomes for 1R / 2R / EOD plus MFE / MAE (in R, gross)."""
    R = side * (e - st)
    res = {}
    for ex in (1.0, 2.0, 0.0):
        tgt = e + side * ex * R if ex else None
        px = None
        for k in range(j, k_end + 1):
            if (side > 0 and L[k] <= st) or (side < 0 and H[k] >= st):
                px = st if k == j or not ((side > 0 and O[k] <= st) or (side < 0 and O[k] >= st)) else O[k]; break
            if tgt is not None and k > j and ((side > 0 and H[k] >= tgt) or (side < 0 and L[k] <= tgt)):
                px = O[k] if ((side > 0 and O[k] >= tgt) or (side < 0 and O[k] <= tgt)) else tgt; break
        if px is None:
            px = C[k_end]
        res[ex] = side * (px - e) / R
    # MFE / MAE until stop or square-off
    mfe = mae = 0.0
    for k in range(j, k_end + 1):
        mfe = max(mfe, side * ((H[k] if side > 0 else L[k]) - e) / R)
        mae = min(mae, side * ((L[k] if side > 0 else H[k]) - e) / R)
        if (side > 0 and L[k] <= st) or (side < 0 and H[k] >= st):
            break
    return res, mfe, mae, R


def scan_stock(sym, d, mkt):
    d = d.copy()
    d["day"] = d.time.dt.normalize(); d["m"] = d.time.dt.hour * 60 + d.time.dt.minute - 555
    days = d.groupby("day")
    daily = days.agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
    tr = np.maximum(daily.h - daily.l, np.maximum((daily.h - daily.c.shift(1)).abs(), (daily.l - daily.c.shift(1)).abs()))
    daily["atr"] = tr.rolling(14, min_periods=8).mean().shift(1)
    daily["pc"], daily["ph"], daily["pl"] = daily.c.shift(1), daily.h.shift(1), daily.l.shift(1)
    daily["ema20"] = daily.c.ewm(span=20, adjust=False).mean().shift(1)
    # same time-of-day average volume (20 sessions)
    piv = d.pivot_table(index="day", columns="m", values="volume", aggfunc="sum")
    tod = piv.rolling(20, min_periods=10).mean().shift(1)
    rows = []
    for day, g in days:
        r = daily.loc[day]
        if not (r.atr > 0 and r.pc > 0):
            continue
        g = g[g.m <= 595]
        if len(g) < 40:
            continue
        O, H, L, C, V, M = (g[x].values.astype(float) for x in ("open", "high", "low", "close", "volume", "m"))
        T = g.time.values
        pv = np.cumsum((H + L + C) / 3 * V); cv = np.cumsum(V); vw = pv / np.where(cv > 0, cv, np.nan)
        orb = M < 15
        orh, orl = H[orb].max(), L[orb].min()
        if not orh > orl:
            continue
        tv = tod.loc[day].reindex(M).values if day in tod.index else np.full(len(M), np.nan)
        k_end = len(C) - 1
        gap = (r.o - r.pc) / r.pc
        trend = 1 if r.pc > r.ema20 else -1
        a = r.atr
        done = set()

        def add(setup, side, j, e, st, note=""):
            if (setup, side) in done or j >= k_end or M[j] > 285 or M[j] < 15:
                return
            R = side * (e - st)
            if not (0.15 * a <= R <= 1.0 * a):
                return
            done.add((setup, side))
            res, mfe, mae, R = trade(H, L, C, O, j, side, e, st, k_end)
            back = any((side > 0 and C[k] < (orh if setup in ("ORB",) else e)) or (side < 0 and C[k] > (orl if setup in ("ORB",) else e))
                       for k in range(j, min(j + 3, k_end + 1)))
            mk = mkt.get(T[j], np.nan)
            cost = CF * e / R
            rows.append(dict(sym=sym, day=day, setup=setup, side=side, minute=int(M[j]), gross1=res[1.0], gross2=res[2.0],
                             grossE=res[0.0], cost=cost, mfe=mfe, mae=mae, false_break=back, gap=gap, trend=trend,
                             mkt=np.sign(mk) if mk == mk else 0, risk_atr=R / a, risk_pct=R / e))

        brk_up = brk_dn = None
        for k in range(len(C)):
            if M[k] < 15:
                continue
            # ORB
            if brk_up is None and H[k] > orh:
                brk_up = k; add("ORB", 1, k, max(orh + 0.05, O[k]), orl)
            if brk_dn is None and L[k] < orl:
                brk_dn = k; add("ORB", -1, k, min(orl - 0.05, O[k]), orh)
            # FAIL: broke above, closes back inside within 2 bars -> sell below that bar
            if brk_up is not None and k - brk_up <= 2 and C[k] < orh and k + 1 <= k_end and ("FAIL", -1) not in done:
                hi = H[brk_up:k + 1].max()
                for t in range(k + 1, min(k + 4, k_end + 1)):
                    if L[t] < L[k]:
                        add("FAIL", -1, t, min(L[k] - 0.05, O[t]), hi + 0.05); break
                    if H[t] > hi:
                        break
            if brk_dn is not None and k - brk_dn <= 2 and C[k] > orl and k + 1 <= k_end and ("FAIL", 1) not in done:
                lo = L[brk_dn:k + 1].min()
                for t in range(k + 1, min(k + 4, k_end + 1)):
                    if H[t] > H[k]:
                        add("FAIL", 1, t, max(H[k] + 0.05, O[t]), lo - 0.05); break
                    if L[t] < lo:
                        break
            # ORB retest
            for side, b, lvl in ((1, brk_up, orh), (-1, brk_dn, orl)):
                if b is None or k <= b + 1 or ("ORB_RET", side) in done:
                    continue
                touch = (L[k] <= lvl + 0.1 * (orh - orl)) if side > 0 else (H[k] >= lvl - 0.1 * (orh - orl))
                hold = C[k] > lvl if side > 0 else C[k] < lvl
                if touch and hold:
                    for t in range(k + 1, min(k + 4, k_end + 1)):
                        if side > 0 and H[t] > H[k]:
                            add("ORB_RET", 1, t, max(H[k] + 0.05, O[t]), L[k] - 0.05); break
                        if side < 0 and L[t] < L[k]:
                            add("ORB_RET", -1, t, min(L[k] - 0.05, O[t]), H[k] + 0.05); break
            # first pull-back after the break
            for side, b in ((1, brk_up), (-1, brk_dn)):
                if b is None or k <= b or ("PB1", side) in done:
                    continue
                if (side > 0 and L[k] < L[k - 1]) or (side < 0 and H[k] > H[k - 1]):
                    for t in range(k + 1, min(k + 4, k_end + 1)):
                        if side > 0 and H[t] > H[k]:
                            add("PB1", 1, t, max(H[k] + 0.05, O[t]), L[k] - 0.05); break
                        if side < 0 and L[t] < L[k]:
                            add("PB1", -1, t, min(L[k] - 0.05, O[t]), H[k] + 0.05); break
                    done.add(("PB1_seen", side))
            # VWAP reclaim / loss
            if k >= 6 and M[k] >= 30:
                bvol = V[k] / (np.nanmean(V[max(0, k - 20):k]) or np.nan)
                if np.all(C[k - 6:k] < vw[k - 6:k]) and C[k] > vw[k] and bvol >= 1.5 and k + 1 <= k_end and H[k + 1] > H[k]:
                    add("VWAP", 1, k + 1, max(H[k] + 0.05, O[k + 1]), L[k] - 0.05)
                if np.all(C[k - 6:k] > vw[k - 6:k]) and C[k] < vw[k] and bvol >= 1.5 and k + 1 <= k_end and L[k + 1] < L[k]:
                    add("VWAP", -1, k + 1, min(L[k] - 0.05, O[k + 1]), H[k] + 0.05)
            # relative volume expansion
            if tv[k] == tv[k] and tv[k] > 0 and V[k] >= 3 * tv[k] and k + 1 <= k_end:
                rng = H[k] - L[k]
                if rng > 0 and abs(C[k] - O[k]) >= 0.5 * rng:
                    if C[k] > O[k] and (C[k] - L[k]) / rng >= 0.75 and H[k + 1] > H[k]:
                        add("RVOL", 1, k + 1, max(H[k] + 0.05, O[k + 1]), L[k] - 0.05)
                    if C[k] < O[k] and (H[k] - C[k]) / rng >= 0.75 and L[k + 1] < L[k]:
                        add("RVOL", -1, k + 1, min(L[k] - 0.05, O[k + 1]), H[k] + 0.05)
            # previous-day high / low breakout
            if H[k] > r.ph and (k == 0 or H[:k].max() <= r.ph):
                add("PDH", 1, k, max(r.ph + 0.05, O[k]), r.ph - 0.3 * a)
            if L[k] < r.pl and (k == 0 or L[:k].min() >= r.pl):
                add("PDH", -1, k, min(r.pl - 0.05, O[k]), r.pl + 0.3 * a)
            # trend continuation: pull-back to VWAP in the daily trend direction
            if k >= 6 and M[k] >= 30 and k + 1 <= k_end:
                if trend > 0 and C[k] > vw[k] and C[k] > r.o and L[k] <= vw[k] and C[k] > O[k] and H[k + 1] > H[k]:
                    add("TREND", 1, k + 1, max(H[k] + 0.05, O[k + 1]), L[k] - 0.05)
                if trend < 0 and C[k] < vw[k] and C[k] < r.o and H[k] >= vw[k] and C[k] < O[k] and L[k + 1] < L[k]:
                    add("TREND", -1, k + 1, min(L[k] - 0.05, O[k + 1]), H[k] + 0.05)
    return rows


def main(src):
    D = load(src)
    mkt = market_move(D).to_dict()
    rows = []
    for s, d in D.items():
        rows += scan_stock(s, d, mkt)
    T = pd.DataFrame(rows)
    for ex, col in (("1R", "gross1"), ("2R", "gross2"), ("EOD", "grossE")):
        T[f"net_{ex}"] = T[col] - T.cost
    tag = "intra_m5" if src == "m5" else "intra_eq"
    T.to_csv(OUT / f"{tag}_trades.csv.gz", index=False)
    report(T, tag)


def report(T, tag):
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    days = T.day.nunique(); stocks = T.sym.nunique()
    print(f"{tag}: {days} sessions · {stocks} stocks · {len(T):,} trades\n")
    o = T[T.setup == "ORB"]
    print("=== WHY ORB FAILS (15-min OR, both sides) ===")
    print(f"trades {len(o)} · gross EOD {o.grossE.mean():+.3f}R · cost {o.cost.mean():.3f}R/trade (median risk {100 * o.risk_pct.median():.2f}% of price)"
          f" · net EOD {o.net_EOD.mean():+.3f}R")
    print(f"false breaks (closed back inside within 3 bars): {100 * o.false_break.mean():.0f}% · their gross EOD {o[o.false_break].grossE.mean():+.2f}R vs "
          f"genuine {o[~o.false_break].grossE.mean():+.2f}R")
    print(f"reach +1R before stop/close: {100 * (o.mfe >= 1).mean():.0f}% · +2R: {100 * (o.mfe >= 2).mean():.0f}% · stopped (MAE <= -1R): {100 * (o.mae <= -1).mean():.0f}%")
    for col, nm in (("gap", "gap"),):
        b = pd.cut(o.gap * o.side, [-1, -0.01, -0.003, 0.003, 0.01, 1], labels=["against >1%", "against", "flat", "with", "with >1%"])
        print("by gap in trade direction:", o.groupby(b, observed=True).net_EOD.agg(["size", "mean"]).round(3).to_dict("index"))
    print("by market direction at entry (same/flat/against):",
          o.groupby(o.mkt * o.side).net_EOD.agg(["size", "mean"]).round(3).to_dict("index"))
    print("by entry time:", o.groupby(pd.cut(o.minute, [0, 30, 60, 120, 300]), observed=True).net_EOD.agg(["size", "mean"]).round(3).to_dict("index"))
    print("by risk size (x daily ATR):", o.groupby(pd.cut(o.risk_atr, [0, 0.3, 0.5, 0.7, 1.0]), observed=True).agg(
        n=("net_EOD", "size"), gross=("grossE", "mean"), cost=("cost", "mean"), net=("net_EOD", "mean")).round(3).to_dict("index"))
    print("\n=== ALL SETUPS (net of costs; first half / second half of the sessions) ===")
    mid = np.sort(T.day.unique())[days // 2]
    rows = []
    for (s, sd), x in T.groupby(["setup", "side"]):
        for ex in ("1R", "2R", "EOD"):
            y = x[f"net_{ex}"]
            rows.append(dict(setup=s, side="BUY" if sd > 0 else "SELL", exit=ex, n=len(y), per_day=len(y) / days, win=100 * (y > 0).mean(),
                             R=y.mean(), gross=x[{"1R": "gross1", "2R": "gross2", "EOD": "grossE"}[ex]].mean(), cost=x.cost.mean(),
                             h1=y[x.day < mid].mean(), h2=y[x.day >= mid].mean(),
                             with_mkt=y[x.mkt == x.side].mean(), stocks_pos=(y.groupby(x.sym).mean() > 0).mean()))
    S = pd.DataFrame(rows).sort_values("R", ascending=False)
    S.to_csv(OUT / f"{tag}_summary.csv", index=False)
    print(S.round(3).to_string(index=False))


if __name__ == "__main__":
    main((sys.argv[1:] or ["m5"])[0])

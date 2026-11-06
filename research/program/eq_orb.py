"""EQ-ORB-001 – NSE cash INTRADAY opening-range breakout (separate from delivery research; results never mixed).

Pre-registered: OR = first 5 / 15 / 30 minutes. Long: buy-stop 1 tick above the OR high; short (intraday MIS only):
sell-stop below the OR low; first trigger of the day only, no new entries after 14:00, mandatory square-off at the
15:10 bar close. Stop = other side of the OR (structure) or OR midpoint. Exit = 1R / 2R / square-off only.
Filters: OR width 0.25-1.2 x daily ATR(14) (prior days); relative OR volume >= 1.5x its 20-day average; gap
{any, |gap| < 1 %, gap in trade direction}; NIFTY direction (NIFTY's OR candle same direction) {off, on}; daily trend
(prior close vs EMA20) {off, with}. Conservative fills: stop checked first inside a bar, including the entry bar.
Costs: intraday round trip (eq_data.cost_frac('intraday')) incl. 0.04 % slippage per side.
Validation: chronological halves + monthly stability; PASS = positive in both halves, BH q < 0.10, n >= 300,
>= 55 % of stocks positive, >= 60 % of months positive.
python research/program/eq_orb.py [m5|eq]    m5 = research/data/m5 (≈3 months, preliminary) · eq = NSE_EQ 5-min (≈2 years)"""
import sys
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_data as ED  # noqa: E402

OUT = ROOT / "research/program/results"
ORS = (5, 15, 30); STOPS = ("OR", "MID"); EXITS = (1.0, 2.0, 0.0); GAPS = ("any", "small", "with"); NIF = (0, 1); TREND = (0, 1)


def load(src):
    D = {}
    if src == "m5":
        for f in sorted((ROOT / "research/data/m5").glob("eq_*.csv")):
            d = pd.read_csv(f, parse_dates=["time"]); D[f.stem[3:]] = ED.clean(d, intraday=True)
        nifty = None
    else:
        u = pd.read_csv(ED.EQ / "universe.csv")
        for s in u[u.fno].symbol:
            d = ED.load(s, "FIVE_MINUTE")
            if d is not None and len(d) > 2000:
                D[s] = d
        nifty = ED.load("NIFTY", "FIVE_MINUTE")
    return D, nifty


def day_table(d, orm):
    """One row per session: OR high/low/volume, open, prior close, daily ATR, EMA20 trend, and the post-OR bars."""
    d = d.copy(); d["day"] = d.time.dt.normalize(); d["mins"] = d.time.dt.hour * 60 + d.time.dt.minute - 555
    g = d.groupby("day")
    daily = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    tr = np.maximum(daily.high - daily.low, np.maximum((daily.high - daily.close.shift(1)).abs(), (daily.low - daily.close.shift(1)).abs()))
    daily["atr"] = tr.rolling(14, min_periods=10).mean().shift(1)
    daily["pc"] = daily.close.shift(1)
    daily["ema20"] = daily.close.ewm(span=20, adjust=False).mean().shift(1)
    orb = d[d.mins < orm].groupby("day").agg(orh=("high", "max"), orl=("low", "min"), orv=("volume", "sum"), oro=("open", "first"), orc=("close", "last"))
    daily = daily.join(orb)
    daily["orv20"] = daily.orv.rolling(20, min_periods=10).mean().shift(1)
    return d, daily


def simulate(d, daily, orm, nifty_dir, tick=0.05):
    """All first triggers (long and short) with every stop/exit variant -> list of dict rows (filters applied later)."""
    rows = []
    for day, bars in d[d.mins >= orm].groupby("day"):
        r = daily.loc[day]
        if not (r.atr > 0 and r.orh > r.orl and r.pc > 0):
            continue
        bb = bars[bars.mins <= 595]                            # through the 15:10 bar
        if bb.empty:
            continue
        H, L, O, C, M = bb.high.values, bb.low.values, bb.open.values, bb.close.values, bb.mins.values
        upi = np.flatnonzero(H > r.orh); dni = np.flatnonzero(L < r.orl)
        first = None
        if len(upi) and (not len(dni) or upi[0] < dni[0]):
            first = (1, upi[0])
        elif len(dni) and (not len(upi) or dni[0] < upi[0]):
            first = (-1, dni[0])
        elif len(upi) and len(dni) and upi[0] == dni[0]:
            continue                                            # both sides in one bar – ambiguous, skip
        if first is None:
            continue
        side, j = first
        if M[j] > 285:                                         # after 14:00
            continue
        lvl = r.orh + tick if side > 0 else r.orl - tick
        e = max(lvl, O[j]) if side > 0 else min(lvl, O[j])
        width = (r.orh - r.orl) / r.atr
        gap = (r.open - r.pc) / r.pc
        base = dict(day=day, side=side, width=width, relv=r.orv / r.orv20 if r.orv20 > 0 else np.nan, gap=gap,
                    trend=1 if r.pc > r.ema20 else -1, nif=nifty_dir.get(day, 0), mins=int(M[j]))
        for sp in STOPS:
            st = (r.orl if side > 0 else r.orh) if sp == "OR" else (r.orh + r.orl) / 2
            R = side * (e - st)
            if not R > 0:
                continue
            for ex in EXITS:
                tgt = e + side * ex * R if ex > 0 else None
                px = None
                for k in range(j, len(H)):
                    if (side > 0 and L[k] <= st) or (side < 0 and H[k] >= st):
                        px = st if k == j or not ((side > 0 and O[k] <= st) or (side < 0 and O[k] >= st)) else O[k]; break
                    if tgt is not None and k > j and ((side > 0 and H[k] >= tgt) or (side < 0 and L[k] <= tgt)):
                        px = tgt; break
                if px is None:
                    px = C[-1]
                cost = ED.cost_frac("intraday") * e
                rows.append(dict(base, stop=sp, exit=ex, R=(side * (px - e) - cost) / R, risk_pct=R / e))
    return rows


def nifty_dirs(nifty, orm):
    if nifty is None:
        return {}
    n = nifty.copy(); n["day"] = n.time.dt.normalize(); n["mins"] = n.time.dt.hour * 60 + n.time.dt.minute - 555
    g = n[n.mins < orm].groupby("day").agg(o=("open", "first"), c=("close", "last"))
    return dict(zip(g.index, np.sign(g.c - g.o).astype(int)))


def main(src):
    D, nifty = load(src)
    T = []
    for orm in ORS:
        if nifty is not None:
            nd = nifty_dirs(nifty, orm)
        else:                                                  # m5 set has no index: median stock OR direction
            ret = []
            for s, d in D.items():
                y = d.copy(); y["day"] = y.time.dt.normalize(); y["mins"] = y.time.dt.hour * 60 + y.time.dt.minute - 555
                z = y[y.mins < orm].groupby("day").agg(o=("open", "first"), c=("close", "last"))
                ret.append(np.log(z.c / z.o).rename(s))
            nd = dict(np.sign(pd.concat(ret, axis=1).median(axis=1)).astype(int))
        for s, d in D.items():
            dd, daily = day_table(d, orm)
            for r in simulate(dd, daily, orm, nd):
                r.update(sym=s, orm=orm); T.append(r)
    T = pd.DataFrame(T)
    tag = "orb_m5" if src == "m5" else "orb_eq"
    T.to_csv(OUT / f"{tag}_trades.csv.gz", index=False)
    summarise(T, tag)


def summarise(T, tag):
    T = T[(T.width >= 0.25) & (T.width <= 1.2) & (T.relv >= 1.5)].copy()
    days = np.sort(T.day.unique()); mid = days[len(days) // 2]
    T["half"] = (T.day >= mid).astype(int); T["month"] = pd.to_datetime(T.day).dt.to_period("M")
    rows = []
    for orm, side, sp, ex, gp, nf, tr in product(ORS, (1, -1), STOPS, EXITS, GAPS, NIF, TREND):
        x = T[(T.orm == orm) & (T.side == side) & (T.stop == sp) & (T.exit == ex)]
        if gp == "small":
            x = x[x.gap.abs() < 0.01]
        elif gp == "with":
            x = x[np.sign(x.gap) == side]
        if nf:
            x = x[x.nif == side]
        if tr:
            x = x[x.trend == side]
        if len(x) < 30:
            continue
        R = x.R.values; w, ls = R[R > 0], R[R <= 0]
        t = R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))
        mo = x.groupby("month").R.mean()
        rows.append(dict(orm=orm, side="BUY" if side > 0 else "SELL", stop=sp, exit="EOD" if ex == 0 else f"{ex:g}R", gap=gp, nifty=nf,
                         trend=tr, n=len(R), win=100 * (R > 0).mean(), R=R.mean(), PF=w.sum() / -ls.sum() if len(ls) else np.nan,
                         h1=x[x.half == 0].R.mean(), h2=x[x.half == 1].R.mean(), months_pos=(mo > 0).mean(),
                         stocks_pos=(x.groupby("sym").R.mean() > 0).mean(), per_day=len(R) / len(days),
                         risk_pct=100 * x.risk_pct.median(), p=stats.t.sf(t, len(R) - 1)))
    S = pd.DataFrame(rows).sort_values("p").reset_index(drop=True)
    m = len(S); S["q"] = (S.p * m / (np.arange(m) + 1))[::-1].cummin()[::-1].clip(upper=1)
    S["PASS"] = (S.h1 > 0) & (S.h2 > 0) & (S.q < 0.10) & (S.n >= 300) & (S.stocks_pos >= 0.55) & (S.months_pos >= 0.6)
    S.to_csv(OUT / f"{tag}_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(f"days {len(days)} · combinations {len(S)} · PASS {int(S.PASS.sum())}")
    print(S.groupby(["orm", "side"]).R.agg(["size", "mean", "max"]).round(3))
    print(S.sort_values("R", ascending=False).head(15).round(3).to_string(index=False))


if __name__ == "__main__":
    main((sys.argv[1:] or ["m5"])[0])

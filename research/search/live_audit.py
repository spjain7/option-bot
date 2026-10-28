"""LIVE-AUDIT-001 (28-Oct-2026): performance audit of every LIVE futures rule, in R, with the live exits.

Strategies (exactly as live after 28-Oct):
  S1 3h breakout   MCX 7 + NIFTY/BANKNIFTY · close > 20-candle high, vol > 1.5×, EMA200 side · SL 2 ATR · target 2R · 40 candles
  S2 daily breakout same entry on daily candles                                   · SL 1.5 ATR · target 3R · 40 days
  S3 monthly breakout first daily close beyond last month's high/low + weekly & monthly trend · SL 1.5 ATR · 2R · 20 days
  S4 stock OI breakout 181 stock futures · 20-day breakout, vol > 1.5×, OI ≥ +2% with price, EMA200 · SL 2 ATR · trail 3 ATR · 40 d
  S5 stock bearish engulfing after a rise, vol > 1.5× · SL 1.5 ATR · target 1R · 10 days
Each also with the 28-Oct stop-width cap (3h 2.5%, daily/monthly 4%, stocks 6%).
Fills: entry next candle open; stop checked before target inside a candle; gap through stop fills at the open.
Costs at 1× and 2×. Results in R (1R = the stop distance). Portfolio drawdown = cumulative R over all trades in time order.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import strategy_search as SS, stock_search as SR, stock_check as SC  # noqa
from research.search.sr_levels import levels as SRLV  # noqa
from research.search.candle_rev import pats  # noqa
from alerts import stats as ST  # noqa
from alerts.stocks import in_rollover_window  # noqa

SPLIT = pd.Timestamp("2024-07-01")
OUT = ROOT / "research/search/results_live_audit"
CAP = {"S1": 2.5, "S2": 4.0, "S3": 4.0, "S4": 6.0, "S5": 6.0}


def sim(df, sig, k_sl, tgt_r, maxh, swd, cost, trail=None, start=210):
    o, h, l, c = (df[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = I.atr(df, 14).values
    e200 = I.ema(df["close"], 200).values
    atrp = a / c
    med = pd.Series(atrp).rolling(250, min_periods=60).median().values
    out, busy = [], -1
    for i in np.flatnonzero(sig):
        if i < start or i <= busy or i >= len(c) - 1 or swd[i] or not a[i] > 0:
            continue
        s = int(sig[i]); e0 = o[i + 1]; R = k_sl * a[i]
        st = e0 - s * R; tp = e0 + s * tgt_r * R if tgt_r else None
        best = e0; px = None; j = i + 1
        while j < len(c):
            if (o[j] <= st) if s > 0 else (o[j] >= st): px = o[j]; break
            if tp is not None and ((o[j] >= tp) if s > 0 else (o[j] <= tp)): px = o[j]; break  # gap through the target fills at the open (VERIFY-EXITS, 29-Oct)
            if (l[j] <= st) if s > 0 else (h[j] >= st): px = st; break
            if tp is not None and ((h[j] >= tp) if s > 0 else (l[j] <= tp)): px = tp; break
            if swd[j] or j - (i + 1) >= maxh: px = c[j]; break
            if trail:
                best = max(best, c[j]) if s > 0 else min(best, c[j])
                ns = best - s * trail * a[j]
                if s * (ns - st) > 0: st = ns
            j += 1
        if px is None: px, j = c[-1], len(c) - 1
        regime = ("trend" if abs(c[i] - e200[i]) > 2 * a[i] else "range") + "/" + ("hi-vol" if atrp[i] > med[i] else "lo-vol")
        out.append(dict(time=df["time"].iat[i], side="BUY" if s > 0 else "SELL", r1=(s * (px - e0) - cost[i]) / R,
                        r2=(s * (px - e0) - 2 * cost[i]) / R, slpct=R / e0 * 100, regime=regime))
        busy = j
    return out


def bo_signal(df):
    c, hi, lo, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
    va = v.rolling(20).mean().shift(1); e = I.ema(c, 200)
    return np.where((c > hi.shift(1).rolling(20).max()) & (v > 1.5 * va) & (c > e), 1,
                    np.where((c < lo.shift(1).rolling(20).min()) & (v > 1.5 * va) & (c < e), -1, 0))


def run():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR"); sw = SS.switch_days(name, exch, h)
        for sname, df, k, tr, mx in (("S1", ST.three_hour_generic(h), 2.0, 2.0, 40), ("S2", SS.daily_from(h), 1.5, 3.0, 40)):
            df = df.reset_index(drop=True)
            swd = np.array([pd.Timestamp(x) in sw for x in df["time"].dt.normalize()])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in df["close"]])
            rows += [dict(r, strat=sname, name=name) for r in sim(df, bo_signal(df), k, tr, mx, swd, cost)]
        d = SRLV(SS.daily_from(h))
        c, pc = d["close"].values, d["close"].shift(1).values
        with np.errstate(invalid="ignore"):
            mb = np.where((c > d.pmh) & (pc <= d.pmh) & (d.wtr > 0) & (d.mtr > 0), 1,
                          np.where((c < d.pml) & (pc >= d.pml) & (d.wtr < 0) & (d.mtr < 0), -1, 0))
        swd = np.array([pd.Timestamp(x) in sw for x in d["time"].dt.normalize()])
        cost = np.array([INS.cost_points(name, p, 1.0) for p in d["close"]])
        rows += [dict(r, strat="S3", name=name) for r in sim(d, mb, 1.5, 2.0, 20, swd, cost, start=60)]
        print(name, flush=True)
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    for rr in man.itertuples():
        f1, fo = SR.DATA / f"{rr.name}_ONE_HOUR.csv", SR.DATA / f"{rr.name}_OI_ONE_DAY.csv"
        if not f1.exists():
            continue
        h = pd.read_csv(f1, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        d = SS.daily_from(h).reset_index(drop=True)
        day = d["time"].dt.normalize()
        swd = np.array([in_rollover_window(pd.Timestamp(x)) for x in day])
        cost = np.array([SC.cost_frac(p, rr.lot) for p in d["close"]])
        if fo.exists():
            oi = pd.read_csv(fo)
            o = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last().reindex(day)
            doi = o.pct_change().values; dp = d["close"].pct_change().values
            b = bo_signal(d)
            s4 = np.where((b > 0) & (dp > 0) & (np.nan_to_num(doi) >= 0.02), 1, np.where((b < 0) & (dp < 0) & (np.nan_to_num(doi) >= 0.02), -1, 0))
            rows += [dict(r, strat="S4", name=rr.name) for r in sim(d, s4, 2.0, None, 40, swd, cost, trail=3.0)]
        cl = d["close"]; e20 = I.ema(cl, 20); r5 = cl.pct_change(5)
        v = d["volume"].astype(float); vol = v > 1.5 * v.rolling(20).mean().shift(1)
        be = (pats(d)["bear_engulf"] & (cl > e20) & (r5 > 0) & vol).fillna(False).values
        rows += [dict(r, strat="S5", name=rr.name) for r in sim(d, np.where(be, -1, 0), 1.5, 1.0, 10, swd, cost, start=30)]
    return pd.DataFrame(rows)


def metrics(g, col="r1"):
    r = g[col].values
    if len(r) == 0:
        return {}
    w, l = r[r > 0], r[r <= 0]
    eq = np.cumsum(g.sort_values("time")[col].values)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    streak = mx = 0
    for x in g.sort_values("time")[col].values:
        streak = streak + 1 if x <= 0 else 0; mx = max(mx, streak)
    return dict(n=len(r), win=round(len(w) / len(r) * 100, 1), avg_win=round(w.mean(), 2) if len(w) else 0,
                avg_loss=round(l.mean(), 2) if len(l) else 0, exp=round(r.mean(), 3),
                pf=round(w.sum() / -l.sum(), 2) if l.sum() < 0 else None, maxdd_R=round(dd, 1), lose_streak=mx)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    T = run()
    T["year"] = pd.to_datetime(T["time"]).dt.year
    T["per"] = np.where(pd.to_datetime(T["time"]) < SPLIT, "design", "holdout")
    T.to_csv(OUT / "trades.csv.gz", index=False)
    lines = []
    for capped in (False, True):
        lines.append(f"\n##### {'WITH the 28-Oct stop-width cap' if capped else 'without the stop-width cap'}")
        for sname, G in T.groupby("strat"):
            if capped:
                G = G[G.slpct <= CAP[sname]]
            m1, m2 = metrics(G, "r1"), metrics(G, "r2")
            lines.append(f"\n{sname}: 1× costs {m1}\n    2× costs exp {m2.get('exp')} pf {m2.get('pf')}")
            for by in ("per", "year", "side", "regime"):
                t = G.groupby(by).apply(lambda x: pd.Series(dict(n=len(x), win=round((x.r1 > 0).mean() * 100, 1), exp1=round(x.r1.mean(), 3),
                                                                   exp2=round(x.r2.mean(), 3))), include_groups=False)
                lines.append(f"  by {by}: " + "; ".join(f"{i}: n{int(v.n)} w{v.win}% {v.exp1:+.3f}R ({v.exp2:+.3f})" for i, v in t.iterrows()))
            byi = G.groupby("name").r1.mean()
            lines.append(f"  instruments positive: {(byi > 0).sum()}/{len(byi)}")
    txt = "\n".join(lines)
    (OUT / "summary.txt").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()

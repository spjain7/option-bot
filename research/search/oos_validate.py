"""OOS-VALIDATE-001 (28-Oct-2026): independent chronological validation of the LIVE futures rules.

Why a new run (not a repeat): LIVE-AUDIT-001 was descriptive (design / hold-out only, no uncertainty) and its simulator
exited trades on the contract-switch day at the NEW contract's close. This study
  1. fixes roll handling: a trade open into a contract switch exits at the last close of the OLD contract, before the
     switch-day bar is looked at; no entry on a switch-day bar (signal bar or entry bar);
  2. uses a three-way chronological split  TRAIN < 2024-07-01 ≤ VALIDATION < 2025-07-01 ≤ TEST;
  3. reports 95 % month-block bootstrap intervals (trades in the same month are correlated, so months are resampled);
  4. runs ONE pre-registered parameter check (stop ATR × target R grid) selected on TRAIN only, checked on VALIDATION,
     reported once on TEST. The live (baseline) parameters are never changed by this script.
Strategies, entries, stop-before-target ordering, gap fills and costs (incl. slippage, 1× and 2×) as in live_audit.py.

Honest limits: the TEST period (Jul-2025 → Oct-2026) was already seen in aggregate in LIVE-AUDIT-001 and the hold-out of
earlier studies (PAT-002 / SR-001 chose the live exits with it visible). It is NOT a clean untouched sample; only data
after 28-Oct-2026 (forward paper record) is.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import strategy_search as SS, stock_search as SR, stock_check as SC  # noqa
from research.search.sr_levels import levels as SRLV  # noqa
from research.search.candle_rev import pats  # noqa
from research.search import live_audit as LA  # noqa
from alerts import stats as ST  # noqa
from alerts.stocks import in_rollover_window  # noqa

T1, T2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")
OUT = ROOT / "research/search/results_oos"
CAP = LA.CAP
LIVE = {"S1": (2.0, 2.0, 40), "S2": (1.5, 3.0, 40), "S3": (1.5, 2.0, 20)}     # stop ATR, target R, max candles
GRID_K, GRID_R = (1.5, 2.0, 2.5), (1.5, 2.0, 3.0)
TF = {"S1": "3h", "S2": "1d", "S3": "1m-breakout (daily bars)", "S4": "1d stock", "S5": "1d stock"}


def split(t):
    return np.where(t < T1, "1-train", np.where(t < T2, "2-valid", "3-test"))


def sim(df, sig, k_sl, tgt_r, maxh, swd, cost, trail=None, start=210, mkt=None):
    """Next-bar-open entry · stop checked before target · gap through stop fills at the open · roll exit at the old
    contract's last close · time exit at the close of the last allowed candle."""
    o, h, l, c = (df[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = I.atr(df, 14).values
    e200 = I.ema(df["close"], 200).values
    atrp = a / c
    med = pd.Series(atrp).rolling(250, min_periods=60).median().values
    t = df["time"].values
    out, busy = [], -1
    for i in np.flatnonzero(sig):
        if i < start or i <= busy or i >= len(c) - 1 or swd[i] or swd[i + 1] or not a[i] > 0:
            continue
        s = int(sig[i]); e0 = o[i + 1]; R = k_sl * a[i]
        st = e0 - s * R; tp = e0 + s * tgt_r * R if tgt_r else None
        best = e0; px = None; why = None; j = i + 1
        while j < len(c):
            if j > i + 1 and swd[j]:
                px, why, j = c[j - 1], "roll", j - 1; break          # last close of the old contract
            if (o[j] <= st) if s > 0 else (o[j] >= st): px, why = o[j], "stop-gap"; break
            if tp is not None and ((o[j] >= tp) if s > 0 else (o[j] <= tp)): px, why = o[j], "target-gap"; break  # gap through the target fills at the open (VERIFY-EXITS, 29-Oct)
            if (l[j] <= st) if s > 0 else (h[j] >= st): px, why = st, "stop"; break
            if tp is not None and ((h[j] >= tp) if s > 0 else (l[j] <= tp)): px, why = tp, "target"; break
            if j - (i + 1) >= maxh: px, why = c[j], "time"; break
            if trail:
                best = max(best, c[j]) if s > 0 else min(best, c[j])
                ns = best - s * trail * a[j]
                if s * (ns - st) > 0: st = ns
            j += 1
        if px is None: px, why, j = c[-1], "open-at-end", len(c) - 1
        day = pd.Timestamp(t[i]).normalize()
        out.append(dict(time=pd.Timestamp(t[i]), side="BUY" if s > 0 else "SELL", exit=why,
                        r1=(s * (px - e0) - cost[i]) / R, r2=(s * (px - e0) - 2 * cost[i]) / R, slpct=R / e0 * 100,
                        regime=("trend" if abs(c[i] - e200[i]) > 2 * a[i] else "range") + "/" + ("hi-vol" if atrp[i] > med[i] else "lo-vol"),
                        market=(mkt.get(day, "n/a") if mkt is not None else "n/a"), bars=j - i))
        busy = j
    return out


def nifty_regime():
    d = SS.daily_from(SS.load("NFO", "NIFTY", "ONE_HOUR"))
    e = I.ema(d["close"], 200)
    r = np.where(d["close"] > e, "NIFTY>EMA200", "NIFTY<EMA200")
    # regime known at the close of the PREVIOUS trading day is used (no look-ahead for intraday signals)
    ser = pd.Series(r, index=d["time"].dt.normalize())
    days = pd.date_range(ser.index.min(), ser.index.max() + pd.Timedelta(days=7))
    full = ser.reindex(days).shift(1).ffill()          # a calendar day -> regime of the last close strictly before it
    return full.dropna().to_dict()


def index_mcx(mkt, legacy=False, params=None):
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR"); sw = SS.switch_days(name, exch, h)
        frames = {"S1": ST.three_hour_generic(h).reset_index(drop=True), "S2": SS.daily_from(h).reset_index(drop=True)}
        d = SRLV(SS.daily_from(h)).reset_index(drop=True)
        c, pc = d["close"].values, d["close"].shift(1).values
        with np.errstate(invalid="ignore"):
            mb = np.where((c > d.pmh) & (pc <= d.pmh) & (d.wtr > 0) & (d.mtr > 0), 1,
                          np.where((c < d.pml) & (pc >= d.pml) & (d.wtr < 0) & (d.mtr < 0), -1, 0))
        frames["S3"] = d
        for sname, df in frames.items():
            swd = np.array([pd.Timestamp(x) in sw for x in df["time"].dt.normalize()])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in df["close"]])
            sig = mb if sname == "S3" else LA.bo_signal(df)
            for k, r, mx in (params[sname] if params else [LIVE[sname]]):
                if legacy:
                    res = LA.sim(df, sig, k, r, mx, swd, cost, start=60 if sname == "S3" else 210)
                else:
                    res = sim(df, sig, k, r, mx, swd, cost, start=60 if sname == "S3" else 210, mkt=mkt)
                rows += [dict(x, strat=sname, name=name, k=k, tr=r) for x in res]
    return pd.DataFrame(rows)


def stocks(mkt):
    rows = []
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
            b = LA.bo_signal(d)
            s4 = np.where((b > 0) & (dp > 0) & (np.nan_to_num(doi) >= 0.02), 1, np.where((b < 0) & (dp < 0) & (np.nan_to_num(doi) >= 0.02), -1, 0))
            res = sim(d, s4, 2.0, None, 40, swd, cost, trail=3.0, mkt=mkt)
            for x in res:
                ii = int(np.searchsorted(d["time"].values, np.datetime64(x["time"])))
                x["doi"] = float(doi[ii]) if ii < len(doi) else np.nan
            rows += [dict(x, strat="S4", name=rr.name, k=2.0, tr=None) for x in res]
        cl = d["close"]; e20 = I.ema(cl, 20); r5 = cl.pct_change(5)
        v = d["volume"].astype(float); vol = v > 1.5 * v.rolling(20).mean().shift(1)
        be = (pats(d)["bear_engulf"] & (cl > e20) & (r5 > 0) & vol).fillna(False).values
        rows += [dict(x, strat="S5", name=rr.name, k=1.5, tr=1.0) for x in sim(d, np.where(be, -1, 0), 1.5, 1.0, 10, swd, cost, start=30, mkt=mkt)]
    return pd.DataFrame(rows)


# ─────────────── statistics ───────────────
def boot_ci(g, col="r1", n=2000, seed=7):
    """95 % interval of the mean R by resampling calendar MONTHS (keeps same-month trades together)."""
    if len(g) < 5:
        return (np.nan, np.nan)
    m = g.assign(_m=pd.to_datetime(g["time"]).dt.to_period("M"))
    groups = [x[col].values for _, x in m.groupby("_m")]
    rng = np.random.default_rng(seed)
    k = len(groups); means = []
    sums = np.array([x.sum() for x in groups]); cnts = np.array([len(x) for x in groups])
    for _ in range(n):
        idx = rng.integers(0, k, k)
        means.append(sums[idx].sum() / max(cnts[idx].sum(), 1))
    return tuple(np.round(np.percentile(means, [2.5, 97.5]), 3))


def metrics(g):
    if len(g) == 0:
        return dict(n=0)
    r = g["r1"].values; r2 = g["r2"].values
    w, l = r[r > 0], r[r <= 0]
    eq = np.cumsum(g.sort_values("time")["r1"].values)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    lo, hi = boot_ci(g)
    return dict(n=len(r), win=round(len(w) / len(r) * 100, 1), exp1=round(r.mean(), 3), exp2=round(r2.mean(), 3),
                ci=f"[{lo:+.2f}, {hi:+.2f}]" if lo == lo else "n/a",
                pf=round(w.sum() / -l.sum(), 2) if l.sum() < 0 else np.nan, dd=round(dd, 1))


def table(G, by):
    rows = []
    for key, g in G.groupby(by, sort=True):
        rows.append(dict(zip(by if isinstance(by, list) else [by], key if isinstance(key, tuple) else [key]), **metrics(g)))
    return pd.DataFrame(rows)


def md(df):
    return df.to_markdown(index=False) if len(df) else "_none_"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mkt = nifty_regime()
    A = index_mcx(mkt)
    B = stocks(mkt)
    T = pd.concat([A, B], ignore_index=True)
    T["time"] = pd.to_datetime(T["time"]); T["year"] = T["time"].dt.year; T["split"] = split(T["time"])
    T["capped"] = T.apply(lambda r: r.slpct <= CAP[r.strat], axis=1)
    T.to_csv(OUT / "trades.csv.gz", index=False)
    L = ["# OOS-VALIDATE-001 – generated tables (baseline = live rules incl. live stop-width cap)\n",
         f"Split: train < {T1.date()} ≤ validation < {T2.date()} ≤ test. R = stop distance. exp1/exp2 = mean R at 1×/2× costs. "
         "ci = 95 % month-block bootstrap of exp1. dd = max drawdown in R (all trades of the group in time order).\n"]
    C = T[T.capped]
    # roll-handling comparison
    Lg = index_mcx(mkt, legacy=True)
    Lg = Lg[Lg.apply(lambda r: r.slpct <= CAP[r.strat], axis=1)]
    L.append("## Roll handling: live_audit simulator vs corrected (index + MCX, capped)\n")
    L.append(md(pd.DataFrame([dict(strat=s, legacy_n=len(Lg[Lg.strat == s]), legacy_exp1=round(Lg[Lg.strat == s].r1.mean(), 3),
                                    fixed_n=len(C[C.strat == s]), fixed_exp1=round(C[C.strat == s].r1.mean(), 3),
                                    roll_exits=int((C[C.strat == s].exit == "roll").sum()))
                               for s in ("S1", "S2", "S3")])) + "\n")
    for s in ("S1", "S2", "S3", "S4", "S5"):
        G = C[C.strat == s]
        L.append(f"\n## {s} – {TF[s]}\n")
        L.append("### by split × side\n" + md(table(G, ["split", "side"])) + "\n")
        L.append("### by split (both sides)\n" + md(table(G, "split")) + "\n")
        L.append("### by year × side\n" + md(table(G, ["year", "side"])) + "\n")
        L.append("### by instrument regime × side\n" + md(table(G, ["regime", "side"])) + "\n")
        L.append("### by market regime (NIFTY vs EMA200, previous close) × side\n" + md(table(G, ["market", "side"])) + "\n")
        L.append("### by exit reason\n" + md(table(G, "exit")) + "\n")
        if s in ("S1", "S2", "S3"):
            L.append("### by instrument × side\n" + md(table(G, ["name", "side"])) + "\n")
        else:
            bi = G.groupby(["side", "name"]).r1.mean().groupby("side").agg(lambda x: f"{(x > 0).sum()}/{len(x)} positive")
            L.append("### instruments with positive mean R\n" + "; ".join(f"{k}: {v}" for k, v in bi.items()) + "\n")
    # stock OI BUY deep-dive
    G = C[(C.strat == "S4") & (C.side == "BUY")].copy()
    G["oi_bucket"] = pd.cut(G["doi"], [0.0, 0.04, 0.08, 10], labels=["OI +2–4%", "OI +4–8%", "OI >8%"], include_lowest=True)
    G["hold"] = pd.cut(G["bars"], [0, 5, 15, 100], labels=["≤5 d", "6–15 d", ">15 d"])
    L.append("\n## S4 stock OI BUY – deep dive\n")
    for by in ("split", "market", "oi_bucket", "exit", "hold", "year"):
        L.append(f"### by {by}\n" + md(table(G, by)) + "\n")
    # pre-registered parameter check (train selection only)
    grid = {s: [(k, r, LIVE[s][2]) for k in GRID_K for r in GRID_R] for s in ("S1", "S2", "S3")}
    P = index_mcx(mkt, params=grid)
    P["time"] = pd.to_datetime(P["time"]); P["split"] = split(P["time"])
    P = P[P.apply(lambda r: r.slpct <= CAP[r.strat], axis=1)]
    L.append("\n## Pre-registered parameter check (selection on TRAIN exp2 only, min 30 trades; baseline = live)\n")
    rows = []
    for s in ("S1", "S2", "S3"):
        tr = P[(P.strat == s) & (P.split == "1-train")].groupby(["k", "tr"]).agg(n=("r2", "size"), exp2=("r2", "mean")).reset_index()
        tr = tr[tr.n >= 30]
        best = tr.sort_values("exp2", ascending=False).iloc[0] if len(tr) else None
        for lab, (k, r) in (("live", LIVE[s][:2]), ("train-best", (best.k, best.tr) if best is not None else (None, None))):
            if k is None:
                continue
            g = P[(P.strat == s) & (P.k == k) & (P.tr == r)]
            for sp in ("1-train", "2-valid", "3-test"):
                m = metrics(g[g.split == sp])
                rows.append(dict(strat=s, choice=lab, k=k, tr=r, split=sp, **m))
    L.append(md(pd.DataFrame(rows)) + "\n")
    (OUT / "tables.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()

"""Research cycle 2 (owner 11-Nov) – shared pieces: market loaders with context (market regime, breadth, sector), higher-
timeframe alignment, VWAP, pre-registered filters, and the evaluation protocol.

Protocol for every filter test (fixed before looking at OOS):
  * base event and exits are fixed; a filter is added ONE at a time (no stacking search)
  * SELECTION uses DEV and VALID only: a filter is "selected" if it raises avg R vs the base in BOTH DEV and VALID
  * EVIDENCE: OOS avg R of the filtered set minus the excluded set (Welch t), and OOS filtered vs base; BH-FDR 10 % over
    every filter x market x timeframe tested; walk-forward (expanding, yearly): the filter is used in year Y only if its
    cumulative gain over the base in all years before Y is positive
  * benchmarks: the unfiltered base, and the same exits entered every 10th bar (drift)
All look-ups use information known at the decision bar's close (higher-timeframe values are from the LAST COMPLETED
higher bar, cross-sectional values from the same date)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.rsirev import run as RR  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)
UNIV = ROOT / "research/shadow/universe.csv"
METALS = {"GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"}


# ───────────────────────── cross-sectional context ─────────────────────────
_CS = {}


def cash_context():
    """daily: market regime (EW top-100 index vs EMA200), breadth (% eligible above EMA50), sector trend and sector RS."""
    if "cash" in _CS:
        return _CS["cash"]
    from research.cashq import data as D
    W = D.daily_panel()
    c, el = W["close"], W["elig"].astype(bool)
    above = (c > c.ewm(span=50, adjust=False).mean()).where(el)
    breadth = above.mean(axis=1)
    mk = W["market"]["close"]
    reg = pd.DataFrame(dict(mkt_up=mk > mk.ewm(span=200, adjust=False).mean(), mkt_ma100=mk > mk.rolling(100).mean(), breadth=breadth))
    imap = dict(pd.read_csv(UNIV)[["symbol", "industry"]].fillna("").values)
    sec = W["symbol"].map(imap).fillna("")
    ret = c.pct_change(fill_method=None).where(el)
    sidx = {s: ret[list(cols)].mean(axis=1).fillna(0).add(1).cumprod() for s, cols in sec.groupby(sec).groups.items() if s}
    S = pd.DataFrame(sidx)
    s_up = S > S.ewm(span=50, adjust=False).mean()
    s_rs = (S.pct_change(63) .rank(axis=1, pct=True))
    rs = c.pct_change(63, fill_method=None).sub(mk.pct_change(63), axis=0).where(el).rank(axis=1, pct=True)
    sym_rs = {str(W["symbol"][k]): rs[k] for k in rs.columns}
    _CS["cash"] = dict(reg=reg, sector_of=imap, s_up=s_up, s_rs=s_rs, rs=sym_rs, W=W)
    return _CS["cash"]


def weekly_last(s):
    return s.resample("W-FRI").last()


# ───────────────────────── per-frame filters ─────────────────────────
def htf_up(b, tf):
    """higher-timeframe trend from the last COMPLETED higher bar: 1h/3h -> daily close > daily EMA20 (previous day);
    1d -> weekly close > weekly EMA20 (previous week); 1w -> monthly close > 10-month EMA (previous month)."""
    t = pd.to_datetime(b["time"]); c = pd.Series(b["close"].astype(float).values, index=t)
    if tf in ("1h", "3h"):
        d = c.groupby(t.dt.normalize().values).last(); up = (d > d.ewm(span=20, adjust=False).mean()).shift(1)
        return t.dt.normalize().map(up).fillna(False).astype(bool).values
    if tf == "1d":
        w = c.resample("W-FRI").last(); up = (w > w.ewm(span=20, adjust=False).mean()).shift(1)
        return pd.Series(t.values).map(lambda x: up.asof(x)).fillna(False).astype(bool).values
    m = c.resample("ME").last(); up = (m > m.ewm(span=10, adjust=False).mean()).shift(1)
    return pd.Series(t.values).map(lambda x: up.asof(x)).fillna(False).astype(bool).values


def vwap_ok(b, tf, d5=None):
    """close above VWAP at the decision bar: intraday = session VWAP from 5-minute data (MCX) or the bars themselves;
    daily / weekly = 20-bar rolling volume-weighted price."""
    h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("high", "low", "close", "volume"))
    tp = (h + l + c) / 3
    if tf in ("1h", "3h"):
        day = pd.to_datetime(b["time"]).dt.normalize().values
        pv, vv = (tp * v).groupby(day).cumsum(), v.groupby(day).cumsum()
        vw = pv / vv.replace(0, np.nan)
    else:
        vw = (tp * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    return (c > vw).fillna(False).values


def filters(b, tf, ctx=None):
    """pre-registered filters (one at a time). ctx: dict of date-aligned arrays for this frame (sector, breadth, regime)."""
    o, h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("open", "high", "low", "close", "volume"))
    ad, atr = RR.adx(h, l, c)
    e20, e50, e200 = (c.ewm(span=n, adjust=False).mean() for n in (20, 50, 200))
    rv = v / v.rolling(20).mean().shift(1)
    F = {"adx25": (ad >= 25).values, "adx35": (ad >= 35).values, "adx_rising": (ad > ad.shift(3)).values,
         "ema_stack": ((c > e20) & (e20 > e50) & (e50 > e200)).values, "rvol1.5": (rv >= 1.5).values, "rvol2": (rv >= 2.0).values,
         "breakout20": (c > h.shift(1).rolling(20).max()).values, "close_top_quarter": ((c - l) >= 0.75 * (h - l)).values,
         "vwap": vwap_ok(b, tf), "htf_up": htf_up(b, tf)}
    for k, x in (ctx or {}).items():
        F[k] = np.asarray(x, bool)
    return {k: np.nan_to_num(np.asarray(x, float)).astype(bool) for k, x in F.items()}


def base_events(b):
    """B1: RSI(14) crosses to >= 75 (momentum continuation BUY, the RSIREV/RSIDIV 'cross_in:continuation' event);
    B2: S10 (RSI >= 75 + ADX >= 25 + close > EMA50 + 20-bar breakout)."""
    s, conf, reg, risk = RR.strategies(b, 3)
    c = b["close"].astype(float).reset_index(drop=True); r = E.rsi_of(c)
    b1 = ((r >= 75) & (r.shift(1) < 75)).fillna(False).values
    return {"B1": b1, "B2": s["S10"]}, risk, conf


def confirm_of(sig, b, side=1):
    h, l, c = (b[x].astype(float).values for x in ("high", "low", "close"))
    n = len(c); z = np.zeros(n, bool)
    for i in np.where(sig)[0]:
        for j in (i + 1, i + 2):
            if j < n and ((side > 0 and c[j] > h[i]) or (side < 0 and c[j] < l[i])):
                z[j] = True; break
    return z


# ───────────────────────── evaluation ─────────────────────────
def per_period(T, cuts):
    lab = E.periods(T.entry.values, cuts) if len(T) else np.array([])
    out = {}
    for p_, _ in cuts:
        r = T.netR.values[lab == p_] if len(T) else np.array([])
        out[p_] = (len(r), float(r.mean()) if len(r) else np.nan)
    return out


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 5 or len(b) < 5:
        return np.nan
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return (a.mean() - b.mean()) / se if se > 0 else np.nan


def walk_forward(Tb, Tf, years):
    """yearly expanding: use the filter in year Y if its cumulative gain (filtered avg R - base avg R, summed over prior
    years with trades) is > 0. -> (chained avg R per trade with the rule, base avg R, years used)."""
    yb = Tb.groupby(pd.to_datetime(Tb.entry).dt.year).netR; yf = Tf.groupby(pd.to_datetime(Tf.entry).dt.year).netR
    gain, used, rs, rb = 0.0, 0, [], []
    for y in years:
        use = gain > 0
        if y in yb.groups:
            rb.extend(yb.get_group(y).values)
            rs.extend((yf.get_group(y).values if (use and y in yf.groups) else (yb.get_group(y).values if not use else [])))
            used += int(use)
        if y in yb.groups and y in yf.groups:
            gain += yf.get_group(y).mean() - yb.get_group(y).mean()
    return (float(np.mean(rs)) if rs else np.nan), (float(np.mean(rb)) if rb else np.nan), used, len(rs)


def test_filters(pool, base_key, Fkeys, cuts, hold, R, tag):
    """pool idx holds base_key and (base_key + filter) keys -> one row per filter."""
    Tb = pool.run(base_key, R, hold); rows = []
    if len(Tb) < 30:
        return rows, Tb
    pb = per_period(Tb, cuts)
    years = sorted(pd.to_datetime(Tb.entry).dt.year.unique())
    for f in Fkeys:
        k = (base_key[0] + "+" + f,) + base_key[1:]
        if k not in pool.idx:
            rows.append(dict(tag, filter=f, n=0)); continue
        Tf = pool.run(k, R, hold)
        pf = per_period(Tf, cuts)
        oos0 = np.datetime64(cuts[-1][1])
        inn = set(zip(Tf.name, Tf.entry))
        Tx = Tb[[(n_, e_) not in inn for n_, e_ in zip(Tb.name, Tb.entry)]]
        a = Tf.netR[Tf.entry.values >= oos0]; bx = Tx.netR[Tx.entry.values >= oos0]
        wf, wb, used, nwf = walk_forward(Tb, Tf, years)
        sel = all(np.isfinite(pf[p_][1]) and pf[p_][1] > pb[p_][1] and pf[p_][0] >= 20 for p_, _ in cuts[:2])
        rows.append(dict(tag, filter=f, base_n=len(Tb), n=len(Tf), keep_share=round(len(Tf) / len(Tb), 3),
                         **{f"{p_}_base_R": round(pb[p_][1], 3) for p_, _ in cuts}, **{f"{p_}_n": pf[p_][0] for p_, _ in cuts},
                         **{f"{p_}_R": round(pf[p_][1], 3) if np.isfinite(pf[p_][1]) else np.nan for p_, _ in cuts},
                         selected_on_dev_val=bool(sel), oos_filtered_minus_excluded=round(float(a.mean() - bx.mean()), 3) if len(a) and len(bx) else np.nan,
                         oos_welch_t=round(welch(a, bx), 2) if np.isfinite(welch(a, bx)) else np.nan, oos_excluded_n=len(bx),
                         wf_R=round(wf, 3), wf_base_R=round(wb, 3), wf_years_used=used, wf_trades=nwf))
    return rows, Tb


def bh(p, q=0.10):
    p = np.asarray(p, float); ok = np.isfinite(p); out = np.zeros(len(p), bool)
    if ok.any():
        out[np.where(ok)[0]] = E.bh(p[ok], q)
    return out

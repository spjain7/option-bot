"""EQ-BTST-001 – NSE cash BTST / short positional BUY setups (10-Nov-2026, owner: "how can we find BTST or positional cash
stock – make a setup"). BUY only (cash: no overnight short). Alerts only.

Data: official NSE cash bhavcopies 2005-01 … 2026-11 (research/data/nse_cm, eq_bhav.adjusted: exact corporate-action
adjustment, delisted stocks included, ETFs / fund units excluded). Point-in-time universe on day t: 60-session median
turnover (to t-1) >= ₹25 cr, close >= ₹50, >= 250 sessions of history.
Signal on day t's close (in practice: scan at 15:20-15:25 and buy before 15:30; NOTE the NSE closing price is the
15:00-15:30 VWAP, so the backtest entry is an approximation – checked separately on 5-minute data, stage 2).
Exits: O1 next open (classic BTST) · C1 next close · C3 / C5 close after 3 / 5 sessions. Trades across a corporate
action (factor != 1 inside the hold) and likely upper-circuit closes (close = high and day move > 4.5 %) are excluded.
Costs: delivery round trip 0.393 % incl. 0.05 %/side slippage (eq_data.cost_frac('delivery')).
Pre-registered setups (no tuning after looking at OOS):
  S1 STRONG   day +2 %, close in the top 20 % of the range, volume >= 1.5x 20-day average
  S2 SURGE    day +4 %, close in the top 20 %, volume >= 2x
  S3 BO20     close at a 20-session closing high (first in 5 sessions), close top 30 %, volume >= 1.5x
  S4 BO52W    close at a 252-session closing high (first in 20 sessions), close top 30 %, volume >= 1.5x
  S5 RS       63-day relative strength top 20 % of the universe, day +1.5 %, close top 20 %
  S6 DIPBUY   RS top 30 %, close above EMA50, 3 down closes then an up close in the top 20 % of the range
  S7 FLUSH    day -4 % or worse, close in the top 40 % of the range (buyers came back), volume >= 1.5x
  × market filter {off, EW top-100 index above its 100-session average} × exit {O1, C1, C3, C5} = 56 variants.
Control: same-day universe average of the same exit (excess = signal − universe); random matched picks for the passers.
Validation: DEV 2005-2015 / OOS 2016-2026 + 4 blocks; t on day-averaged returns; BH-FDR over 56.
PASS = net > 0 in DEV and OOS, excess > 0 in both, every block net > 0, OOS n >= 300, OOS q < 0.10.
python research/eqbtst/btst.py"""
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_bhav as EB  # noqa: E402
OUT = Path(__file__).resolve().parent
COST = 0.00393
BLOCKS = [("2005", "2010"), ("2011", "2015"), ("2016", "2020"), ("2021", "2026")]


def wide(A):
    keys = list(A)
    idx = pd.DatetimeIndex(sorted({t for d in A.values() for t in d["time"]}))
    W = {}
    for f in ("open", "high", "low", "close", "value", "volume", "factor"):
        W[f] = pd.DataFrame({k: pd.Series(A[k][f].values, index=pd.DatetimeIndex(A[k]["time"])) for k in keys}).reindex(idx)
    return W


def build(W, mk):
    O, H, L, C, V, F = (W[x] for x in ("open", "high", "low", "close", "value", "factor"))
    n_hist = C.notna().cumsum()
    to60 = V.rolling(60, min_periods=40).median().shift(1)
    elig = (to60 >= 25e7) & (C >= 50) & (n_hist >= 250)
    r1 = C / C.shift(1) - 1
    rng = (H - L).where(H > L)
    clv = (C - L) / rng
    vr = V / V.rolling(20, min_periods=15).mean().shift(1)
    hi20 = C >= C.rolling(20, min_periods=20).max()
    hi20_first = hi20 & ~(hi20.shift(1).rolling(5, min_periods=1).max().astype(bool))
    hi252 = C >= C.rolling(252, min_periods=240).max()
    hi252_first = hi252 & ~(hi252.shift(1).rolling(20, min_periods=1).max().astype(bool))
    r63 = C.shift(0) / C.shift(63) - 1
    rs = r63.where(elig).rank(axis=1, pct=True)
    ema50 = C.ewm(span=50, adjust=False, min_periods=50).mean()
    dn = (C < C.shift(1))
    dip = dn.shift(1) & dn.shift(2) & dn.shift(3) & (r1 > 0)
    circuit = (C >= H * 0.9995) & (r1 > 0.045)
    ok = elig & ~circuit & C.notna()
    S = {
        "S1_STRONG": ok & (r1 >= 0.02) & (clv >= 0.8) & (vr >= 1.5),
        "S2_SURGE": ok & (r1 >= 0.04) & (clv >= 0.8) & (vr >= 2.0),
        "S3_BO20": ok & hi20_first & (clv >= 0.7) & (vr >= 1.5),
        "S4_BO52W": ok & hi252_first & (clv >= 0.7) & (vr >= 1.5),
        "S5_RS": ok & (rs >= 0.8) & (r1 >= 0.015) & (clv >= 0.8),
        "S6_DIPBUY": ok & (rs >= 0.7) & (C > ema50) & dip & (clv >= 0.8),
        "S7_FLUSH": ok & (r1 <= -0.04) & (clv >= 0.6) & (vr >= 1.5),
    }
    ca = (F.fillna(1.0) != 1.0)
    X = {}
    for ex, (px, h) in {"O1": (O, 1), "C1": (C, 1), "C3": (C, 3), "C5": (C, 5)}.items():
        ret = px.shift(-h) / C - 1
        bad = ca.shift(-1).fillna(False).astype(bool)
        for j in range(2, h + 1):
            bad |= ca.shift(-j).fillna(False).astype(bool)
        X[ex] = ret.where(~bad & ok)
    mkt_on = (mk.set_index("time")["close"] > mk.set_index("time")["close"].rolling(100).mean()).reindex(C.index).fillna(False)
    return S, X, mkt_on, ok, dict(r1=r1, clv=clv, vr=vr, rs=rs)


def daystat(sig, ret, base, mask_days):
    s = sig & ret.notna()
    s = s & pd.DataFrame(np.repeat(mask_days.values[:, None], s.shape[1], 1), index=s.index, columns=s.columns)
    r = ret.where(s)
    n_day = s.sum(1)
    d_mean = r.mean(1)[n_day > 0]
    ex = (d_mean - base.reindex(d_mean.index))
    return s, r, d_mean, ex


def evaluate(S, X, mkt_on):
    rows = []
    for ex, ret in X.items():
        base = ret.mean(1)                                          # same-day universe average (control)
        for name, sig in S.items():
            for mf in (0, 1):
                md = mkt_on if mf else pd.Series(True, index=ret.index)
                s, r, dm, exs = daystat(sig, ret, base, md)
                vals = r.stack().dropna()
                row = dict(setup=name, mkt=mf, exit=ex)
                for lab, (a, b) in [("DEV", ("2005", "2015")), ("OOS", ("2016", "2026"))] + [(f"B{i}", bl) for i, bl in enumerate(BLOCKS)]:
                    v = vals[(vals.index.get_level_values(0) >= a) & (vals.index.get_level_values(0) <= b + "-12-31")]
                    row[f"{lab}_n"] = len(v)
                    row[f"{lab}_net"] = round((v.mean() - COST) * 100, 3) if len(v) else np.nan    # % per trade
                    if lab in ("DEV", "OOS"):
                        e = exs[(exs.index >= a) & (exs.index <= b + "-12-31")]
                        row[f"{lab}_win"] = round(((v - COST) > 0).mean() * 100, 1) if len(v) else np.nan
                        row[f"{lab}_excess"] = round(e.mean() * 100, 3) if len(e) else np.nan
                        dd = dm[(dm.index >= a) & (dm.index <= b + "-12-31")] - COST
                        row[f"{lab}_t"] = round(dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd))), 2) if len(dd) > 2 else np.nan
                        row[f"{lab}_p"] = float(stats.t.sf(row[f"{lab}_t"], len(dd) - 1)) if len(dd) > 2 else 1.0
                        row[f"{lab}_perday"] = round(len(v) / max(len(dd), 1), 2)
                rows.append(row)
    R = pd.DataFrame(rows)
    p = R["OOS_p"].values; o = np.argsort(p); q = np.empty_like(p); m = len(p)
    q[o] = np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]
    R["OOS_q"] = np.round(np.minimum(q, 1), 4)
    R["PASS"] = ((R.DEV_net > 0) & (R.OOS_net > 0) & (R.DEV_excess > 0) & (R.OOS_excess > 0) & (R.OOS_n >= 300) &
                 (R.OOS_q < 0.10) & (R[[f"B{i}_net" for i in range(4)]] > 0).all(1))
    return R


if __name__ == "__main__":
    A = pickle.loads((ROOT / "research/data/nse_cm/_adjusted.pkl").read_bytes())
    W = wide(A)
    mk = EB.market(A)
    S, X, mkt_on, ok, feat = build(W, mk)
    base = {ex: dict(DEV=round((r.loc[:"2015"].stack().mean() - COST) * 100, 3), OOS=round((r.loc["2016":].stack().mean() - COST) * 100, 3))
            for ex, r in X.items()}
    print("universe (every eligible stock-day) net % per trade:", base)
    R = evaluate(S, X, mkt_on)
    R.to_csv(OUT / "RESULTS_btst.csv", index=False)
    cols = ["setup", "mkt", "exit", "DEV_n", "DEV_net", "DEV_excess", "OOS_n", "OOS_perday", "OOS_win", "OOS_net", "OOS_excess", "OOS_t",
            "OOS_q", "B0_net", "B1_net", "B2_net", "B3_net", "PASS"]
    print(R.sort_values("OOS_net", ascending=False)[cols].head(25).to_string(index=False))
    print("PASS:", int(R.PASS.sum()))
    pickle.dump(dict(S=S, X=X, mkt_on=mkt_on, feat=feat, base=base), open(OUT / "_btst_cache.pkl", "wb"))

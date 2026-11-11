"""RSIDIV-CM – NSE cash equities, BUY only (delivery cannot be shorted), daily and weekly, 2005-01 … 2026-11
(owner 11-Nov priority 4). Point-in-time universe from the cash bhavcopy incl. delisted stocks (60-session median
turnover >= ₹25 cr, close >= ₹50, >= 250 sessions of history); corporate-action adjusted prices; delivery cost 0.393 %
round trip incl. 0.05 % slippage per side.
Contexts added to the common ones:
  liq_top / liq_bottom  – 60-session median turnover in the top / bottom third of that day's eligible stocks
  rs_strong / rs_weak   – 63-session return minus the market's (EW index of the 100 most-traded stocks) in the top 30 % /
                          bottom 30 % of that day's eligible stocks
  sector_up / sector_down – the stock's sector (equal-weight index of its eligible sector peers) above / below its
                          50-session EMA. SECTOR MAP = today's NIFTY 500 industry list (20 sectors); stocks not in it
                          (mostly delisted) have no sector and are left out of these two contexts only.
  trend_up / trend_down – close vs EMA200.
Periods: DEV 2005–2014 · VALID 2015–2019 · OOS 2020–2026.          python -m research.rsidiv.cash"""
import gc
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.cashq import data as D  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
CUTS = [("DEV", "2005-01-01"), ("VAL", "2015-01-01"), ("OOS", "2020-01-01")]
COST = 0.00393
UNIV = ROOT / "research/data/angel/NSE_EQ/universe.csv"


def contexts(W, weekly=False):
    c, el = W["close"], W["elig"].astype(bool)
    ret = c.pct_change(fill_method=None)
    mk = W["market"]["close"] if "market" in W and isinstance(W["market"], pd.DataFrame) else ret.where(el).mean(axis=1).add(1).cumprod()
    n = 13 if weekly else 63
    rs = c.pct_change(n, fill_method=None).sub(mk.pct_change(n, fill_method=None), axis=0).where(el)
    rsr = rs.rank(axis=1, pct=True)
    to = W["value"].rolling(12 if weekly else 60, min_periods=8 if weekly else 40).median().shift(1).where(el)
    tor = to.rank(axis=1, pct=True)
    imap = dict(pd.read_csv(UNIV)[["symbol", "industry"]].fillna("").values)
    sec = W["symbol"].map(imap).fillna("")
    sec_up = pd.DataFrame(False, index=c.index, columns=c.columns); sec_dn = sec_up.copy()
    for s, cols in sec.groupby(sec).groups.items():
        if not s:
            continue
        cols = list(cols)
        ix = ret[cols].where(el[cols]).mean(axis=1).fillna(0).add(1).cumprod()
        e = ix.ewm(span=10 if weekly else 50, adjust=False).mean()
        sec_up.loc[:, cols] = np.repeat((ix > e).values[:, None], len(cols), axis=1)
        sec_dn.loc[:, cols] = np.repeat((ix < e).values[:, None], len(cols), axis=1)
    ema = c.ewm(span=40 if weekly else 200, adjust=False).mean()
    return dict(liq_top=tor >= 2 / 3, liq_bottom=tor <= 1 / 3, rs_strong=rsr >= 0.7, rs_weak=rsr <= 0.3,
                sector_up=sec_up, sector_down=sec_dn, trend_up=c > ema, trend_down=c < ema), int((sec != "").sum()), len(sec)


def build(tf):
    W = D.daily_panel()
    if tf == "1w":
        mk = W["market"]; W = D.weekly(W); W["market"] = mk.resample("W-FRI").last().reindex(W["close"].index, method="ffill")
    C, with_sec, cols = contexts(W, weekly=tf == "1w")
    pool = E.Pool(); gid = 0
    idx = W["close"].index
    for k in W["close"].columns:
        cl = W["close"][k]
        ok = cl.notna().values
        if ok.sum() < 300 or not W["elig"][k].fillna(False).astype(bool).any():
            continue
        b = pd.DataFrame(dict(time=idx[ok], open=W["open"][k].values[ok], high=W["high"][k].values[ok], low=W["low"][k].values[ok],
                              close=cl.values[ok], volume=W["volume"][k].values[ok]))
        bad = (b[["open", "high", "low", "close"]] <= 0).any(axis=1) | (b.high < b.low)
        b.loc[bad, ["open", "high", "low"]] = np.nan
        for col in ("open", "high", "low"):                              # unusable OHLC -> the close (never invented ranges)
            b[col] = b[col].fillna(b["close"])
        extra = {n: m[k].fillna(False).astype(bool).values[ok] for n, m in C.items()}
        S, risk = E.study(b, E.K_BY_TF[tf], extra=extra, sides=(1,))
        el = W["elig"][k].fillna(False).astype(bool).values[ok]
        S = {kk: e & el for kk, e in S.items() if kk[-1] == 1}
        pool.add(b, S, risk, gid, np.full(len(b), COST), np.zeros(len(b), np.int64), str(W["symbol"][k])); gid += 1
        if gid % 300 == 0:
            print(f"  {tf}: {gid} stocks", flush=True)
    del W, C; gc.collect()
    print(f"{tf}: {gid} stocks · sector known for {with_sec} of {cols}", flush=True)
    return pool.freeze()


def main():
    t0 = time.time(); Ls, Ts = [], []
    for tf, hold in (("1d", 15), ("1w", 10)):
        pool = build(tf)
        keys = sorted(k for k in pool.idx if k[0] in ("RSI", "DIV"))
        L, T = E.evaluate(pool, keys, CUTS, hold, tf, "NSE_CASH")
        B = E.baselines(pool, CUTS, hold, tf, "NSE_CASH", sides=(1,))
        Ls += [L, B]; Ts.append(T)
        print(f"{tf}: {len(L)} variants · PASS {int(L.PASS.sum())} · PASS+FDR {int((L.PASS & L.FDR10).sum())} · {time.time() - t0:.0f}s", flush=True)
        del pool; gc.collect()
    L = pd.concat(Ls, ignore_index=True); T = pd.concat(Ts, ignore_index=True)
    L.to_csv(OUT / "cash_variants.csv", index=False); T.to_csv(OUT / "cash_trades.csv.gz", index=False, compression="gzip")
    print(L[L.family == "BASE"][["tf", "side", "target_R", "DEV_R", "VAL_R", "OOS_R", "all_n"]].to_string(index=False))
    pd.set_option("display.width", 250)
    cols = ["tf", "family", "event", "context", "side", "target_R", "DEV_n", "DEV_R", "VAL_n", "VAL_R", "OOS_n", "OOS_R", "OOS_PF", "all_win", "t_day", "FDR10", "HOLM5", "names_pos", "names"]
    print(L[L.PASS].sort_values("t_day", ascending=False)[cols].head(40).to_string(index=False))


if __name__ == "__main__":
    main()

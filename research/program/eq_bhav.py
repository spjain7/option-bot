"""NSE cash bhavcopy research layer (research-nse-cm branch, research/adapters/nse_cm.py).

* panel()        all EQ (+BE) rows 2005-> as one frame; duplicates (symbol, date) removed (EQ preferred over BE)
* adjusted()     exact corporate-action adjustment: factor_t = PREVCLOSE_t / CLOSE_(t-1) (NSE adjusts PREVCLOSE on the
                 ex-date for splits, bonuses, rights and dividends); cumulative back-adjustment of OHLC, volume / factor.
                 Symbol changes are followed through the ISIN.
* verify()       coverage, trading days vs missing weekdays, duplicates, zero/negative prices, gaps > 40 % without a
                 factor, adjustment counts, symbols that stop trading (delisted / suspended) -> results/eq_data_check.json
* market()       point-in-time equal-weight index of the 100 most-traded stocks each day (cash prices only) – used for
                 relative strength and the regime when the NIFTY index series is not available for a date
Everything is point-in-time: a stock exists in the universe only on days it actually traded (delisted stocks included).
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CM = ROOT / "research/data/nse_cm"
OUT = ROOT / "research/program/results"


def panel(years=None):
    fs = sorted(CM.glob("*.csv.gz"))
    if years:
        fs = [f for f in fs if int(f.name[:4]) in years]
    dt = {"symbol": "category", "series": "category", "isin": "string", "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "prevclose": "float32", "volume": "float64", "value": "float64"}
    P = pd.concat([pd.read_csv(f, parse_dates=["date"], usecols=list(dt) + ["date"], dtype=dt) for f in fs], ignore_index=True)
    P["symbol"] = P.symbol.astype(str); P["series"] = P.series.astype(str)
    P = P.sort_values(["date", "symbol", "series"])                        # 'BE' < 'EQ' -> keep last = EQ
    dup = int(P.duplicated(["date", "symbol"]).sum())
    P = P.drop_duplicates(["date", "symbol"], keep="last")
    P.attrs["dups"] = dup
    return P.reset_index(drop=True)


def adjusted_cached():
    """adjusted() of the full panel, cached as a pickle next to the data (rebuilt when the data files change)."""
    import pickle
    f = CM / "_adjusted.pkl"
    stamp = max(p.stat().st_mtime for p in CM.glob("*.csv.gz"))
    if f.exists() and f.stat().st_mtime > stamp:
        return pickle.loads(f.read_bytes())
    A = adjusted(panel())
    f.write_bytes(pickle.dumps(A))
    return A


FUND_PAT = r"(BEES|ETF|LIQUID|GOLD|SILVER|NIFTY|SENSEX|GILT|IETF|NETF|^CPSE|MON100|MAFANG|HNGSNGBEES)"


def securities(P):
    """6-Nov fix: ISIN is missing in the files before mid-2011 -> carry each symbol's first known ISIN backwards (one
    continuous history per company); drop ETFs / mutual-fund units (ISIN INF..., or no ISIN and an ETF-like name)."""
    P = P.copy()
    P["isin"] = P["isin"].astype("string").fillna("")
    first = P[P["isin"].str.len() > 5].sort_values("date").drop_duplicates("symbol")[["symbol", "isin"]].set_index("symbol")["isin"]
    miss = P["isin"].str.len() <= 5
    P.loc[miss, "isin"] = P.loc[miss, "symbol"].map(first).fillna("")
    fund = P["isin"].str.startswith("INF") | ((P["isin"].str.len() <= 5) & P["symbol"].str.contains(FUND_PAT, regex=True))
    P.attrs["funds_removed"] = int(P.loc[fund, "symbol"].nunique())
    return P[~fund]


def adjusted(P):
    """-> dict key (isin or symbol) -> daily frame time/open/high/low/close/volume/value/symbol/factor"""
    P = securities(P)
    P["key"] = P["isin"].where(P["isin"].astype(str).str.len() > 5, P["symbol"])
    out = {}
    for k, g in P.groupby("key", sort=False):
        g = g.sort_values("date")
        if len(g) < 60:
            continue
        pc, c = g.prevclose.values.astype(float), g.close.values.astype(float)
        f = np.ones(len(g))
        f[1:] = np.where((c[:-1] > 0) & (pc[1:] > 0), pc[1:] / c[:-1], 1.0)
        f = np.where(np.abs(f - 1) < 0.002, 1.0, f)                         # rounding noise
        # UDiFF files (from Jul-2024) report an UNADJUSTED previous close: an overnight gap beyond -40 % / +60 % (NSE price
        # bands cap most stocks at 20 %) with no factor is a bonus / split / demerger -> use open / previous close
        o_ = g.open.values.astype(float)
        r = np.ones(len(g)); r[1:] = np.where(c[:-1] > 0, o_[1:] / c[:-1], 1.0)
        miss = (f == 1.0) & ((r < 0.6) | (r > 1.6))
        f = np.where(miss, r, f)
        cum = np.r_[np.cumprod(f[::-1])[::-1][1:], 1.0]
        d = pd.DataFrame(dict(time=g.date.values, open=g.open.values * cum, high=g.high.values * cum, low=g.low.values * cum,
                              close=c * cum, volume=g.volume.values / cum, value=g.value.values, symbol=g.symbol.values,
                              series=g.series.values, factor=f))
        out[k] = d.reset_index(drop=True)
    return out


def verify(P, A):
    days = np.sort(P.date.unique())
    wk = pd.bdate_range(days[0], days[-1])
    missing = sorted(set(wk.date) - set(pd.DatetimeIndex(days).date))
    adj = sum(int((d.factor != 1).sum()) for d in A.values())
    big = sum(int(((d.factor != 1) & ((d.factor < 0.9) | (d.factor > 1.1))).sum()) for d in A.values())
    last = max(d.time.max() for d in A.values())
    stopped = sum(1 for d in A.values() if d.time.max() < last - pd.Timedelta(days=30))
    gaps = 0
    for d in A.values():
        r = d.open.values[1:] / d.close.values[:-1]
        gaps += int(((r < 0.6) | (r > 1.6)).sum())
    rep = dict(first=str(pd.Timestamp(days[0]).date()), last=str(pd.Timestamp(days[-1]).date()), trading_days=len(days),
               weekdays_without_file=len(missing), securities=len(A), symbol_rows=len(P), duplicates_removed=P.attrs.get("dups", 0),
               nonpositive_prices=int((P[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
               corporate_action_adjustments=adj, of_which_split_bonus_like=big, unexplained_gaps_over_40pct=gaps,
               securities_stopped_trading=stopped,
               survivorship="none in the data itself: every security that traded on a day is in that day's file; "
                            "stocks that stopped trading (delisted / suspended / merged) remain in the history")
    (OUT / "eq_data_check.json").write_text(json.dumps(rep, indent=1))
    return rep


def market(A, top=100):
    rows = []
    for k, d in A.items():
        rows.append(pd.DataFrame(dict(time=d.time, key=k, ret=d.close.pct_change().values,
                                      to=(d.close * d.volume).rolling(60, min_periods=20).median().shift(1).values)))
    X = pd.concat(rows)
    X["rk"] = X.groupby("time").to.rank(ascending=False)
    m = X[X.rk <= top].groupby("time").ret.mean().clip(-0.2, 0.2).fillna(0)
    idx = (1 + m).cumprod() * 1000
    return pd.DataFrame(dict(time=idx.index, open=idx.shift(1).fillna(idx).values, high=idx.values, low=idx.values,
                             close=idx.values, volume=1.0)).reset_index(drop=True)

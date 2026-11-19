"""RSIDIV-IX – NSE index futures NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY (owner 11-Nov priority 3).
DAILY 2018-01 … 2026-11: NSE futures bhavcopy, near contract, OHLC back-adjusted by ratio at every roll (ratio = next /
near close on the old contract's last day), volume = contracts over all expiries, OI = sum over all expiries
(roll-neutral). HOURLY 2022-07 … 2026-10: Angel front-month hourly candles (no OI in Angel candles); which contract each
day belongs to is read by matching the 15:15 close to the bhavcopy closes, then back-adjusted the same way; trades never
span a contract change. 3-hour bars = hourly bars 09:15-11:15 / 12:15-14:15 / 15:15. Special sessions dropped.
No index SPOT history is stored, so BASIS cannot be tested for indices (listed in the missing-data register).
Contexts: oi_up / oi_down (daily only), vol_high / vol_low, trend_up / trend_down.
Costs: index futures, slippage 0.01 % per side, STT schedule as for stock futures, extra round trip on a roll.
Periods: daily DEV 2018–2021 · VALID 2022–2023 · OOS 2024–2026; hourly DEV 2022-07–2024-06 · VALID 2024-07–2025-06 ·
OOS 2025-07–2026-10.                         python -m research.rsidiv.index"""
import json
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.rsidiv.stockfut import fut_cost, CUTS as DCUTS  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
NAMES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
HCUTS = [("DEV", "2022-07-01"), ("VAL", "2024-07-01"), ("OOS", "2025-07-01")]
# thin early years (open = 0 on many days, jumps from stale closes): FINNIFTY from Jul-2021, MIDCPNIFTY from Jul-2023
START = {"FINNIFTY": "2021-07-01", "MIDCPNIFTY": "2023-07-01"}
ANG = ROOT / "research/data/angel/NFO"


def idx_rows():
    import glob
    fs = sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz")))
    X = pd.concat((pd.read_csv(f) for f in fs), ignore_index=True)
    X = X[(X["kind"] == "IDX") & X["symbol"].isin(NAMES)].copy()
    X["date"], X["expiry"] = pd.to_datetime(X["date"]), pd.to_datetime(X["expiry"])
    return X[X["expiry"] >= X["date"]]


def daily(X, name):
    x = X[X.symbol == name].sort_values(["date", "expiry"])
    near = x.groupby("date").head(1).set_index("date")
    nxt = x.groupby("date").nth(1).set_index("date")
    agg = x.groupby("date").agg(oi=("oi", "sum"), volume=("contracts", "sum"))
    d = near[["open", "high", "low", "close", "expiry"]].join(agg)
    # back-adjust: on the last day of each near contract, ratio next / near; multiply all earlier prices by the product
    ratio = pd.Series(1.0, index=d.index)
    chg = d["expiry"].ne(d["expiry"].shift(-1)) & d["expiry"].shift(-1).notna()
    for dt in d.index[chg]:
        if dt in nxt.index and nxt.at[dt, "close"] > 0 and d.at[dt, "close"] > 0:
            ratio.loc[:dt] *= nxt.at[dt, "close"] / d.at[dt, "close"]
    for c in ("open", "high", "low", "close"):
        d[c] = d[c] * ratio
    d = d.reset_index().rename(columns={"date": "time"})
    bad = (d[["open", "high", "low", "close"]] <= 0).any(axis=1) | (d.high < d.low)           # untraded rows (open 0)
    d = d[~bad & (d.time >= START.get(name, "2018-01-01"))].reset_index(drop=True)
    return d, x


def hourly(name, x):
    f = ANG / f"{name}27OCT26FUT_ONE_HOUR.csv"
    if not f.exists():
        return None
    h = pd.read_csv(f, parse_dates=["time"])
    h = h[h.time.dt.strftime("%H:%M").isin(["09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"])].copy()
    h["date"] = h.time.dt.normalize()
    last = h.groupby("date").close.last()
    piv = x.pivot_table(index="date", columns="expiry", values="close")
    which = {}
    for dt, c in last.items():
        if dt not in piv.index:
            continue
        row = piv.loc[dt].dropna()
        if len(row):
            which[dt] = row.index[np.argmin(np.abs(row.values - c))]
    h["contract"] = h["date"].map(which)
    h = h[(h["date"] >= START.get(name, "2018-01-01")) & (h[["open", "high", "low", "close"]] > 0).all(axis=1)]
    h = h.dropna(subset=["contract"]).reset_index(drop=True)
    ratio = pd.Series(1.0, index=h.index)
    seg = h["contract"].ne(h["contract"].shift())
    for i in np.where(seg.values)[0][1:]:
        dt_prev, c_old, c_new = h.at[i - 1, "date"], h.at[i - 1, "contract"], h.at[i, "contract"]
        ok = dt_prev in piv.index and c_new in piv.columns and c_old in piv.columns
        if ok and np.isfinite(piv.at[dt_prev, c_new]) and np.isfinite(piv.at[dt_prev, c_old]):
            ratio.iloc[:i] *= piv.at[dt_prev, c_new] / piv.at[dt_prev, c_old]
    for c in ("open", "high", "low", "close"):
        h[c] = h[c] * ratio.values
    return h


def to3h(h):
    k = (h.time.dt.hour * 60 + h.time.dt.minute - 555) // 180
    g = h.groupby([h["date"], k, h["contract"]])
    return g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                 volume=("volume", "sum"), contract=("contract", "first")).reset_index(drop=True).sort_values("time").reset_index(drop=True)


def ctx(b, tf, oi=None):
    c = b["close"].astype(float).reset_index(drop=True); h, l = b["high"].astype(float).reset_index(drop=True), b["low"].astype(float).reset_index(drop=True)
    pc = c.shift(1); atrp = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14)) / c
    span = {"1d": 200, "1w": 40, "1h": 7 * 20, "3h": 3 * 20}[tf]
    ema = c.ewm(span=span, adjust=False).mean(); avm = atrp.rolling(250, min_periods=60).median()
    out = dict(vol_high=(atrp > avm).values, vol_low=(atrp < avm).values, trend_up=(c > ema).values, trend_down=(c < ema).values)
    if oi is not None:
        oc = pd.Series(oi) / pd.Series(oi).shift(5) - 1
        out.update(oi_up=(oc > 0).values, oi_down=(oc < 0).values)
    return out


def main():
    t0 = time.time(); X = idx_rows(); Ls, Ts = [], []
    runs = {}
    for gid, name in enumerate(NAMES):
        d, x = daily(X, name)
        runs.setdefault("1d", []).append((name, d, x))
        hh = hourly(name, x)
        if hh is not None and len(hh) > 500:
            runs.setdefault("1h", []).append((name, hh, x)); runs.setdefault("3h", []).append((name, to3h(hh), x))
    for tf, hold, cuts in (("1d", 15, DCUTS), ("1h", 21, HCUTS), ("3h", 15, HCUTS)):
        pool = E.Pool()
        for gid, (name, b, x) in enumerate(runs.get(tf, [])):
            b = b.reset_index(drop=True)
            oi = b["oi"].values.astype(float) if "oi" in b else None
            S, risk = E.study(b, E.K_BY_TF[tf], extra=ctx(b, tf, oi), oi=oi)
            if tf == "1d":
                start = b["time"] >= "2018-03-01"                             # 40 sessions of warm-up dropped
                S = {k: e & start.values for k, e in S.items()}
                expid = b["expiry"].values.astype("datetime64[D]").astype(np.int64)
            else:
                expid = pd.to_datetime(b["contract"]).values.astype("datetime64[D]").astype(np.int64)
            grp = gid * 100000 + (expid - expid.min() if tf != "1d" else 0)    # intraday trades never span a contract
            pool.add(b, S, risk, grp, fut_cost(b["time"].values, slip=0.0001, notional=1.5e6), expid, name)
        pool.freeze()
        keys = sorted(k for k in pool.idx if k[0] in ("RSI", "DIV"))
        L, T = E.evaluate(pool, keys, cuts, hold, tf, "NSE_INDEX_FUT")
        B = E.baselines(pool, cuts, hold, tf, "NSE_INDEX_FUT")
        Ls += [L, B]; Ts.append(T)
        print(f"{tf}: {len(L)} variants · PASS {int(L.PASS.sum())} · PASS+FDR {int((L.PASS & L.FDR10).sum())} · {time.time() - t0:.0f}s", flush=True)
    L = pd.concat(Ls, ignore_index=True); T = pd.concat(Ts, ignore_index=True)
    L.to_csv(OUT / "index_variants.csv", index=False); T.to_csv(OUT / "index_trades.csv.gz", index=False, compression="gzip")
    print(L[L.family == "BASE"][["tf", "side", "target_R", "DEV_R", "VAL_R", "OOS_R", "all_n"]].to_string(index=False))
    pd.set_option("display.width", 250)
    cols = ["tf", "family", "event", "context", "side", "target_R", "DEV_n", "DEV_R", "VAL_n", "VAL_R", "OOS_n", "OOS_R", "OOS_PF", "all_win", "t_day", "FDR10", "HOLM5", "names_pos", "names"]
    print(L[L.PASS].sort_values("t_day", ascending=False)[cols].head(30).to_string(index=False))


if __name__ == "__main__":
    main()

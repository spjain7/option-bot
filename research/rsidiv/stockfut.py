"""RSIDIV-SF – NSE stock futures, daily and weekly, 2018-01 … 2026-11 (owner 11-Nov priority 2).
Data: NSE futures bhavcopy (research/data/nse_fut_pit, every contract with OI, point-in-time F&O list incl. stocks that
left F&O) + NSE cash bhavcopy (corporate-action adjusted, research/data/nse_cm). Price / volume indicators use the
adjusted CASH series (futures history has unadjusted split jumps; a stock future tracks its cash price), OI = SUM over
all live expiries (roll-neutral) divided by the cumulative cash adjustment (splits change OI in shares), basis = near
future close / unadjusted cash close − 1. Signals only on days the stock HAS a future (and 60-day median cash turnover
>= ₹25 cr). Costs (futures, round trip): brokerage ₹40 + GST on ~₹6 lakh lot, exchange 0.00173 % × 2, stamp 0.002 %,
STT on the sell side 0.0125 % (to Sep-2024) / 0.02 % (Oct-2024 … Mar-2026) / 0.05 % (from 1-Apr-2026), slippage
0.03 % per side; a trade held over an expiry pays one more round trip (roll).
Contexts added to the common ones: oi_up / oi_down (5-session OI change), basis_premium / basis_discount (vs its own
60-session median), vol_high / vol_low (ATR % vs its own 250-session median), trend_up / trend_down (close vs EMA200).
Periods: DEV 2018–2021 · VALID 2022–2023 · OOS 2024–2026.        python -m research.rsidiv.stockfut"""
import glob
import json
import pickle
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(exist_ok=True)
CUTS = [("DEV", "2018-01-01"), ("VAL", "2022-01-01"), ("OOS", "2024-01-01")]
CM_PKL = ROOT / "research/data/nse_cm/_adjusted.pkl"


def fut_cost(dates, slip=0.0003, notional=6e5):
    d = pd.DatetimeIndex(dates)
    stt = np.where(d < "2024-10-01", 0.000125, np.where(d < "2026-04-01", 0.0002, 0.0005))
    exch = 2 * 0.0000173; brok = 40.0 / notional
    return stt + exch + 0.18 * (exch + brok) + brok + 0.00002 + 2e-6 + 2 * slip


def fut_rows(kind="STK"):
    fs = sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz")))
    X = pd.concat((pd.read_csv(f, usecols=["date", "symbol", "kind", "expiry", "close", "contracts", "oi"]) for f in fs), ignore_index=True)
    X = X[X["kind"] == kind]
    X["date"], X["expiry"] = pd.to_datetime(X["date"]), pd.to_datetime(X["expiry"])
    return X[X["expiry"] >= X["date"]]


def fut_daily(X):
    near = X.sort_values("expiry").groupby(["date", "symbol"]).head(1)[["date", "symbol", "expiry", "close"]].rename(columns={"close": "fclose"})
    agg = X.groupby(["date", "symbol"]).agg(oi_all=("oi", "sum"), contracts=("contracts", "sum")).reset_index()
    return near.merge(agg, on=["date", "symbol"])


def build(tf):
    A = pickle.loads(CM_PKL.read_bytes())
    F = fut_daily(fut_rows("STK"))
    sym_key = pd.concat([pd.DataFrame(dict(date=a["time"], symbol=a["symbol"].astype(str), key=k)) for k, a in A.items()], ignore_index=True)
    F = F.merge(sym_key, on=["date", "symbol"], how="inner")
    print(f"futures rows matched to cash: {len(F):,} · stocks {F['key'].nunique()}", flush=True)
    pool = E.Pool(); gid = 0; basis_check = []
    for key, f in F.groupby("key"):
        a = A[key].copy(); a["time"] = pd.to_datetime(a["time"])
        a = a[a["time"] >= "2016-01-01"].reset_index(drop=True)
        f = f.set_index("date")
        j = a.set_index("time")
        fno = j.index.isin(f.index)
        fac = j["factor"].values.astype(float)                          # per-day corporate-action factor
        cum = pd.Series(np.r_[np.cumprod(fac[::-1])[::-1][1:], 1.0], index=j.index)   # adjusted = raw x cum (eq_bhav)
        oi = f["oi_all"].reindex(j.index) / cum                         # OI in adjusted shares (like volume)
        raw = j["close"] / cum
        basis = f["fclose"].reindex(j.index) / raw - 1
        exp = f["expiry"].reindex(j.index)
        to60 = j["value"].rolling(60, min_periods=40).median().shift(1)
        live = fno & (to60 >= 25e7).values & (j["close"] >= 50).values
        b = a[["time", "open", "high", "low", "close", "volume"]].copy()
        b["oi"], b["basis"], b["exp"], b["live"] = oi.values, basis.values, exp.values, live
        if tf == "1w":
            g = b.set_index("time").resample("W-FRI")
            b = pd.DataFrame(dict(open=g["open"].first(), high=g["high"].max(), low=g["low"].min(), close=g["close"].last(),
                                  volume=g["volume"].sum(), oi=g["oi"].last(), basis=g["basis"].last(), exp=g["exp"].last(),
                                  live=g["live"].last())).dropna(subset=["close"]).reset_index()
        if len(b) < 300 or not b["live"].astype(bool).any():
            continue
        c = b["close"].astype(float); h, l = b["high"].astype(float), b["low"].astype(float)
        pc = c.shift(1); atrp = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14)) / c.values
        oi_s = pd.Series(b["oi"].values.astype(float)); bas = pd.Series(b["basis"].values.astype(float))
        oc = oi_s / oi_s.shift(5) - 1
        bmed = bas.rolling(60, min_periods=20).median()
        ema200 = c.ewm(span=200 if tf == "1d" else 40, adjust=False).mean()
        avm = atrp.rolling(250 if tf == "1d" else 52, min_periods=60 if tf == "1d" else 26).median()
        extra = dict(oi_up=(oc > 0).values, oi_down=(oc < 0).values, basis_premium=(bas > bmed).values, basis_discount=(bas < bmed).values,
                     vol_high=(atrp > avm).values, vol_low=(atrp < avm).values, trend_up=(c > ema200).values, trend_down=(c < ema200).values)
        S, risk = E.study(b, E.K_BY_TF[tf], extra=extra, oi=oi_s.ffill().values)
        live_b = b["live"].astype(bool).values
        S = {k: e & live_b for k, e in S.items()}
        expid = pd.Series(b["exp"]).astype("datetime64[ns]").values.astype("datetime64[D]").astype(np.int64)
        expid = np.where(np.isfinite(pd.Series(b["exp"]).astype("datetime64[ns]").values.astype(float)), expid, -1)
        pool.add(b, S, risk, gid, fut_cost(b["time"].values), expid, str(a["symbol"].iloc[-1])); gid += 1
        bb = bas[live_b].dropna()
        if len(bb):
            basis_check.append(bb.values)
    bc = np.concatenate(basis_check) if basis_check else np.array([np.nan])
    print(f"{tf}: {gid} stocks · basis median {100 * np.nanmedian(bc):.2f} % · p1 {100 * np.nanpercentile(bc, 1):.2f} % · p99 {100 * np.nanpercentile(bc, 99):.2f} %", flush=True)
    return pool.freeze(), dict(stocks=gid, basis_median_pct=round(100 * float(np.nanmedian(bc)), 3),
                               basis_p1=round(100 * float(np.nanpercentile(bc, 1)), 2), basis_p99=round(100 * float(np.nanpercentile(bc, 99)), 2))


def main():
    t0 = time.time(); Ls, Ts, info = [], [], {}
    for tf, hold in (("1d", 15), ("1w", 10)):
        pool, inf = build(tf); info[tf] = inf
        keys = sorted(k for k in pool.idx if k[0] in ("RSI", "DIV"))
        L, T = E.evaluate(pool, keys, CUTS, hold, tf, "NSE_STOCK_FUT")
        B = E.baselines(pool, CUTS, hold, tf, "NSE_STOCK_FUT")
        Ls += [L, B]; Ts.append(T)
        print(f"{tf}: {len(L)} variants · PASS {int(L.PASS.sum())} · PASS+FDR {int((L.PASS & L.FDR10).sum())} · {time.time() - t0:.0f}s", flush=True)
    L = pd.concat(Ls, ignore_index=True); T = pd.concat(Ts, ignore_index=True)
    L.to_csv(OUT / "stockfut_variants.csv", index=False); T.to_csv(OUT / "stockfut_trades.csv.gz", index=False, compression="gzip")
    json.dump(info, open(OUT / "stockfut_info.json", "w"), indent=1)
    print(L[L.family == "BASE"][["tf", "event", "side", "target_R", "DEV_R", "VAL_R", "OOS_R", "all_n"]].to_string(index=False))
    pd.set_option("display.width", 250)
    cols = ["tf", "family", "event", "context", "side", "target_R", "DEV_n", "DEV_R", "VAL_n", "VAL_R", "OOS_n", "OOS_R", "OOS_PF", "all_win", "t_day", "FDR10", "HOLM5", "names_pos", "names"]
    print(L[L.PASS].sort_values("t_day", ascending=False)[cols].head(40).to_string(index=False))


if __name__ == "__main__":
    main()

"""CASHQ-OI – F&O stocks only: EXACT-contract futures OI from the NSE futures bhavcopy, full point-in-time F&O stock list
(2018-01 … 2026-11, research/data/nse_fut_pit/days; the older nse_fut/days set holds only ~10 symbols and is not used), traded in CASH (entry next session's open, delivery costs). Never applied to non-F&O stocks.
Contract: the nearest expiry on day t; OI change = that contract's chg_oi vs its own previous OI; sessions in the last
5 days before expiry are excluded (OI migrates to the next month = rollover, not positioning). Also aggregate OI over all
expiries (roll-neutral) as a robustness variant. Classes on day t (cash close vs previous close, OI change > +2 % / < −2 %):
  LB long build-up (price up, OI up) · SC short covering (price up, OI down) · SB short build-up (price down, OI up) ·
  LU long unwinding (price down, OI down). Cash delivery is LONG only -> LB / SC tested as buys; SB / LU tested as buys
  too (contrarian) and reported as "avoid" evidence. Combos: LB + 20-day breakout, LB + RVOL, SB + bullish reversal candle,
  OI divergence (20-day closing high while OI falls 5 days). Exits 1 / 2 / 3R (stop 1.5 ATR) within 20 sessions.
python -m research.cashq.oi_run"""
import glob
import json
import pickle
import time
from pathlib import Path
import numpy as np
import pandas as pd
from . import data as D, ind as I, engine as EN, validate as V
from .daily_run import summarise, first_in

OI_SPLITS = dict(DEV=("2018-01-01", "2021-12-31"), VALID=("2022-01-01", "2023-12-31"), OOS=("2024-01-01", "2026-12-31"))

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "results"


def fut_panel():
    fs = sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz")))
    X = pd.concat((pd.read_csv(f, usecols=["date", "symbol", "kind", "expiry", "close", "oi", "chg_oi"]) for f in fs), ignore_index=True)
    X = X[X["kind"] == "STK"]
    X["date"], X["expiry"] = pd.to_datetime(X["date"]), pd.to_datetime(X["expiry"])
    X = X[X["expiry"] >= X["date"]]
    near = X.sort_values("expiry").groupby(["date", "symbol"]).head(1).copy()
    near["prev_oi"] = near["oi"] - near["chg_oi"]
    near["oi_chg"] = near["chg_oi"] / near["prev_oi"].replace(0, np.nan)
    bd = pd.Series(1, index=pd.DatetimeIndex(sorted(X["date"].unique()))).cumsum()
    near["sess_to_exp"] = near["expiry"].map(lambda e: bd[bd.index <= e].iloc[-1] if (bd.index <= e).any() else np.nan) - near["date"].map(bd)
    agg = X.groupby(["date", "symbol"]).agg(oi_all=("oi", "sum"), chg_all=("chg_oi", "sum")).reset_index()
    agg["oi_all_chg"] = agg["chg_all"] / (agg["oi_all"] - agg["chg_all"]).replace(0, np.nan)
    return near.merge(agg[["date", "symbol", "oi_all_chg"]], on=["date", "symbol"], how="left")


def main():
    t0 = time.time()
    A = pickle.loads(D.CM_PKL.read_bytes())
    sym_key = pd.concat([pd.DataFrame(dict(date=a["time"], symbol=a["symbol"].astype(str), key=k)) for k, a in A.items()], ignore_index=True)
    W = D.daily_panel()
    N = fut_panel().merge(sym_key, on=["date", "symbol"], how="inner")
    print(f"futures rows matched to cash: {len(N):,}, symbols {N['symbol'].nunique()} ({time.time() - t0:.0f}s)", flush=True)
    keys = sorted(set(N["key"]) & set(W["close"].columns))
    P = {f: W[f][keys] for f in ("open", "high", "low", "close", "volume")}
    P["elig"] = W["elig"][keys]
    piv = lambda col: N.pivot_table(index="date", columns="key", values=col, aggfunc="last").reindex(index=P["close"].index, columns=keys)
    oi, oi_all, ste = piv("oi_chg"), piv("oi_all_chg"), piv("sess_to_exp")
    c, h, l, o = P["close"], P["high"], P["low"], P["open"]
    r1 = c / c.shift(1) - 1
    fo = oi.notna() & (ste > 5) & P["elig"]                     # F&O stock with a near contract, outside the roll week
    th = 0.02
    cls = dict(LB=(r1 > 0) & (oi > th), SC=(r1 > 0) & (oi < -th), SB=(r1 < 0) & (oi > th), LU=(r1 < 0) & (oi < -th))
    cls_all = dict(LB_all=(r1 > 0) & (oi_all > th), SC_all=(r1 > 0) & (oi_all < -th))
    rv = I.rvol(P["volume"], 20)
    hi20 = first_in(c > h.shift(1).rolling(20).max(), 5)
    rev = I.hammer(o, h, l, c) | I.bull_engulf(o, h, l, c)
    S = {f"OI_{k}": v & fo for k, v in cls.items()}
    S.update({f"OI_{k}": v & oi_all.notna() & P["elig"] for k, v in cls_all.items()})
    S["OI_LB_BO20"] = cls["LB"] & hi20 & fo
    S["OI_LB_rvol2"] = cls["LB"] & (rv >= 2) & fo
    S["OI_SB_reversal_candle"] = cls["SB"].shift(1).fillna(False).astype(bool) & rev & fo
    S["OI_div_high_OIfalling"] = (c >= c.rolling(20).max()) & (oi.rolling(5).sum() < -0.05) & fo
    S["OI_LB_strong_5pct"] = (r1 > 0.02) & (oi > 0.05) & fo
    F = dict(P); F["atr"] = I.atr(h, l, c, 14)
    rows, led = [], []
    for nm, sig in S.items():
        sig = sig.fillna(False).astype(bool)
        for R in (1.0, 2.0, 3.0):
            T = EN.daily_trades(F, sig, 1.5 * F["atr"], 1, R, 20)
            if not len(T):
                continue
            T["strategy"], T["R"] = nm, R
            rows.append(summarise(nm, "OPEN_INTEREST", T, splits=OI_SPLITS, extra=dict(params=f"F&O stocks, near-contract OI (roll week excluded), cash entry next open, target {R:g}R, stop 1.5 ATR, max 20",
                                                                 R=R, hold="swing", side="LONG")))
            led.append(T)
        print(f"  {nm} ({time.time() - t0:.0f}s)", flush=True)
    L = pd.DataFrame(rows)
    sel = L.apply(V.verdict, axis=1) != "NOT_SELECTED"
    L["OOS_q"] = 1.0
    L.loc[sel, "OOS_q"] = V.bh(L.loc[sel, "OOS_p"].fillna(1).values)
    L["status"] = L.apply(V.verdict, axis=1)
    L.to_csv(OUT / "oi_leaderboard.csv", index=False)
    pd.concat(led, ignore_index=True).assign(symbol=lambda x: x["key"].map(W["symbol"])).to_csv(OUT / "oi_trades.csv.gz", index=False)
    json.dump(dict(variants=len(L), trades=int(sum(len(x) for x in led)), fo_symbols=int(N["symbol"].nunique()), seconds=round(time.time() - t0)),
              open(OUT / "oi_run.json", "w"))
    print(L["status"].value_counts().to_dict())


if __name__ == "__main__":
    main()

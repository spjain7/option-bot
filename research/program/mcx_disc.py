"""MCXD-001 – MCX intraday STRATEGY-FAMILY discovery engine (owner research reset, 6-Nov-2026).

Why (audit of MCXI-001, artifacts in results/): the 7k combinations were parameter variants of 3 breakout families; stops were
5-30-minute ranges (median cost 0.43-1.06R per trade under a cost model of 2 x (fees + 2-20 ticks slippage per side) =
2.4-4.5 x a realistic cost); the day's typical move is 9-66 x the realistic round trip. New design: different families,
positions held for hours, wider stops, realistic costs with a stress test, failure reasons recorded per experiment.

COSTS: realistic = statutory fees (instruments.COSTS) + 1.5 ticks slippage per side; STRESS = 2 x realistic. Both reported;
a strategy must stay positive under STRESS on DEV + VALID to pass.
PERIODS: DEV 2025-11-06 … 2026-06-30 (selection) · VALID 2026-07-01 … 2026-11-03 · HIST 2023 … 2025-11-05 (never used to select).
EXECUTION: signals on completed bars, entry at the next bar's open, stop checked first in every 5-minute bar, intraday only
(no entry after 22:00, square-off at the 23:00 bar), no trading on contract-switch days.
FAMILIES (hypotheses, each BUY and SELL, each commodity separately):
  TPB  trend pull-back: 60m EMA20>EMA50 & close>EMA50 (mirror), 15m pull-back to session VWAP or EMA20 within 3 bars, then a
       15m close above the previous bar's high -> stop under the 4-bar low.
  FBR  failed breakout: price trades beyond the previous-day high/low or the 09:00-10:00 range, closes back inside within 2
       15m bars -> reverse; stop beyond the sweep extreme.
  VCE  volatility compression -> expansion: 30m Bollinger(20,2) width within 10 % of its 100-bar low in the last 5 bars, then a
       close outside the band with a body >= 60 % of the range -> stop 1.5 x ATR(30m).
  MEX  momentum exhaustion: 15m RSI(14) >= 80 (<= 20) and close >= 2.5 x ATR(15m) beyond VWAP, then a reversal bar (close below
       the previous low) -> fade; stop beyond the day's extreme; target VWAP.
  VMR  VWAP mean reversion in a range regime: previous-day daily ADX < 20, close <= VWAP - 2 x ATR(15m) then a bullish bar ->
       target VWAP; stop 1.5 x ATR beyond.
  DTC  day-trend continuation (time-of-day): at 13:00 / 17:00 checkpoints, price above VWAP and the day's open by >= 0.3 x
       daily ATR and 60m trend up -> follow to the close; stop 0.5 x daily ATR.
  USO  US-session open momentum: direction of the first 30 minutes after the NYMEX/COMEX open (18:30 IST in US summer, 19:30 in
       winter) -> follow to the close; stop at the other side of that 30-minute range.
EXITS per family: its own target (where defined) / 2.5 x ATR(15m) trailing stop / square-off at the close.
python research/program/mcx_disc.py"""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import liqtl_mcx5 as LM, mcx_event as EV  # noqa: E402
from research.instruments import REGISTRY as REG, COSTS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
Y0, DEV_END, Y1 = pd.Timestamp("2025-11-06"), pd.Timestamp("2026-07-01"), pd.Timestamp("2026-11-04")


def real_cost(name, p):
    r = REG[name]; c = COSTS[r["exchange"]]; m = r["mult"]; tb = ts = p * m
    exch = (tb + ts) * c["exch"]; sebi = (tb + ts) * c["sebi"]; brk = 2 * c["brokerage"]
    fees = brk + exch + sebi + c["gst"] * (brk + exch + sebi) + ts * c["tax_sell"] + tb * c["stamp_buy"]
    return fees / m + 2 * 1.5 * r["tick"]


def prep(name):
    d = LM.load(name, "FIVE_MINUTE")
    d = d[d.time >= "2023-01-01"].reset_index(drop=True)
    d["day"] = d.time.dt.normalize(); d["m"] = d.time.dt.hour * 60 + d.time.dt.minute
    tp = (d.high + d.low + d.close) / 3
    d["vwap"] = (tp * d.volume).groupby(d.day).cumsum() / d.volume.groupby(d.day).cumsum().replace(0, np.nan)
    f15 = LM.resample(d, 15).reset_index(drop=True); f30 = LM.resample(d, 30).reset_index(drop=True); f60 = LM.resample(d, 60).reset_index(drop=True)
    for f in (f15, f30, f60):
        f["day"] = f.time.dt.normalize(); f["m"] = f.time.dt.hour * 60 + f.time.dt.minute
        f["atr"] = I.atr(f, 14)
    # VWAP at each 15m bar close = VWAP of the last 5m bar inside it
    end15 = f15.time + pd.Timedelta(minutes=10)
    f15["vwap"] = pd.Series(d.set_index("time").vwap).reindex(end15.values).values
    f15["ema20"] = f15.close.ewm(span=20, adjust=False).mean()
    f15["rsi"] = I.rsi(f15.close, 14)
    e20, e50 = f60.close.ewm(span=20, adjust=False).mean(), f60.close.ewm(span=50, adjust=False).mean()
    f60["tr"] = np.where((e20 > e50) & (f60.close > e50), 1, np.where((e20 < e50) & (f60.close < e50), -1, 0))
    f60["end"] = f60.time + pd.Timedelta(minutes=60)
    # 60m trend known at a 15m bar = last 60m bar that ENDED at or before the 15m bar's end
    idx = np.searchsorted(f60.end.values, (f15.time + pd.Timedelta(minutes=15)).values, side="right") - 1
    f15["tr60"] = np.where(idx >= 0, f60.tr.values[np.clip(idx, 0, None)], 0)
    mid = (f30.close.rolling(20).mean()); sd = f30.close.rolling(20).std()
    f30["bbu"], f30["bbl"] = mid + 2 * sd, mid - 2 * sd
    w = (f30.bbu - f30.bbl) / mid
    f30["sq"] = (w <= w.rolling(100).min() * 1.1).rolling(5).max().fillna(0).astype(bool)
    dd = d.groupby("day").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
    tr = np.maximum(dd.h - dd.l, np.maximum((dd.h - dd.c.shift()).abs(), (dd.l - dd.c.shift()).abs()))
    dd["atr"] = tr.rolling(14).mean().shift(1)
    dd["adx"] = I.adx(dd.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"}), 14).shift(1).values
    dd["ph"], dd["pl"] = dd.h.shift(1), dd.l.shift(1)
    sw = set(d.loc[d.switch.fillna(False), "day"])
    return d, f15, f30, f60, dd, sw


def walk(d5, i0, side, e, st, tgt, trail_atr, ie):
    """5-minute walk from bar index i0 (entry bar) to ie (square-off). Returns exit price, MFE / MAE in price units."""
    H, L, O, C = d5.high.values, d5.low.values, d5.open.values, d5.close.values
    best = e; mfe = mae = 0.0
    for k in range(i0, ie + 1):
        if k > i0 and ((side > 0 and O[k] <= st) or (side < 0 and O[k] >= st)):
            return O[k], mfe, mae
        if (side > 0 and L[k] <= st) or (side < 0 and H[k] >= st):
            return st, mfe, min(mae, -abs(e - st))
        mfe = max(mfe, side * ((H[k] if side > 0 else L[k]) - e)); mae = min(mae, side * ((L[k] if side > 0 else H[k]) - e))
        if tgt is not None and k > i0 and ((side > 0 and H[k] >= tgt) or (side < 0 and L[k] <= tgt)):
            return tgt, mfe, mae
        if trail_atr:
            best = max(best, H[k]) if side > 0 else min(best, L[k])
            ns = best - side * trail_atr
            if (side > 0 and ns > st) or (side < 0 and ns < st):
                st = ns
    return C[ie], mfe, mae


def signals(name, d5, f15, f30, f60, dd, sw):
    """-> list of (family, side, signal_time, entry_bar_time, stop, target(or None), atr15, day)"""
    out = []
    for day, g in f15.groupby("day"):
        if day in sw or day not in dd.index or not dd.at[day, "atr"] > 0:
            continue
        D = dd.loc[day]; g = g[(g.m <= 22 * 60 - 15)]
        if len(g) < 8:
            continue
        O, H, L, C, V, A, M = (g[x].values for x in ("open", "high", "low", "close", "vwap", "atr", "m"))
        T, E20, RSI, TR = g.time.values, g.ema20.values, g.rsi.values, g.tr60.values
        dayo = O[0]
        orh, orl = H[M < 600].max() if (M < 600).any() else np.nan, L[M < 600].min() if (M < 600).any() else np.nan
        used = set()
        def add(fam, side, k, st, tgt):
            if (fam, side) in used or k + 1 >= len(g) or not A[k] > 0:
                return
            used.add((fam, side)); out.append((fam, side, T[k], st, tgt, A[k], day))
        for k in range(2, len(g)):
            if M[k] < 600:
                continue
            # TPB
            for s in (1, -1):
                if TR[k] == s:
                    touched = any((s > 0 and (L[j] <= V[j] or L[j] <= E20[j])) or (s < 0 and (H[j] >= V[j] or H[j] >= E20[j])) for j in range(max(0, k - 3), k))
                    if touched and ((s > 0 and C[k] > H[k - 1]) or (s < 0 and C[k] < L[k - 1])):
                        lo = L[max(0, k - 3):k + 1].min() if s > 0 else H[max(0, k - 3):k + 1].max()
                        add("TPB", s, k, lo - s * 0.1 * A[k], None)
            # FBR: sweep of prev-day H/L or opening range, close back inside within 2 bars
            for lvl, s in ((D.ph, -1), (orh, -1), (D.pl, 1), (orl, 1)):
                if not lvl == lvl:
                    continue
                for j in (k - 1, k - 2):
                    if j < 0:
                        continue
                    swept = (s < 0 and H[j] > lvl) or (s > 0 and L[j] < lvl)
                    back = (s < 0 and C[k] < lvl and C[j] >= lvl - 1e-12) or (s > 0 and C[k] > lvl and C[j] <= lvl + 1e-12)
                    if swept and back and ((s < 0 and C[k] < O[k]) or (s > 0 and C[k] > O[k])):
                        ext = H[j:k + 1].max() if s < 0 else L[j:k + 1].min()
                        add("FBR", s, k, ext + (-s) * 0.1 * A[k], None)
            # MEX: RSI extreme and stretched from VWAP, then a reversal bar
            for s in (-1, 1):
                ext_ok = (s < 0 and RSI[k - 1] >= 80 and C[k - 1] >= V[k - 1] + 2.5 * A[k - 1]) or (s > 0 and RSI[k - 1] <= 20 and C[k - 1] <= V[k - 1] - 2.5 * A[k - 1])
                if ext_ok and ((s < 0 and C[k] < L[k - 1]) or (s > 0 and C[k] > H[k - 1])):
                    ext = H[:k + 1].max() if s < 0 else L[:k + 1].min()
                    add("MEX", s, k, ext - s * 0.1 * A[k], V[k])
            # VMR: range regime, stretched below/above VWAP, reversal bar
            if D.adx == D.adx and D.adx < 20:
                for s in (1, -1):
                    if ((s > 0 and C[k - 1] <= V[k - 1] - 2 * A[k - 1] and C[k] > O[k] and C[k] > C[k - 1])
                            or (s < 0 and C[k - 1] >= V[k - 1] + 2 * A[k - 1] and C[k] < O[k] and C[k] < C[k - 1])):
                        add("VMR", s, k, C[k] - s * 1.5 * A[k], V[k])
            # DTC: checkpoints 13:00 and 17:00 (bar starting 12:45 / 16:45 closes at the checkpoint)
            if M[k] in (12 * 60 + 45, 16 * 60 + 45):
                for s in (1, -1):
                    if TR[k] == s and s * (C[k] - V[k]) > 0 and s * (C[k] - dayo) >= 0.3 * D.atr:
                        add("DTC", s, k, C[k] - s * 0.5 * D.atr, None)
        # USO: first 30 minutes after the US open (NYMEX 09:00 ET for energy, COMEX 08:20 ET for metals)
        us = (9 * 60) if name in ("CRUDEOIL", "NATURALGAS") else (8 * 60 + 20)
        ist = us + (9 * 60 + 30 if EV.us_dst(pd.Timestamp(day)) else 10 * 60 + 30)       # ET -> IST
        ist = int(np.floor(ist / 15) * 15)
        win = (M >= ist) & (M < ist + 30)
        if win.sum() == 2:
            k = np.flatnonzero(win)[-1]
            hi, lo = H[win].max(), L[win].min(); s = 1 if C[k] > O[np.flatnonzero(win)[0]] else -1
            add("USO", s, k, (lo if s > 0 else hi) - s * 0.1 * A[k], None)
    # VCE on 30m
    for day, g in f30.groupby("day"):
        if day in sw or day not in dd.index:
            continue
        g = g[g.m <= 22 * 60 - 30]
        for k in range(len(g)):
            r = g.iloc[k]
            if not (r.sq and r.atr > 0) or r.m < 600:
                continue
            rng = r.high - r.low
            if rng <= 0:
                continue
            for s in (1, -1):
                if (s > 0 and r.close > r.bbu and (r.close - r.open) >= 0.6 * rng) or (s < 0 and r.close < r.bbl and (r.open - r.close) >= 0.6 * rng):
                    out.append(("VCE", s, r.time + pd.Timedelta(minutes=15), r.close - s * 1.5 * r.atr, None, r.atr / np.sqrt(2), day))
                    break
            else:
                continue
            break
    return out


def simulate(name):
    d5, f15, f30, f60, dd, sw = prep(name)
    sig = signals(name, d5, f15, f30, f60, dd, sw)
    t5 = d5.time.values; rows = []
    eod_idx = d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1])
    for fam, s, tsig, st, tgt, a15, day in sig:
        t_entry = pd.Timestamp(tsig) + pd.Timedelta(minutes=15)           # next bar after the 15m signal bar closes
        i0 = np.searchsorted(t5, np.datetime64(t_entry))
        if i0 >= len(d5) or d5.day.iat[i0] != day or day not in eod_idx.index:
            continue
        ie = int(eod_idx[day])
        if i0 >= ie:
            continue
        e = d5.open.iat[i0]
        R = s * (e - st)
        if not R > 0 or R > 6 * a15:
            continue
        cst = real_cost(name, e)
        D = dd.loc[day]
        for ex in ("TGT", "TRAIL", "EOD"):
            if ex == "TGT" and tgt is None:
                tg = e + s * 2 * R
            elif ex == "TGT":
                tg = tgt if s * (tgt - e) > 0 else e + s * 1 * R
            else:
                tg = None
            px, mfe, mae = walk(d5, i0, s, e, st, tg, 2.5 * a15 if ex == "TRAIL" else 0.0, ie)
            g = s * (px - e)
            rows.append(dict(name=name, fam=fam, side="BUY" if s > 0 else "SELL", exit=ex, day=day, entry_time=t_entry,
                             R_pts=R, gross_R=g / R, net_R=(g - cst) / R, stress_R=(g - 2 * cst) / R, cost_R=cst / R,
                             mfe_R=mfe / R, mae_R=mae / R, adx_prev=D.adx, atr_day=D.atr, pts=g - cst))
    return pd.DataFrame(rows)


def failure(r):
    if r.n < 30:
        return "too few trades"
    if r.gross_dev <= 0 and r.gross_hist <= 0:
        return "no gross edge (entries no better than chance)"
    if r.gross_dev > 0 and r.net_dev <= 0:
        return "gross edge eaten by costs -> needs larger moves / lower turnover"
    if r.net_dev > 0 and r.net_valid <= 0:
        return "development only – failed validation"
    if r.net_dev > 0 and r.net_valid > 0 and r.net_hist <= 0:
        return "recent regime only – failed older history"
    if r.stress_dev <= 0 or r.stress_valid <= 0:
        return "positive only at realistic cost, not under 2x stress"
    return "PASS"


def summarise(T):
    T = T.copy()
    T["per"] = np.where(T.day < Y0, "hist", np.where(T.day < DEV_END, "dev", "valid"))
    rows = []
    for k, g in T.groupby(["name", "fam", "side", "exit"]):
        r = dict(zip(["name", "fam", "side", "exit"], k), n=len(g))
        for p in ("dev", "valid", "hist"):
            x = g[g.per == p]
            r.update({f"n_{p}": len(x), f"gross_{p}": x.gross_R.mean() if len(x) else np.nan, f"net_{p}": x.net_R.mean() if len(x) else np.nan,
                      f"stress_{p}": x.stress_R.mean() if len(x) else np.nan, f"win_{p}": 100 * (x.net_R > 0).mean() if len(x) else np.nan})
        r["cost_R"] = g.cost_R.median(); r["mfe_med"] = g.mfe_R.median()
        r["n"] = r["n_dev"]
        rows.append(r)
    S = pd.DataFrame(rows).fillna({"gross_dev": -9, "net_dev": -9, "net_valid": -9, "net_hist": -9, "stress_dev": -9, "stress_valid": -9, "gross_hist": -9})
    S["verdict"] = S.apply(failure, axis=1)
    return S


def main():
    t0 = time.time()
    T = pd.concat([simulate(n) for n in NAMES], ignore_index=True)
    T.to_csv(OUT / "mcxd_trades.csv.gz", index=False)
    S = summarise(T)
    S.to_csv(OUT / "mcxd_ledger.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
    print(f"[{(time.time() - t0) / 60:.1f} min] trades {len(T):,} · experiments {len(S)}")
    print(S.verdict.value_counts().to_string())
    fam = T.assign(per=np.where(T.day < Y0, "hist", np.where(T.day < DEV_END, "dev", "valid"))).groupby(["fam", "per"])[["gross_R", "net_R"]].mean().unstack().round(3)
    print("\nfamily averages (all commodities, all exits):\n", fam)
    cols = ["name", "fam", "side", "exit", "n_dev", "gross_dev", "net_dev", "n_valid", "net_valid", "n_hist", "net_hist", "stress_dev", "stress_valid", "cost_R", "verdict"]
    print(S.sort_values("net_dev", ascending=False)[cols].head(30).round(3).to_string(index=False))


if __name__ == "__main__":
    main()

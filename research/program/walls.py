"""WALLS-001 (1-Nov-2026, owner after ZYDUSLIFE: "check what indication before the up move – yes run").
Option-OI 'walls' from the real NSE bhavcopy (Jul-2022 → Oct-2026, ~180 stocks), daily futures candles.
Walls (from the PREVIOUS day's close – no look-ahead), option expiry ≥ 3 days away:
  call wall = strike above the previous futures close with the largest CE OI · put wall = strike below with the largest PE OI
Setups:
  BRK   BUY: daily close above the call wall, volume ≥ 2x the 20-day average, futures OI up that day (same contract)
        SELL mirror: close below the put wall, volume ≥ 2x, OI up                -> entry next open, 2 ATR stop, 2R, 20 days
  SWP   BUY: low below the put wall, close back above it in the top third of the day, volume ≥ 1.5x
        SELL mirror at the call wall                                             -> entry on a break of the day's high/low
                                                                                    within 3 days, stop beyond the day, 2R
  ZYD   BUY: BRK BUY within 5 days after a SWP BUY day (the ZYDUSLIFE sequence); SELL mirror
Variants: with / without OI-up for BRK, 1R / 2R. Costs 0.06 % of price per side-pair (1x), results at 2x.
python research/program/walls.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, daily_candles as DC  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from crude import indicators as I  # noqa: E402

DAYS = ROOT / "research/data/nse_opt/days"
OUT = ROOT / "research/program/results"
COST = 0.0006


def one_day(p):
    d = pd.read_csv(p, parse_dates=["date", "expiry"])
    day = d["date"].iat[0]
    fut = d[d["kind"] == "FUT"].sort_values("expiry").groupby("symbol").head(1).set_index("symbol")
    o = d[(d["kind"] != "FUT") & (d["expiry"] >= day + pd.Timedelta(days=3))]
    o = o[o["expiry"] == o.groupby("symbol")["expiry"].transform("min")]
    oi = o.groupby(["symbol", "kind", "strike"])["oi"].sum()
    rows = []
    for sym, f in fut.iterrows():
        F = float(f["close"])
        cw = pw = np.nan
        try:
            ce = oi.loc[(sym, "CE")]; ce = ce[ce.index > F]
            pe = oi.loc[(sym, "PE")]; pe = pe[pe.index < F]
            cw = float(ce.idxmax()) if len(ce) and ce.max() > 0 else np.nan
            pw = float(pe.idxmax()) if len(pe) and pe.max() > 0 else np.nan
        except KeyError:
            pass
        rows.append((day, sym, f["open"], f["high"], f["low"], F, f["contracts"], f["oi"], f["expiry"], cw, pw))
    return rows


def panel():
    cache = OUT / "walls_panel.csv.gz"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["time", "expiry"])
    with Pool(3) as pool:
        rows = [r for x in pool.imap(one_day, sorted(DAYS.glob("*.csv")), chunksize=8) for r in x]
    P = pd.DataFrame(rows, columns=["time", "symbol", "open", "high", "low", "close", "volume", "oi", "expiry", "cw", "pw"])
    P = P.sort_values(["symbol", "time"]).reset_index(drop=True)
    P.to_csv(cache, index=False)
    return P


def run_sym(g):
    g = g.sort_values("time").reset_index(drop=True)
    if len(g) < 120:
        return []
    g["switch"] = g["expiry"] != g["expiry"].shift(1)
    f = H.features(g[["time", "open", "high", "low", "close", "volume"]])
    f["switch"] = g["switch"].values
    f["atr"] = I.atr(f, 14)
    cost = (g["close"] * COST).values
    c, h, l = g["close"].values, g["high"].values, g["low"].values
    cw, pw = g["cw"].shift(1).values, g["pw"].shift(1).values          # previous day's walls
    vx = f["volx"].values
    oiup = ((g["oi"] > g["oi"].shift(1)) & ~g["switch"]).values
    pos = (c - l) / np.where(h - l > 0, h - l, np.nan)
    brk = {1: (c > cw) & (vx >= 2), -1: (c < pw) & (vx >= 2)}
    swp = {1: (l < pw) & (c > pw) & (pos >= 2 / 3) & (vx >= 1.5), -1: (h > cw) & (c < cw) & (pos <= 1 / 3) & (vx >= 1.5)}
    rows, tm = [], g["time"].values
    for side in (1, -1):
        prior = pd.Series(swp[side]).rolling(5, min_periods=1).max().shift(1).fillna(0).astype(bool).values
        sets = {"BRK": brk[side], "BRK+OIup": brk[side] & oiup, "ZYD": brk[side] & prior, "ZYD+OIup": brk[side] & prior & oiup}
        for nm, sig in sets.items():
            for r in (1.0, 2.0):
                s = np.where(np.nan_to_num(sig.astype(float)) > 0, side, 0)
                for x in H.simulate(f, s, side, 2.0, r, 20, 0, cost, start=40):
                    if x["status"] == "trade":
                        rows.append((nm, "BUY" if side > 0 else "SELL", f"{r:g}R", x["time"], x["r1"], x["r2"]))
        for r in (1.0, 2.0):
            busy = -1
            for i in np.flatnonzero(np.nan_to_num(swp[side].astype(float)) > 0):
                if i < 40 or i <= busy or i >= len(f) - 2 or f["switch"].iat[i] or not f["atr"].iat[i] > 0:
                    continue
                t = DC.trade(f, i, side, l[i] if side > 0 else h[i], h[i] if side > 0 else l[i], "E2", r, cost)
                if t is None:
                    continue
                busy = t["j"]
                rows.append(("SWP", "BUY" if side > 0 else "SELL", f"{r:g}R", tm[i], t["r1"], t["r2"]))
    return [(g["symbol"].iat[0],) + x for x in rows]


def main():
    P = panel()
    print(f"panel {len(P):,} symbol-days, {P.symbol.nunique()} symbols, {P.time.min():%Y-%m-%d} → {P.time.max():%Y-%m-%d}; "
          f"walls found {P.cw.notna().mean() * 100:.0f}% / {P.pw.notna().mean() * 100:.0f}%")
    with Pool(3) as pool:
        rows = [r for x in pool.imap_unordered(run_sym, [g for _, g in P.groupby("symbol")], chunksize=4) for r in x]
    T = pd.DataFrame(rows, columns=["symbol", "setup", "side", "target", "time", "r1", "r2"])
    T["time"] = pd.to_datetime(T["time"])
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    T.to_csv(OUT / "walls_trades.csv.gz", index=False)
    K = ["setup", "side", "target"]
    S = T.groupby(K).agg(n=("r2", "size"), win=("r2", lambda s: (s > 0).mean()), R_1x=("r1", "mean"), R_2x=("r2", "mean")) \
        .join(T.pivot_table(index=K, columns="split", values="r2", aggfunc="mean")[["train", "valid", "test"]])
    S["all3"] = (S[["train", "valid", "test"]] > 0).all(axis=1)
    S.reset_index().to_csv(OUT / "walls_summary.csv", index=False)
    pd.set_option("display.width", 220)
    print(S.round(3).to_string())


if __name__ == "__main__":
    main()

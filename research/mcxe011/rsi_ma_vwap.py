"""MCXE-011c: RSI crossing its smoothed moving average + VWAP confirmation (owner idea, 7-Nov). Exploratory: DEV + VALID
only, OOS masked; VALID not fresh.
  base     : RSI(14) crosses above (BUY) / below (SELL) its 14-period SMA (TradingView 'RSI-based MA' default)
  vwap     : + close above (BUY) / below (SELL) the session VWAP
  vwap_z   : + vwap + RSI > 50 (BUY) / < 50 (SELL)
Exits: SHORT = 1.5 ATR stop, 2R target, max ~1 session of bars;  TREND = 2 ATR stop, 4 ATR trail (as H1.12L).
Markets: MCX 15m, MCX 1h, stock futures 1h (point-in-time), index futures 1h. BUY / SELL separately.
python research/mcxe011/rsi_ma_vwap.py -> research/mcxe011/RSI_MA_VWAP_RESULTS.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402
from research.mcxe006 import engine as EN6  # noqa: E402
from research.mcxe007 import engine7 as E7  # noqa: E402
from research.mcxe011 import intraday_bo as IB  # noqa: E402

OUT = ROOT / "research/mcxe011"
VARIANTS = {"base": (), "vwap": ("vwap",), "vwap_z": ("vwap", "zone")}


def make_fn(flt, ma=14):
    def fn(f, side, extra=None, **kw):
        c = f.close.astype(float)
        r = I.rsi(c, 14); m = r.rolling(ma).mean()
        x = (side * (r - m) > 0) & (side * (r.shift(1) - m.shift(1)) <= 0)
        sig = x.fillna(False).values.copy()
        if "vwap" in flt:
            sig &= np.nan_to_num(side * (c.values - f.vwap.values.astype(float)), nan=-1) > 0
        if "zone" in flt:
            sig &= np.nan_to_num(side * (r.values - 50), nan=-1) > 0
        return dict(sig=sig, warm=60, entry="open")
    return fn


def main():
    from research.program import mcx_disc as MD
    from research.mcxe008 import lab8 as L8
    mcx1h = EN6.frames("MCX", 60)
    for f in mcx1h:
        f.attrs.update(kind="MCX", wkey="MCX", mult=MD.REG[f.attrs["name"]]["mult"])
    idx = L8.idx1h()
    markets = [("MCX_15m", IB.mcx15(), 58), ("MCX_1h", mcx1h, 15), ("STK_1h", IB.stk1h(), 7), ("IDX_1h", idx, 7)]
    rows = []
    for mk, fs, bars_day in markets:
        fs = [f for f in fs if "vwap" in f]
        exits = {"SHORT 1.5ATR/2R/~1 session": dict(k=1.5, tgtR=2.0, maxbars=bars_day),
                 "TREND 2ATR + 4ATR trail": dict(k=2.0, trail=4.0, maxbars=16 * bars_day)}
        for xn, ex in exits.items():
            for side in (1, -1):
                for vn, flt in VARIANTS.items():
                    T = E7.run(fs, make_fn(flt), {}, ex, side)
                    r = dict(market=mk, side="BUY" if side > 0 else "SELL", exit=xn, filters=vn, **(IB.summ(T) if len(T) else {}))
                    if r.get("eligible"):
                        r["random_2x"], r["random_p95"] = IB.control(fs, T, ex, side)
                        r["beats_random_p95"] = bool(T[T.period.isin(["DEV", "VALID"])].r2.mean() > r["random_p95"])
                    rows.append(r)
                    print(mk, r["side"], xn[:5], vn, {k: r.get(k) for k in ("DEV_n", "DEV_exp2", "VALID_n", "VALID_exp2", "VALID_win", "DV_ci_lo", "eligible", "beats_random_p95")}, flush=True)
        pd.DataFrame(rows).to_csv(OUT / "RSI_MA_VWAP_RESULTS.csv", index=False)


if __name__ == "__main__":
    main()

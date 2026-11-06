"""NSE cash-equity research data layer (6-Nov-2026, owner workstream "cash equity, 4-5 quality stocks a day").

* load(symbol, iv)    Angel NSE cash candles (research/data/angel/NSE_EQ, from research/adapters/angel_eq.py)
* clean()             duplicates, non-positive prices, zero-range-zero-volume rows, out-of-session rows (intraday)
* adjust_splits()     Angel cash prices are NOT adjusted for splits / bonuses: overnight jumps matching a split or bonus
                      ratio (2:1, 5:1, 10:1, 1:1 bonus = 0.5, 1:2 bonus = 0.667, 3:2 ...) within 2.5 % are treated as a
                      corporate action – earlier prices are divided, volumes multiplied. Every adjustment is logged.
                      Dividends are not adjusted (small vs the stop distances used; stated in the report).
* universe_mask()     POINT-IN-TIME liquidity universe: on each day a stock is eligible only if its trailing 60-session
                      median turnover >= MIN_TURNOVER and price >= MIN_PRICE and it has >= 250 sessions of history.
                      Survivorship bias remains (Angel lists only current symbols; delisted stocks are absent) – reported.
* costs               Angel One schedule (angelone.in/exchange-transaction-charges, read 6-Nov-2026) + slippage.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EQ = ROOT / "research/data/angel/NSE_EQ"
MIN_TURNOVER = 25e7           # ₹25 crore median daily turnover
MIN_PRICE = 50.0
SPLIT_RATIOS = [1 / 2, 1 / 5, 1 / 10, 2 / 3, 1 / 3, 1 / 4, 3 / 4, 2 / 5, 4 / 5, 5 / 6]
NOTIONAL = 100_000.0          # assumed position value for the fixed (₹) parts of the cost schedule


def load(symbol, iv="ONE_DAY"):
    f = EQ / f"{symbol}_{iv}.csv.gz"
    if not f.exists():
        return None
    d = pd.read_csv(f, parse_dates=["time"])
    return clean(d, intraday=iv != "ONE_DAY")


def clean(d, intraday=False):
    d = d.sort_values("time").drop_duplicates("time", keep="last")
    d = d[(d[["open", "high", "low", "close"]] > 0).all(axis=1)]
    d = d[~((d.high == d.low) & (d.volume <= 0))]
    if intraday:
        t = d.time.dt.hour * 60 + d.time.dt.minute
        d = d[(t >= 555) & (t <= 925)]                       # 09:15 – 15:25 bar starts
    else:
        d["time"] = d.time.dt.normalize()
    d = d.copy()
    d["high"] = d[["open", "high", "close"]].max(axis=1); d["low"] = d[["open", "low", "close"]].min(axis=1)
    return d.reset_index(drop=True)


def adjust_splits(d, log=None, sym=""):
    """Daily candles. Returns adjusted copy; appends (sym, date, ratio) to log."""
    d = d.copy()
    r = (d.open / d.close.shift(1)).values
    fac = np.ones(len(d))
    for i in range(1, len(d)):
        x = r[i]
        if not (x < 0.85 or x > 1.6):
            continue
        for q in SPLIT_RATIOS + [1 / q for q in SPLIT_RATIOS]:
            if abs(x / q - 1) < 0.025:
                fac[:i] *= q
                if log is not None:
                    log.append((sym, str(d.time.iat[i].date()), round(q, 4)))
                break
    for c in ("open", "high", "low", "close"):
        d[c] = d[c] * fac
    d["volume"] = d["volume"] / fac
    d["adj_factor"] = fac
    return d


def universe_mask(d):
    to = (d.close * d.volume).rolling(60, min_periods=40).median().shift(1)
    return ((to >= MIN_TURNOVER) & (d.close.shift(1) >= MIN_PRICE) & (np.arange(len(d)) >= 250)).values


# ── costs (fraction of traded value, round trip, incl. slippage) ──────────────────────────────────────────────────────
def _side(v, brok_pct, stt, stamp, buy, dp=0.0):
    brok = min(20.0, brok_pct * v); brok = max(brok, 5.0) if brok > 0 else 0.0
    exch = 0.000030699 * v; sebi = 1e-6 * v
    gst = 0.18 * (brok + exch + sebi + (dp if dp else 0.0))
    return brok + stt * v + exch + sebi + gst + (stamp * v if buy else 0.0) + dp


def cost_frac(kind, notional=NOTIONAL, slippage=None):
    """kind 'delivery' or 'intraday' -> round-trip cost as a fraction of notional (both legs + slippage)."""
    v = notional
    if kind == "delivery":
        c = _side(v, 0.001, 0.001, 0.00015, True) + _side(v, 0.001, 0.001, 0.0, False, dp=20.0)
        slip = 0.0005 if slippage is None else slippage                      # per side
    else:
        c = _side(v, 0.001, 0.0, 0.00003, True) + _side(v, 0.001, 0.00025, 0.0, False)
        slip = 0.0004 if slippage is None else slippage
    return c / v + 2 * slip


if __name__ == "__main__":
    print(f"delivery round trip {100 * cost_frac('delivery'):.3f}% · intraday {100 * cost_frac('intraday'):.3f}% of ₹{NOTIONAL:,.0f}")

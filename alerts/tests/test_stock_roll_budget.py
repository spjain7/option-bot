"""23-Nov-2026 fixes (alerts/stocks.py):
1) In the 2 sessions before a monthly expiry stock calls move to next month's contract; its short own history is joined
   with the expiring contract's history (shifted by the price gap) so the indicators keep working. Calls stay on next month.
2) An Angel call skipped because the scan's time budget is used up counts as 'blocked' (the stock is retried next cycle,
   not counted as scanned).
python -m alerts.tests.test_stock_roll_budget"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import stocks as SK  # noqa: E402

ok = 0


def check(n, c):
    global ok
    assert c, n
    ok += 1; print("✅", n)


master = pd.DataFrame([
    dict(exch_seg="NFO", instrumenttype="FUTSTK", name="SBIN", symbol="SBIN24NOV26FUT", token="111", expiry_dt=pd.Timestamp("2026-11-24"), lotsize=750, tick=0.05),
    dict(exch_seg="NFO", instrumenttype="FUTSTK", name="SBIN", symbol="SBIN29DEC26FUT", token="222", expiry_dt=pd.Timestamp("2026-12-29"), lotsize=750, tick=0.05),
])
u = SK.universe(master, pd.Timestamp("2026-11-23 10:00"))
check("2 sessions before expiry: call contract = next month, expiring token kept for history",
      u["SBIN"]["symbol"] == "SBIN29DEC26FUT" and u["SBIN"]["token"] == "222" and u["SBIN"]["prev_token"] == "111")
u2 = SK.universe(master, pd.Timestamp("2026-11-16 10:00"))
check("earlier in the month: near contract, no stitching", u2["SBIN"]["token"] == "111" and u2["SBIN"]["prev_token"] is None)


def bars(days, px0, step, vol):
    rows = []
    for k, d in enumerate(days):
        for hh in range(7):
            p = px0 + step * (k * 7 + hh)
            rows.append(dict(time=d + pd.Timedelta(hours=9, minutes=15 + 60 * hh), open=p, high=p + 1, low=p - 1, close=p, volume=vol))
    return pd.DataFrame(rows)


d_all = pd.bdate_range(end="2026-11-23", periods=250)
front = bars(d_all, 500.0, 0.1, 1000)                   # expiring contract: long history, still leads on volume
nxt = bars(d_all[-30:], 0.0, 0.0, 100)
nxt[["open", "high", "low", "close"]] = front[front["time"] >= d_all[-30]][["open", "high", "low", "close"]].values + 5.0
st = SK.stitch_roll(nxt, front)
last = d_all[-1]
check("stitched history is long again (expiring contract's candles before the switch day)", len(st) == len(front))
check("older candles shifted by the measured gap (+5)", np.isclose(st["close"].iloc[0], front["close"].iloc[0] + 5.0))
check("switch-day candles are next month's own", np.allclose(st[st["time"] >= last]["close"].values, nxt[nxt["time"] >= last]["close"].values))
check("no overlap -> next month's series unchanged", SK.stitch_roll(nxt.iloc[:5], front.iloc[:3]).equals(nxt.iloc[:5]))


class Api:
    def __init__(self, over=False):
        self.tokens, self.over = [], over

    def candles(self, ex, tok, iv, a, b):
        self.tokens.append(tok)
        return (front if tok == "111" else nxt).copy()

    def failfast(self):
        return False

    def over_budget(self):
        return self.over


a = Api()
h = SK.candles_1h(a, u["SBIN"], pd.Timestamp("2026-11-23 15:40"), 200)
check("candles_1h fetches both contracts and returns the joined history", a.tokens == ["222", "111"] and len(h) == len(front))
a2 = Api()
SK.candles_1h(a2, u2["SBIN"], pd.Timestamp("2026-11-16 15:40"), 200)
check("no expiring contract -> one fetch only", a2.tokens == ["111"])
check("time budget used up counts as blocked", SK.blocked(Api(over=True)) and not SK.blocked(Api(over=False)))
check("client without the methods -> not blocked", not SK.blocked(object()))
print(f"{ok} checks passed")

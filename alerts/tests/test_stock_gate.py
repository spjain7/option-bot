"""19-Nov-2026 stock-futures gate (alerts/strategies.conflict + stock_gate): one open call per stock on any timeframe, at
most 5 new stock-futures calls a day, 5-session cooldown after a stop-loss; MCX and NIFTY / BANKNIFTY unchanged.
python alerts/tests/test_stock_gate.py"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import strategies as ST  # noqa: E402

ok = 0


def check(n, c):
    global ok
    assert c, n
    ok += 1; print("✅", n)


NOW = "2026-11-19 13:17"
row = lambda name, side="SELL", key=None, status="OPEN", date="2026-11-19", **k: dict(
    status=status, cat="FUTURES", seg=k.pop("seg", "NSE"), name=name, side=side, type="4-hour MACD", time=f"{date} 13:17", date=date,
    key=key or f"RB|RB_STK_4h_MACD0_SELL|{name}|{date} 09:15:00", **k)

# one open call per stock on ANY timeframe
st = {"ledger": [row("MAZDOCK", key="RB|RB_STK_3h_MACD0_SELL|MAZDOCK|2026-11-18 12:15:00")]}
check("stock: same side on another timeframe -> duplicate (was allowed)", "duplicate" in (ST.conflict(st, "MAZDOCK", "SELL", "2h", now=NOW) or ""))
check("stock: opposite side still a contradiction", "contradicts" in ST.conflict(st, "MAZDOCK", "BUY", "1d", now=NOW))
check("stock: another stock is free", ST.conflict(st, "JUBLFOOD", "SELL", "3h", now=NOW) is None)

# MCX / index keep one call per instrument + direction + timeframe
st = {"ledger": [row("GOLD", side="BUY", seg="MCX", key="4H|GOLD|2026-11-19 09:00:00"),
                 row("BANKNIFTY", side="BUY", key="RB|RB_IDX_1d_BO10_BUY|BANKNIFTY|2026-11-17 09:15:00")]}
check("MCX: other timeframe still allowed", ST.conflict(st, "GOLD", "BUY", "2h", now=NOW) is None)
check("index: other timeframe still allowed", ST.conflict(st, "BANKNIFTY", "BUY", "1h", now=NOW) is None)

# daily cap: 5 stock calls a day (MCX / index / experimental / not-published rows do not count)
led = [row(n, key=f"RB|RB_STK_4h_MACD0_SELL|{n}|2026-11-19 09:15:00") for n in ("A1", "A2", "A3", "A4")]
led += [row("GOLD", seg="MCX"), row("NIFTY", side="BUY"), row("VEDL", status="VOID", note="not published – opened 0.6 ATR past the entry"),
        row("POLYCAB", status="CLOSED", note="skipped – gap"), dict(row("ZEE"), cat="FUTURES (EXPERIMENTAL)"),
        row("OLD1", date="2026-11-18"), row("OLD2", date="2026-11-18")]
st = {"ledger": led}
check("4 stock calls today -> 5th allowed", ST.conflict(st, "B1", "SELL", "3h", now=NOW) is None)
st["ledger"].append(row("A5"))
r = ST.conflict(st, "B1", "SELL", "3h", now=NOW)
check("5 stock calls today -> 6th blocked (daily cap)", r is not None and "daily cap" in r)
check("cap never blocks MCX or index calls", ST.conflict(st, "SILVER", "SELL", "3h", now=NOW) is None and ST.conflict(st, "BANKNIFTY", "SELL", "1h", now=NOW) is None)
check("cap resets the next day", ST.conflict(st, "B1", "SELL", "3h", now="2026-11-20 10:17") is None)

# cooldown after a stop-loss on the stock
st = {"ledger": [row("AMBER", status="CLOSED", note="stop-loss", closed="2026-11-13 09:32:01")]}
r = ST.conflict(st, "AMBER", "SELL", "4h", now="2026-11-17 17:17")
check("AMBER stopped 13-Nov -> no new call 17-Nov (2 sessions later)", r is not None and "cooldown" in r)
check("cooldown over after 5 sessions", ST.conflict(st, "AMBER", "SELL", "4h", now="2026-11-21 10:00") is None)
st = {"ledger": [row("AMBER", status="CLOSED", note="rest stopped at cost", closed="2026-11-18 10:00")]}
check("a stop at cost (after T1) is not a loss -> no cooldown", ST.conflict(st, "AMBER", "SELL", "4h", now=NOW) is None)
st = {"ledger": [row("AMBER", status="CLOSED", note="TARGET HIT", closed="2026-11-18 10:00")]}
check("target hit -> no cooldown", ST.conflict(st, "AMBER", "SELL", "4h", now=NOW) is None)

# switch off
os.environ["STOCK_GATE"] = "0"
st = {"ledger": [row("MAZDOCK", key="RB|RB_STK_3h_MACD0_SELL|MAZDOCK|2026-11-18 12:15:00")] + [row(f"X{i}") for i in range(9)]}
check("STOCK_GATE=0 restores the old behaviour", ST.conflict(st, "MAZDOCK", "SELL", "2h", now=NOW) is None and ST.conflict(st, "NEW", "SELL", "2h", now=NOW) is None)
os.environ.pop("STOCK_GATE")
print(f"\n{ok} stock-gate checks passed")

"""28-Oct approved changes: 3h SELL futures calls are logged only (never sent); HA-1 high-accuracy variant is logged beside
every 3h BUY. Deterministic fixtures, no network.   python -m alerts.tests.test_shadow"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import engine as E, breakout as BO  # noqa: E402

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name)
    print("✅", name)


def hourly(s=1, days=260):
    d0 = pd.bdate_range(end="2026-10-27", periods=days)
    rows, px = [], 20000.0
    rng = np.random.default_rng(3)
    for d in d0:
        for h in range(7):
            o = px; px = px * (1 + s * 0.0004 + rng.normal(0, 0.0008)); hi = max(o, px) * 1.0006; lo = min(o, px) * 0.9994
            rows.append((d + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=h), o, hi, lo, px, 1000.0))
    last = pd.Timestamp("2026-10-28")
    ref = max(r[2] for r in rows[-60:]) if s > 0 else min(r[3] for r in rows[-60:])
    for h, (m, v) in enumerate([(1.004, 3000.0), (1.008, 3500.0), (1.012, 4000.0)]):
        c = ref * (m if s > 0 else 2 - m)
        rows.append((last + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=h), c * (0.999 if s > 0 else 1.001), c * 1.001, c * 0.998, c, v))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def day():
    return dict(date="2026-10-28", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])


C_ = dict(symbol="NIFTY25NOV26FUT", token="1", expiry="2026-11-25", lot=75, tick=0.05)
NOW = pd.Timestamp("2026-10-28 12:17")


def test_sell_sent():
    """30-Oct (owner): 3h SELL calls are SENT again (were log-only since 28-Oct)."""
    h = hourly(-1)
    st = E.new_state(); st["day"] = day()
    live = float(h["close"].iloc[-1]) - 3.0
    msgs, info = [], {}
    E._breakouts(st, msgs, info, "NIFTY", "NFO", C_, h, None, NOW, None, {"ltp": live, "exchFeedTime": "28-Oct-2026 12:16:50"})
    real = [p for p in st["bo_active"] if p["tf"] == "3h" and not p.get("shadow")]
    check("3h SELL breakout -> Telegram call + tracked + report-ledger row",
          any("SELL  NIFTY FUT" in m for m in msgs) and len(real) == 1 and real[0]["side"] == "SELL"
          and any(r["key"] == real[0]["key"] for r in st["ledger"]))
    st2 = E.new_state(); st2["day"] = day()
    st2["bo_active"] = [dict(real[0], shadow="3h SELL (log only, not sent)", opened="2026-10-28 12:17:00")]
    m3 = []
    E._promote_shadow_sells(st2, m3, "NIFTY", "NFO", C_, {"ltp": real[0]["entry"] - 5}, pd.Timestamp("2026-10-28 13:02"))
    check("a 3h SELL logged only earlier today is sent once with the current price and added to the report",
          len(m3) == 1 and "Now" in m3[0] and not st2["bo_active"][0].get("shadow") and len(st2["ledger"]) == 1)


def test_buy_sent_and_ha_logged():
    h = hourly(1)
    st = E.new_state(); st["day"] = day()
    live = float(h["close"].iloc[-1]) + 3.0
    msgs = []
    E._breakouts(st, msgs, {}, "NIFTY", "NFO", C_, h, None, NOW, None, {"ltp": live, "exchFeedTime": "28-Oct-2026 12:16:50"})
    real = [p for p in st["bo_active"] if p["tf"] == "3h" and not p.get("shadow")]
    ha = [p for p in st["bo_active"] if p.get("shadow", "").startswith("HA-1")]
    check("3h BUY is still SENT as before (one call + one ledger row)",
          any("BUY  NIFTY FUT" in m for m in msgs) and len(real) == 1 and any(r["key"] == real[0]["key"] for r in st["ledger"]))
    check("HA-1 logged beside it: stop 3 ATR (≤ 2.5 %), target 0.5R, labelled with its conditions, no extra message",
          len(ha) == 1 and abs((ha[0]["target"] - ha[0]["entry"]) / (ha[0]["entry"] - ha[0]["stop"]) - 0.5) < 0.02
          and (ha[0]["entry"] - ha[0]["stop"]) / ha[0]["entry"] * 100 <= 2.5 + 1e-9 and sum("NIFTY FUT" in m for m in msgs) == 1)
    st2 = E.new_state(); st2["day"] = day()
    st2.setdefault("bo_active", []).append(dict(name="NIFTY", tf="3h", side="SELL", entry=1.0, stop=2.0, target=0.0, risk=1.0, best=1.0, trailed=False,
                                 n=0, last_candle="2026-10-27 12:15:00", checked=str(NOW), key="x", shadow="3h SELL (log only, not sent)"))
    m3 = []
    E._breakouts(st2, m3, {}, "NIFTY", "NFO", C_, h, None, NOW, None, {"ltp": live, "exchFeedTime": "28-Oct-2026 12:16:50"})
    check("an open log-only SELL never blocks a real BUY call", any("BUY  NIFTY FUT" in m for m in m3))


if __name__ == "__main__":
    test_sell_sent(); test_buy_sent_and_ha_logged()
    print(f"\nALL {len(OK)} SHADOW CHECKS PASSED")

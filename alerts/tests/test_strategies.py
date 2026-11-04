"""Call-quality layer: strategy registry, conflict guard, shadow routing, scorecard."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import strategies as ST, scorecard as SC, engine as E  # noqa: E402
import paperguard  # noqa: E402


def check(name, cond):
    assert cond, name
    print("✅", name)


check("losing / unproven breakout SELLs are shadow", {("3h", "SELL"), ("1d", "SELL"), ("1m", "SELL")} <= E.SHADOW_ONLY)
check("winning breakout BUYs stay live", not ({("3h", "BUY"), ("1d", "BUY"), ("1m", "BUY")} & E.SHADOW_ONLY))
check("decaying stock OI BUY is shadow", ST.status("STK_OI_BUY") == "SHADOW" and ST.is_live("STK_OI_SELL"))
check("E_BUY_v1 is paper", ST.status("E_BUY_v1") == "PAPER")
for sid, v in ST.S.items():
    st, tier, label, n, w, r, pf, note = v
    if st == "LIVE":
        assert n >= 70 and r > 0, f"{sid}: LIVE needs >= 70 trades and positive expectancy"
    if n is not None and n < 30:
        assert st != "LIVE", f"{sid}: < 30 trades cannot be LIVE"
print("✅ every LIVE strategy has >= 70 backtest trades and positive expectancy; < 30 trades never LIVE")
check("evidence line only for LIVE", "345 backtest trades" in ST.evidence_line("BO_3h_BUY") and ST.evidence_line("BO_3h_SELL") == "")

state = dict(ledger=[dict(status="OPEN", cat="FUTURES", name="GOLD", side="BUY", type="Positional", time="2026-11-04 10:00"),
                     dict(status="CLOSED", cat="FUTURES", name="SILVER", side="BUY", type="Positional", time="2026-11-03 10:00")])
check("opposite call on an instrument with an open call is a contradiction", "contradicts" in ST.conflict(state, "GOLD", "SELL"))
check("same-side second call is a duplicate", "duplicate" in ST.conflict(state, "GOLD", "BUY"))
check("closed calls do not block", ST.conflict(state, "SILVER", "SELL") is None and ST.conflict(state, "ZINC", "BUY") is None)

m = ST.mark("🔴 SELL GOLD FUT", True)
check("shadow messages are marked and blocked by every sender", m.startswith(ST.SHADOW_MARK) and paperguard.blocked(m)
      and ST.mark("x", False) == "x" and not paperguard.blocked("🟢 BUY GOLD FUT"))

led = [dict(key="GOLD|3h|2026-10-30 09:00:00", cat="FUTURES", status="CLOSED", side="SELL", entry=100, sl=102, exit=96, note="TARGET HIT",
            t1_hit=True, mfe_R=2.1, mae_R=-0.3),
       dict(key="GOLD|3h|2026-10-30 18:00:00", cat="FUTURES", status="CLOSED", side="SELL", entry=100, sl=102, exit=102, note="stop-loss hit",
            t1_hit=False, mfe_R=0.4, mae_R=-1.0),
       dict(key="X|1dSTK|2026-10-30", cat="FUTURES", status="CLOSED", side="BUY", entry=10, sl=9, exit=10, note="cancelled – gap"),
       dict(key="GOLD|1w|x", cat="FUTURES", status="CLOSED", side="SELL", entry=1, sl=2, exit=1, note="withdrawn – weekly calls off")]
sc = SC.build(dict(ledger=led, shadow_bo=[dict(label="3h SELL (registry SHADOW, not sent)", r=-1.0)],
                   shadow_calls=[dict(strategy="STK_OI_BUY", R=0.5)],
                   paper={"E_BUY_v1": {"closed": [dict(status="CLOSED", net_R=1.4, t1_hit=True, mfe_R=2.2, mae_R=-0.2)]}}))
s3 = sc["LIVE"]["BO_3h_SELL"]
check("live scorecard: R from entry/SL/exit, cancelled and withdrawn calls excluded", s3["n"] == 2 and abs(s3["exp_R"] - 0.5) < 1e-9
      and s3["profitable"] == 0.5 and s3["pf"] == 2.0 and s3["t1_hit"] == 0.5 and abs(s3["mfe"] - 1.25) < 1e-9)
check("shadow and paper kept separate from live", "3h SELL" in sc["SHADOW"] and "STK_OI_BUY" in sc["SHADOW"]
      and sc["PAPER"]["E_BUY_v1"]["n"] == 1 and "E_BUY_v1" not in sc["LIVE"])
check("strategy ids from ledger keys", SC.strategy_of(dict(key="MCX_HAMMER|GOLD|d", side="BUY")) == "MCX_HAMMER"
      and SC.strategy_of(dict(key="TCS|1dSTK|t", side="SELL")) == "STK_OI_SELL"
      and SC.strategy_of(dict(key="4H|GOLD|t", seg="MCX", side="BUY")) == "FH_MCX_BUY")
check("scorecard text labels small samples", "not yet evidence" in SC.text(dict(ledger=led)))
print("ALL STRATEGY / SCORECARD CHECKS PASSED")

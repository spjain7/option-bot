"""7-Nov: rulebook.describe() must work for EVERY rule (it crashed with IndexError for 8 LIVE rules whose parameter has no "/",
e.g. MACD "zero", BO "N55 vol2", SQZ "BB20" – the WHY message and ledger row of such a call were lost).
python alerts/tests/test_rulebook_describe.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import rulebook as RB  # noqa: E402

for rid, rule in RB.RULES.items():
    txt = RB.describe(rule)
    assert isinstance(txt, str) and txt, rid
assert RB.describe(RB.RULES["RB_MCX_1d_RSIX_BUY"]).startswith("RSI(7) touched 30 / 70"), RB.describe(RB.RULES["RB_MCX_1d_RSIX_BUY"])
assert RB.describe(RB.RULES["RB_MCX_1d_BO55_BUY"]).startswith("close beyond the 55-candle high/low")
print(f"describe() ok for all {len(RB.RULES)} rules")

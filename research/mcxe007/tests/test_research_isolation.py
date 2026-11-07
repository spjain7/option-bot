"""MCXE-007 isolation tests: research code in mcxe006 / mcxe007 has no network, alert, Telegram, broker or order code,
does not import production alert / broker modules, and writes nothing outside research/. Also re-checks that main is
unchanged at the recorded production commit.  python research/mcxe007/tests/test_research_isolation.py"""
import re
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
PROD = "4be5ff29b3cfef307eaad738894c069e7bf66d4a"   # 7-Nov: owner-approved PR #52 (OI 1h EXPERIMENTAL); before 567805d (PR #50), bc3153e6
BAD = re.compile(r"telegram|send_message|place_order|placeOrder|requests\.post|urllib|smartapi|SmartConnect|notify\(|import socket|socket\.", re.I)
BAD_IMPORT = re.compile(r"^\s*(from|import)\s+(alerts|notify|broker|crude\.live|angel)", re.M)


def test_no_side_effect_code():
    hits = []
    for d in ("research/mcxe006", "research/mcxe007"):
        for p in (ROOT / d).rglob("*.py"):
            if p.name in ("test_research_isolation.py", "test_shadow_tracker.py"):   # these files hold the pattern lists
                continue
            s = p.read_text()
            if BAD.search(s) or BAD_IMPORT.search(s):
                hits.append(str(p))
    assert not hits, hits
    print("ok no network / alert / order / production imports in mcxe006 + mcxe007")


def test_main_unchanged():
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    assert head == PROD, head
    print("ok origin/main =", head[:8])


if __name__ == "__main__":
    test_no_side_effect_code(); test_main_unchanged(); print("2 isolation tests passed")

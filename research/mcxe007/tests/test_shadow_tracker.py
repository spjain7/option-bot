"""Shadow-tracker tests: (1) historical replay reproduces every MCXE-006 H1.12L trade exactly (DEV/VALID from the dev
run, OOS from the once-only OOS run); (2) cost breakdown sums to the frozen cost model; (3) the tracker has no network /
alert / order code; (4) rejected-signal accounting is complete (every candidate signal has one status).
python research/mcxe007/tests/test_shadow_tracker.py"""
import re
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.mcxe007.shadow import h112l_tracker as TR  # noqa: E402

R6 = ROOT / "research/mcxe006/results"


def test_replay_reproduces_mcxe006():
    L = TR.main(until="2026-11-03")
    T = L[L.status.isin(["trade", "open"])].copy()
    assert (T.side == "BUY").all()
    ref = pd.concat([pd.read_parquet(R6 / "trades_H1.12L.parquet"), pd.read_parquet(R6 / "oos_trades_H1.12L.parquet")])
    key = lambda x: set(zip(x.iloc[:, 0].astype(str), pd.to_datetime(x.iloc[:, 1]).astype(str)))  # noqa: E731
    # DEV / VALID dev-run trades cap exits at the end of VALID, so compare entries for all, and R values for DEV + OOS
    got = key(T[["commodity", "signal_time"]]); want = key(ref[["inst", "date"]])
    assert want <= got, f"missing trades: {sorted(want - got)[:5]}"
    extra = got - want
    # extra trades can only be signals the dev run skipped because a VALID position was capped early; none expected
    assert not extra, f"unexpected trades: {sorted(extra)[:5]}"
    m = T.merge(ref.rename(columns={"inst": "commodity", "date": "signal_time"}), on=["commodity", "signal_time"])
    full = m[m.period_y.isin(["DEV", "OOS"])]
    assert np.allclose(full.net_R_1x, full.r1, atol=1e-6), "net R differs from MCXE-006"
    assert np.allclose(full.mae_R, full.mae, atol=1e-6) and np.allclose(full.mfe_R, full.mfe, atol=1e-6)
    print("ok replay:", len(m), "trades matched;", len(full), "with identical R/MAE/MFE (DEV+OOS)")


def test_cost_breakdown():
    from research.program import mcx_disc as MD
    for n in ("CRUDEOIL", "GOLD", "NATURALGAS"):
        d, m = TR.cost_breakdown(n, 1000.0 if n != "GOLD" else 120000.0)
        assert abs(sum(d.values()) / m - MD.real_cost(n, 1000.0 if n != "GOLD" else 120000.0)) < 1e-6
    print("ok cost breakdown")


def test_no_side_effects():
    src = (ROOT / "research/mcxe007/shadow/h112l_tracker.py").read_text()
    bad = re.findall(r"telegram|requests|urllib|smartapi|place_order|notify|import socket|socket\.", src, re.I)
    assert not bad, bad
    print("ok no network / alert / order code")


def test_every_signal_has_status():
    L = pd.read_csv(TR.OUT / "ledger_h112l.csv")
    assert L.status.notna().all()
    assert set(L.status) <= {"trade", "open", "rejected_switch_day", "rejected_warmup", "rejected_no_next_bar", "rejected_roll_cap",
                             "rejected_position_open", "rejected_gap_below_stop", "sell_leg_blocking", "sell_leg_open"}
    print("ok statuses:", L.status.value_counts().to_dict())


if __name__ == "__main__":
    test_replay_reproduces_mcxe006(); test_cost_breakdown(); test_no_side_effects(); test_every_signal_has_status()
    print("4 shadow tracker tests passed")

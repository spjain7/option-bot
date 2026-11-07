"""MCXE-004 observability tests.  python research/mcxe004/tests/test_mcxe004.py
Covers: script registration · status transitions · trade counts · win-rate calculation · no DEV/VALID/OOS leakage and no
pre-window data · cost calculation · missing-data handling · rejection-reason logging · failed-script visibility · no false
accuracy claims · reports generated from actual results."""
import json
import re
import sys
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.mcxe004 import register as RG, window as W  # noqa: E402

RES = ROOT / "research/mcxe004/results"


def _tmp():
    return Path(tempfile.mkdtemp()) / "reg.jsonl"


def test_registration_fields():
    p = _tmp()
    with RG.Execution(path=p, script_id="T1", strategy_name="s", market="MCX") as ex:
        ex.finish(total_signals=3, executed_backtest_trades=2, validation_status="RESEARCH_ONLY")
    r = RG.load(p).iloc[-1].to_dict()
    assert set(RG.FIELDS) <= set(r)                               # every required field present
    assert r["status"] == "COMPLETED" and r["script_id"] == "T1" and r["experiment_id"].startswith("T1-")
    assert r["execution_start"] and r["execution_end"]
    assert r["win_rate"] is None or (isinstance(r["win_rate"], float) and np.isnan(r["win_rate"]))   # not fabricated


def test_status_transitions():
    ex = RG.Execution(path=_tmp(), script_id="T2")
    try:
        ex.finish()                                                # PENDING -> COMPLETED is illegal
        raise AssertionError("illegal transition accepted")
    except ValueError:
        pass
    p = _tmp()
    with RG.Execution(path=p, script_id="T3") as ex:
        ex.finish("INSUFFICIENT_DATA", validation_status="INSUFFICIENT_DATA")
    assert RG.load(p).iloc[-1].status == "INSUFFICIENT_DATA"
    try:
        with RG.Execution(path=p, script_id="T4") as ex:
            ex.finish(validation_status="GREAT")                   # unknown status vocabulary
    except ValueError:
        pass
    assert RG.load(p).iloc[-1].validation_status == "ERROR"


def test_failed_script_visibility():
    p = _tmp()
    with RG.Execution(path=p, script_id="T5", strategy_name="boom"):
        raise RuntimeError("data file missing")
    with RG.Execution(path=p, script_id="T6", strategy_name="silent"):
        pass                                                       # never called finish()
    R = RG.load(p)
    assert (R.status == "FAILED").sum() == 2
    assert "data file missing" in R.iloc[0].error_details and R.iloc[1].error_details.startswith("execution ended without")


def test_trade_counts_and_win_rate():
    T = pd.DataFrame(dict(r1=[1.0, -1.0, 2.0, -0.5, 0.0], date=pd.date_range("2026-01-05", periods=5)))
    m = RG.metrics(T, "r1")
    assert m["trades"] == 5 and m["wins"] == 2 and m["losses"] == 3      # 0.0 after costs is not a win
    assert m["win_rate"] == 40.0
    assert m["avg_win"] == 1.5 and m["avg_loss"] == -0.5
    assert abs(m["expectancy_R"] - 0.3) < 1e-9 and m["profit_factor"] == 2.0 and m["net_R"] == 1.5
    assert m["max_drawdown_R"] == 1.0 and m["unique_dates"] == 5


def test_missing_data_handling():
    m = RG.metrics(pd.DataFrame(columns=["r1", "date"]))
    assert m["trades"] == 0 and m["win_rate"] is None and m["expectancy_R"] is None
    st, why = RG.classify(m, m, "intraday", True, False)
    assert st == "INSUFFICIENT_DATA" and "0 trades" in why
    m2 = RG.metrics(pd.DataFrame(dict(r1=[np.nan, 1.0], date=pd.to_datetime(["2026-01-05", "2026-01-06"]))))
    assert m2["trades"] == 1                                       # NaN outcomes are not counted as trades


def test_classify_never_promotes_on_win_rate():
    rng = np.random.default_rng(0)
    T = pd.DataFrame(dict(r1=np.r_[np.full(36, 0.2), np.full(4, -3.0)] + rng.normal(0, 0.01, 40),
                          date=pd.bdate_range("2026-08-10", periods=40)))
    m = RG.metrics(T)
    assert m["win_rate"] >= 89                                     # "90 % accurate" ...
    st, _ = RG.classify(m, m, "intraday", False, True)
    assert st == "REJECTED"                                        # ... but negative expectancy -> rejected
    good = T.assign(r1=np.abs(T.r1) + 0.3)
    mg = RG.metrics(good)
    assert RG.classify(mg, mg, "intraday", True, True)[0] == "PAPER_ONLY"      # window used for selection -> paper only
    assert RG.classify(mg, mg, "intraday", False, False)[0] == "PAPER_ONLY"    # no matched controls -> paper only


def test_window_no_leakage():
    for mk in W.PRIMARY:
        w = W.get(mk)
        assert w["start"] < w["valid_from"] < w["oos_from"] <= w["reference"]
        assert (w["reference"] - w["start"]).days <= 366
    try:
        W.period(pd.Series([W.get("MCX")["start"] - pd.Timedelta(days=1)]), "MCX")
        raise AssertionError("pre-window date accepted")
    except ValueError:
        pass
    T = pd.read_csv(RES / "e1_trades.csv.gz", parse_dates=["date"])
    for mk, wk in (("MCX", "MCX"), ("STOCKS", "NSE_FUT_INTRADAY")):
        x = T[T.mkt == mk]
        w = W.get(wk)
        assert (x.date >= w["start"]).all() and (x.date <= w["reference"] + pd.Timedelta(days=1)).all(), mk
        per = W.period(x.date, wk)
        assert ((per == "OOS") == (x.date >= w["oos_from"]).values).all()
        assert ((per == "DEV") == (x.date < w["valid_from"]).values).all()


def test_cost_calculation():
    T = pd.read_csv(RES / "e1_trades.csv.gz")
    x = T[T.cost_r.notna()]
    assert len(x) > 100
    assert np.allclose(x.r1 - x.r2, x.cost_r, atol=1e-9)          # 2x stress subtracts exactly one more cost
    assert (x.cost_r > 0).all()
    from research.mcxe003 import cost_model as CM
    assert abs(CM.cost_points("NSE_FUT", "X", 1000.0) - 1000.0 * CM.FUT_FRAC) < 1e-9


def test_rejection_reasons_logged():
    S = pd.read_csv(RES / "e1_signals.csv")
    S = S[S.signals > 0]
    for r in S.itertuples():
        reasons = json.loads(r.reasons) if isinstance(r.reasons, str) else {}
        assert r.trades + sum(reasons.values()) == r.signals, r    # every signal is either a trade or has a reason
        assert r.rejected == sum(reasons.values())


def test_no_false_accuracy_claims():
    recs = json.loads((RES / "e1_records.json").read_text())
    sig = dict(strategy="X", script_id="S", market="MCX", instrument="GOLD", side="BUY", entry=1.0, sl=0.9, target=1.2,
               invalidation="close below 0.9", time="2026-11-06 13:00", timeframe="15m", data_age_min=2, cost_R=0.05)
    for ev in recs + [None]:
        card = RG.alert_card(sig, ev)
        assert not re.search(r"\d+\s*%\s*accura|accuracy of \d|probability of success", card, re.I)
        if ev and ev.get("oos", {}).get("trades"):
            o = ev["oos"]
            assert f"{o['wins']}/{o['trades']}" in card and f"{o['unique_dates']} dates" in card and "CI" in card
        if ev and ev["validation_status"] == "INSUFFICIENT_DATA":
            assert "INSUFFICIENT DATA" in card
        assert "not a probability" in card


def test_report_from_actual_results():
    rep = (ROOT / "research/mcxe004/ACCURACY_SUMMARY.md").read_text()
    recs = json.loads((RES / "e1_records.json").read_text())
    for r in recs:
        o = r["oos"]
        assert r["strategy_name"] in rep
        if o["trades"]:
            assert f"| {o['trades']} |" in rep, r["strategy_name"]   # OOS trade counts in the report come from the records


if __name__ == "__main__":
    ok = 0
    for nm, fn in list(globals().items()):
        if nm.startswith("test_"):
            fn(); print("ok", nm); ok += 1
    print(f"{ok} tests passed")

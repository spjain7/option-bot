"""Paper engine v3 tests. Run: python -m paper.tests.test_paper
Synthetic data unless noted; nothing here touches the network, Telegram or any order API."""
import copy, json, re, tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from paper import mcx_daily as P
from paper import contracts as K

ROOT = Path(__file__).resolve().parents[2]
OK = []
CFG0 = copy.deepcopy(P.CFG)


def check(name, cond):
    assert cond, name
    OK.append(name); print("✅", name)


def reset(**over):
    P.CFG.clear(); P.CFG.update(copy.deepcopy(CFG0)); P.CFG.update(over)


def series(n=320, drift=0.0015, seed=1, start="2025-06-02", price=80000.0, last_jump=None):
    rng = np.random.default_rng(seed)
    c = price * np.exp(np.cumsum(rng.normal(drift, 0.008, n)))
    if last_jump:
        c[-1] = c[-2] * (1 + last_jump)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * 1.003; l = np.minimum(o, c) * 0.997
    return pd.DataFrame(dict(time=pd.bdate_range(start, periods=n), open=o, high=h, low=l, close=c, volume=5000.0))


class FakeAngel:
    """Front token -> vendor-stitched history (like Angel); next token -> its own short history (front + carry)."""
    def __init__(self, vendor, carry=600.0, own_days=60):
        self.vendor, self.carry, self.own_days = vendor, carry, own_days

    def candles(self, ex, tok, iv, frm, to):
        v = self.vendor[(self.vendor.time >= pd.Timestamp(frm).normalize()) & (self.vendor.time <= pd.Timestamp(to))]
        if tok == "1":
            return v.copy()
        own = v.tail(self.own_days).copy()
        own[["open", "high", "low", "close"]] += self.carry
        return own

    # deliberately no order methods: the engine must never need them


def master(day, front_days=40):
    d = pd.Timestamp(day)
    return pd.DataFrame([dict(name="GOLD", instrumenttype="FUTCOM", symbol="GOLDF1FUT", token="1", expiry_dt=d + pd.Timedelta(days=front_days)),
                         dict(name="GOLD", instrumenttype="FUTCOM", symbol="GOLDF2FUT", token="2", expiry_dt=d + pd.Timedelta(days=front_days + 60))])


def live_run(state, vendor, now, new=False, front_days=40):
    reset(instruments=["GOLD"], capital=1e9)
    return P.run_live(state_dir=state, new_account=new, now=now, api=FakeAngel(vendor), master=master(now, front_days))


# ─────────────── tests ───────────────
def test_long_only_enforced():
    reset(instruments=["GOLD"], capital=1e9)
    check("default configuration is long-only", P.CFG["long_only"] and P.sides() == (1,))
    v = series(drift=-0.002, seed=4)                                         # strong downtrend: SELL breakouts everywhere
    st = Path(tempfile.mkdtemp())
    P.run_live(state_dir=st, new_account=True, now=v.time.iloc[-1] + pd.Timedelta(days=1), api=FakeAngel(v), master=master(v.time.iloc[-1]))
    log = [json.loads(x) for x in (st / "paper_log.jsonl").read_text().splitlines()] if (st / "paper_log.jsonl").exists() else []
    check("downtrend produces no SELL alert of any status", not any(x.get("direction") == "SELL" for x in log))
    eng = P.Engine(None, P.Book(Path(tempfile.mkdtemp()), new_account=True))
    try:
        eng.emit(dict(status="CONFIRMED PAPER SIGNAL", direction="SELL", instrument="GOLD", contract="X", signal_time="2026-01-01"))
        raised = False
    except AssertionError:
        raised = True
    check("emitting a confirmed SELL in long-only mode is impossible (raises)", raised)


def _breakout_vendor():
    v = series(seed=7, drift=0.0012)
    v.loc[v.index[-1], "close"] = v["high"].iloc[-56:-1].max() * 1.004       # close just above the 55-day high
    v.loc[v.index[-1], "high"] = v["close"].iloc[-1] * 1.001
    return v


def test_two_runs_same_state_no_duplicates():
    v = _breakout_vendor(); st = Path(tempfile.mkdtemp()); now = v.time.iloc[-1] + pd.Timedelta(hours=30)
    b1, e1 = live_run(st, v, now, new=True)
    b2, e2 = live_run(st, v, now)
    check(f"second run on the same state sends no alert again ({len(e1.alerts)} then {len(e2.alerts)})", len(e2.alerts) == 0)
    check("no duplicate pending entries", len(b2.s["pending"]) == len(b1.s["pending"]) <= 1)
    nxt = v.iloc[[-1]].copy(); nxt["time"] = v.time.iloc[-1] + pd.offsets.BDay(1)
    nxt[["open", "high", "low", "close"]] = v.close.iloc[-1] * np.array([1.001, 1.004, 0.999, 1.002])
    v2 = pd.concat([v, nxt], ignore_index=True); now2 = nxt.time.iloc[0] + pd.Timedelta(hours=30)
    b3, _ = live_run(st, v2, now2)
    b4, _ = live_run(st, v2, now2)
    check("the fill is recorded once even when the run repeats", len(b3.s["positions"]) == len(b4.s["positions"]) == 1)


def test_missing_state_stops_safely():
    st = Path(tempfile.mkdtemp())
    try:
        P.Book(st, new_account=False); ok = False
    except P.StateError:
        ok = True
    check("missing state without new-account flag stops (no silent reset)", ok)
    (st / "paper_state.json").write_text("{broken")
    try:
        P.Book(st, new_account=True); ok = False
    except P.StateError:
        ok = True
    check("corrupt state stops even when new-account is requested", ok)


def test_daily_lock_persists():
    reset(capital=1e6)
    st = Path(tempfile.mkdtemp()); b = P.Book(st, new_account=True)
    b.s["day_open_equity"]["2026-03-02"] = 1_000_000; b.s["day_close_equity"]["2026-03-02"] = 950_000
    b.save()
    b2 = P.Book(st)
    check("a 5% loss day locks new entries the next day", b2.locked("2026-03-03") is not None)
    e = P.Engine(None, b2)
    e.book.s["processed"]["__day__"] = "2026-03-03"
    e.run_days([pd.Timestamp("2026-03-03")])                                 # a re-run of the same day
    check("the lock survives a re-run (day-open equity not overwritten)",
          b2.s["day_open_equity"]["2026-03-02"] == 1_000_000 and b2.locked("2026-03-03") is not None)
    check("limits() reports the lock", any("daily loss" in x for x in e.limits("GOLD", 1, 1, "2026-03-03")))


def test_data_validation():
    v = series(n=30)
    bad = pd.concat([v, v.iloc[[5]]], ignore_index=True)
    bad.loc[10, "high"] = bad.loc[10, "low"] * 0.9
    d, issues = K.validate(bad, now=v.time.iloc[-1] + pd.Timedelta(days=10))
    check("duplicate candles removed", d["time"].is_unique and any("duplicate" in x for x in issues))
    check("impossible OHLC removed", any("impossible" in x for x in issues) and len(d) == 29)
    check("stale data detected", any("stale" in x for x in issues))


def test_stale_data_cannot_confirm():
    v = _breakout_vendor(); st = Path(tempfile.mkdtemp())
    _, e = live_run(st, v, v.time.iloc[-1] + pd.Timedelta(days=9), new=True)
    check("stale data never produces a CONFIRMED signal",
          not any(a["status"] == "CONFIRMED PAPER SIGNAL" for a in e.alerts) and any("stale" in " ".join(a.get("blocks", [])) for a in e.alerts))


def test_unknown_roll_blocks_and_exact_roll_adjusts():
    # vendor series with a +3% jump 10 bars ago that the store cannot explain -> unknown switch inside the window
    v = _breakout_vendor()
    v.loc[v.index[-11]:, ["open", "high", "low", "close"]] *= 1.03
    v.loc[v.index[-12], "volume"] = 10; v.loc[v.index[-11], "volume"] = 9000
    st = Path(tempfile.mkdtemp()); store = K.ContractStore(st / "c")
    sig, sw = K.signal_series(v, store, "GOLD", [v.time.iloc[-11]], window=56)
    check("a switch with no recorded contract data is UNKNOWN and flags the window",
          sw and sw[0]["gap"] is None and bool(sig["unknown_in_window"].iloc[-1]))
    # exact: both contracts recorded on the old contract's last day -> gap = new close - old close, applied before
    old = v.iloc[:-10].copy(); new = v.iloc[-12:].copy()
    store.put("GOLDA", "GOLD", "1", "2026-01-01", old)
    nb = new.copy(); last_old = nb["time"] == old["time"].iloc[-1]
    nb.loc[last_old, "close"] = old["close"].iloc[-1] + 777.0             # new contract's close on the old one's last day
    nb.loc[last_old, "high"] = nb.loc[last_old, ["high", "close"]].max(axis=1)
    store.put("GOLDB", "GOLD", "2", "2026-03-01", nb)
    vv = pd.concat([old, new.iloc[2:]], ignore_index=True)
    sig2, sw2 = K.signal_series(vv, store, "GOLD", [], window=56)
    ex = [s for s in sw2 if s["gap"] is not None]
    check("recorded contracts give an EXACT gap", len(ex) == 1 and abs(ex[0]["gap"] - 777.0) < 1e-6)
    check("only bars before the switch are shifted by the exact gap",
          abs(sig2["close"].iloc[0] - vv["close"].iloc[0] - 777.0) < 1e-6 and abs(sig2["close"].iloc[-1] - vv["close"].iloc[-1]) < 1e-9)


def test_front_token_history_not_stored_as_contract():
    v = _breakout_vendor(); st = Path(tempfile.mkdtemp())
    live_run(st, v, v.time.iloc[-1] + pd.Timedelta(hours=30), new=True)
    f1 = pd.read_csv(st / "contracts" / "GOLDF1FUT.csv")
    check("vendor-stitched history is not recorded as the front contract's own candles (bootstrap stores 1 day)", len(f1) == 1)


def test_risk_checked_at_fill():
    reset(instruments=["GOLD"], capital=1e9)
    b = P.Book(Path(tempfile.mkdtemp()), new_account=True)

    class Prov:
        def contract_bar(self, s, d):
            return dict(open=1010.0, high=1015.0, low=1005.0, close=1012.0, volume=100)
    e = P.Engine(Prov(), b)
    pend = dict(instrument="GOLD", contract="X", expiry="x", signal_close=1000.0, level=990.0, atr=50.0, rsi=60,
                signal_time="2026-01-05", risk_rs=0, margin_rs=0,
                alert=dict(instrument="GOLD", direction="BUY", contract="X", expiry="x", signal_time="2026-01-05", close=1000.0))
    P.CFG["max_margin_pct"] = 1e-9
    e.fill(dict(pend), "2026-01-06")
    check("margin limit is re-checked at the fill (rejected)", not b.s["positions"] and e.alerts[-1]["status"] == "NO TRADE")
    P.CFG["max_margin_pct"] = 0.5
    e.fill(dict(pend), "2026-01-07")
    p = b.s["positions"][0]
    check("stop recalculated from the actual fill (fill − 2×ATR)", abs(p["stop"] - (1010.0 + P.SLIP["GOLD"] - 100.0)) < 1e-9)
    check("size from marked-to-market equity and fill-to-stop distance",
          p["lots"] == int(P.CFG["risk_pct"] * P.CFG["capital"] // (100.0 * P.MULT["GOLD"])))   # equity at the fill = capital

    class Gap:
        def contract_bar(self, s, d):
            return dict(open=1040.0, high=1045.0, low=1035.0, close=1040.0, volume=100)
    b2 = P.Book(Path(tempfile.mkdtemp()), new_account=True); e2 = P.Engine(Gap(), b2)
    e2.fill(dict(pend), "2026-01-06")
    check("open > 0.5 ATR above the signal close is rejected (chase)", not b2.s["positions"] and "chase" in " ".join(e2.alerts[-1]["blocks"]))


def test_gap_through_stop():
    reset(instruments=["GOLD"], capital=1e9)
    b = P.Book(Path(tempfile.mkdtemp()), new_account=True)

    class Prov:
        def contract_bar(self, s, d):
            return dict(open=880.0, high=900.0, low=870.0, close=890.0, volume=100)

        def roll_due(self, p, d):
            return None
    e = P.Engine(Prov(), b)
    b.s["positions"].append(dict(id="x", instrument="GOLD", side=1, direction="BUY", contract="X", expiry="x", entry_time="2026-01-05",
                                 entry=1000.0, stop=950.0, R=50.0, lots=2, mult=100, lot_name="GOLD", risk_rs=10000,
                                 margin_rs=1, signal_time="2026-01-02", rsi=60, rolls=0, roll_cost=0.0, exit_pending=False))
    e.manage("GOLD", "2026-01-08", None)
    c = b.s["closed"][0]
    check("gap through the stop fills at the open minus slippage, not at the stop",
          c["exit"] == 880.0 - P.SLIP["GOLD"] and c["gap_loss_rs"] > 0)


def test_no_order_api_and_workflow_safe():
    src = "\n".join(p.read_text() for p in (ROOT / "paper").glob("*.py"))
    check("paper package calls no order API", not re.search(r"placeOrder|modifyOrder|cancelOrder|place_order|\.order\(", src))
    wf = (ROOT / ".github" / "workflows" / "paper-mcx-daily.yml").read_text()
    check("paper workflow: no schedule, Telegram default off, failures not masked",
          "schedule:" not in wf and 'default: "0"' in wf and "|| true\n          echo" not in wf and "exit 1" in wf)
    import config
    run = (ROOT / "runner.py").read_text()
    calls = re.findall(r"mcx_trade\.run\(", run)
    check("hourly MCX engine disabled by its flag, and the flag guards its only call site",
          config.MCXT_ENABLED is False and len(calls) == 1 and "if C.MCXT_ENABLED and mode in" in run)
    check("other engines still enabled", config.OPTION_ENGINE_ENABLED and config.RSI_ENGINE_ENABLED and config.MCX_OPTIONS_ENABLED)
    import sys, runner
    calls, argv = [], sys.argv
    old_angel, runner.Angel = runner.Angel, (lambda: calls.append(1))
    try:
        sys.argv = ["runner.py", "mcxtrade"]; runner.main()
    finally:
        sys.argv, runner.Angel = argv, old_angel
    check("manual 'mcxtrade' run stops early when disabled (does not fall through to the option engine)", not calls)


def test_replay_matches_research_engine():
    try:
        from research import roll_adjust as RA, engine_daily as ED
        RA.load_mcx("GOLD", adjusted=True)
    except Exception:
        print("… skipped replay/research comparison (research data not downloaded)"); return
    reset(capital=1e12, risk_pct=1e-6, max_open_risk_pct=1e9, group_risk_pct=1e9, max_margin_pct=1e9, max_positions=99,
          daily_loss_pct=1e9, max_stop_pct=9, min_contract_volume=0)
    book, eng = P.replay("2016-06-01", mode="estimated", state_dir=tempfile.mkdtemp())
    log = [json.loads(x) for x in book.log_file.read_text().splitlines()]
    sigs = {(x["instrument"], x["signal_time"]) for x in log if x["event"] == "ALERT" and x["status"] == "CONFIRMED PAPER SIGNAL"
            and str(x.get("stage", "")).startswith("signal")}
    r = []
    for n in P.CFG["instruments"]:
        d = ED.add_indicators(RA.load_mcx(n, adjusted=True)[0])
        r.append(ED.run(n, d, dict(rsi_block=True, sides=(1,))))
    r = pd.concat(r); r = r[(pd.to_datetime(r.signal_time) >= "2016-06-01") & r.valid]
    rs = {(a, str(b)[:10]) for a, b in zip(r.instrument, r.signal_time)}
    m = len(sigs & rs) / max(len(rs), 1)
    check(f"replay confirms the research engine's long-only signals ({len(sigs & rs)}/{len(rs)} = {m:.0%})", m >= 0.85)


if __name__ == "__main__":
    for t in (test_long_only_enforced, test_two_runs_same_state_no_duplicates, test_missing_state_stops_safely,
              test_daily_lock_persists, test_data_validation, test_stale_data_cannot_confirm,
              test_unknown_roll_blocks_and_exact_roll_adjusts, test_front_token_history_not_stored_as_contract,
              test_risk_checked_at_fill, test_gap_through_stop, test_no_order_api_and_workflow_safe,
              test_replay_matches_research_engine):
        t()
    reset()
    print(f"\nALL {len(OK)} PAPER-ENGINE CHECKS PASSED")

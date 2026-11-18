"""18-Nov-2026 weekly / monthly cash swing calls (cashstock/swing.py): completed-candle timing, weekly breakout-retest +
delivery, weekly 52-week high + rising delivery, tracking (entry, stop, half at 1R -> stop to cost, target, time exit), one call
per stock, low-delivery warning, NSE delivery-file parsing, messages labelled EXPERIMENTAL / alert only.
python tests/test_cash_swing.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cashstock import swing as S  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


T = pd.Timestamp
# ---------------- completed candles
check(S.complete(T("2026-11-20"), T("2026-11-20"), "W"), "week complete on Friday evening")
check(not S.complete(T("2026-11-18"), T("2026-11-18"), "W"), "week not complete on Wednesday")
check(S.complete(T("2026-11-19"), T("2026-11-20"), "W"), "Friday holiday: Thursday's data is the week's close on Friday's run")
check(not S.complete(T("2026-11-23"), T("2026-11-23"), "W"), "Monday run starts a new (incomplete) week")
check(S.complete(T("2026-11-30"), T("2026-11-30"), "M"), "month complete on its last weekday (Mon 30-Nov)")
check(not S.complete(T("2026-11-27"), T("2026-11-27"), "M"), "month not complete on the Friday before")
check(S.complete(T("2026-10-30"), T("2026-10-30"), "M"), "October: Fri 30-Oct is the last weekday (31st Saturday)")

# ---------------- weekly signals on hand-made weekly candles
wk = pd.date_range("2025-01-03", periods=60, freq="W-FRI")
cols = ["R", "H", "N", "F1", "F2", "F3", "F4"]
O, Hh, Lw, C = (pd.DataFrame(100.0, index=wk, columns=cols) for _ in range(4))
Hh[:] = 101; Lw[:] = 99
for f in ("F1", "F2", "F3", "F4"):
    O[f] = C[f] = 50.0; Hh[f] = 50.5; Lw[f] = 49.5
# R: 20-week breakout in week 40, retest week 42 (low within 2 % of the breakout level 101, green close above it)
C.iloc[40, 0] = 106; Hh.iloc[40, 0] = 106.5; O.iloc[40, 0] = 100.5
C.iloc[41, 0] = 108; Hh.iloc[41, 0] = 109; Lw.iloc[41, 0] = 105; O.iloc[41, 0] = 106
O.iloc[42, 0] = 107; Hh.iloc[42, 0] = 108; Lw.iloc[42, 0] = 102.5; C.iloc[42, 0] = 107.5
C.iloc[43:, 0] = 108; O.iloc[43:, 0] = 108; Hh.iloc[43:, 0] = 109; Lw.iloc[43:, 0] = 107
# N: same pattern, but delivery only 40 %
for X in (O, Hh, Lw, C):
    X["N"] = X["R"]
# H: 52-week closing high in week 55 with delivery 45 % vs a 30 % normal
C.loc[:, "H"] = 100 - 0.05 * np.arange(60); C.iloc[55, 1] = 103; Hh.iloc[55, 1] = 103.5; O.iloc[55, 1] = 99.5
Wk = dict(open=O, high=Hh, low=Lw, close=C, elig=pd.DataFrame(True, index=wk, columns=cols))
dpw = pd.DataFrame(30.0, index=wk, columns=cols); dpw.iloc[42, 0] = 60; dpw.iloc[42, 2] = 40; dpw.iloc[55, 1] = 45
mkt = pd.Series(True, index=wk)
SG, info = S.weekly_signals(Wk, mkt, dpw)
rt = SG["W_RETEST_DP"]; hi = SG["W_HI52_DP"]
check(list(rt.index[rt["R"]]) == [wk[42]], "breakout-retest fires once, on the retest week, with delivery ≥ 50 %")
check(not rt["N"].any(), "same retest with delivery 40 % -> no call")
check(abs(info["lvl"]["R"].iloc[42] - 101) < 1e-9, "retest level = the broken 20-week high")
check(hi["H"].iloc[55] and info["dpx"]["H"].iloc[55] >= 1.2, "52-week high with delivery 1.5× normal fires")
mkt_off = pd.Series(False, index=wk)
check(not S.weekly_signals(Wk, mkt_off, dpw)[0]["W_RETEST_DP"].any().any(), "retest needs the market above its 200-day average")

# ---------------- tracking on daily bars
days = pd.bdate_range("2026-01-05", periods=200)


def panel(path):
    """path: list of (open, high, low, close) for stock 'X' from day 1; day 0 = signal day."""
    n = len(days); o = np.full(n, 100.0); h = o + 1; l = o - 1; c = o.copy()
    for i, (a, b, cc, d) in enumerate(path, start=1):
        o[i], h[i], l[i], c[i] = a, b, cc, d
    df = lambda x: pd.DataFrame({"X": x}, index=days)
    F = dict(open=df(o), high=df(h), low=df(l), close=df(c), volume=df(np.full(n, 1e6)), symbol=pd.Series({"X": "XSTK"}))
    F["value"] = F["close"] * F["volume"]; F["elig"] = df(np.full(n, True)); F["turnover_cr"] = df(np.full(n, 10.0))
    return F


def call(setup):
    return dict(key="X", setup=setup, symbol="XSTK", day=str(days[0].date()), close=100.0, atr=5.0, turnover_cr=10.0, segment="cash-only",
                low=99, lvl=98, dp=55, dpx=1.3, rs=0.9, conf="test")


flat = [(100, 101, 99, 100)] * 199
F = panel([(100, 101, 99, 100), (100, 111, 100.5, 110), (105, 106, 99.5, 101)] + flat[:5])
st = dict(pending=[call("W_HI52_DP")], open=[], closed=[], seen=[]); m = []
S.track(st, F, m, today=days[-1])
x = st["closed"][0] if st["closed"] else {}
check(x.get("entry") == 100 and x.get("half_done") and x.get("exit") == 100 and abs(x.get("R", 0) - 0.5) < 1e-9 and x.get("pnl_100") == 500,
      "52-week setup: half booked at 1R, rest stopped at cost -> +0.5R (₹500 per 100 shares)")
check(any("Book HALF" in y for y in m) and any("ENTRY" in y for y in m), "T1 message says book half / stop to cost")

F = panel([(100, 101, 99, 100), (101, 146, 100, 140)] + flat[:5])
st = dict(pending=[call("W_RETEST_DP")], open=[], closed=[], seen=[]); m = []
S.track(st, F, m, today=days[-1])
x = st["closed"][0]
check(x["exit"] == 145 and abs(x["R"] - 3) < 1e-9 and x["exit_reason"] == "target 3R", "retest setup: SL 3 ATR, target 3R (100 + 3 × 15)")

F = panel([(100, 101, 99, 100), (95, 96, 80, 82)] + flat[:5])
st = dict(pending=[call("W_RETEST_DP")], open=[], closed=[], seen=[]); m = []
S.track(st, F, m, today=days[-1])
check(st["closed"][0]["exit"] == 85 and st["closed"][0]["exit_reason"] == "stop-loss", "stop-loss at entry − 3 ATR")

F = panel([(100, 101, 99, 100)] + flat[:180])
st = dict(pending=[call("W_RETEST_DP")], open=[], closed=[], seen=[]); m = []
S.track(st, F, m, today=days[-1])
x = st["closed"][0]
weeks = (T(x["exit_day"]).to_period("W-FRI") - T(x["entry_day"]).to_period("W-FRI")).n + 1
check(x["exit_reason"].startswith("time exit") and weeks == 26 and T(x["exit_day"]).weekday() == 4, "time exit at the close of week 26")

st = dict(pending=[], open=[], closed=[], seen=[])
F = panel(flat[:10]); m = []
c1 = call("W_RETEST_DP"); c2 = dict(call("W_HI52_DP"))
S.new_calls(st, F, {"W_RETEST_DP": [c1], "W_HI52_DP": [c2]}, m)
check(len(st["pending"]) == 1 and st["pending"][0]["setup"] == "W_RETEST_DP" and len(m) == 2, "one call per stock (priority order), card + WHY")
S.new_calls(st, F, {"W_RETEST_DP": [c1]}, m)
check(len(m) == 2, "the same signal is never sent twice")
txt = "\n".join(m)
check("EXPERIMENTAL" in txt and "Alert only" in txt and "BACKTEST ONLY" in txt and "412 calls" in txt and "cash-only" in txt,
      "message: EXPERIMENTAL, alert only, backtest record, segment")

# ---------------- low-delivery warning
F = panel(flat[:10])
F["volume"].iloc[-1, 0] = 5e6
dp = pd.DataFrame({"X": np.full(len(days), 40.0)}, index=days); dp.iloc[-1, 0] = 12
st = {}; m = []
S.low_dp_warning(F, dp, m, st)
check(len(m) == 1 and "XSTK" in m[0] and "NOT a trade" in m[0], "low-delivery volume spike -> info warning only")
S.low_dp_warning(F, dp, m, st)
check(len(m) == 1, "warning once per day")

# ---------------- NSE delivery file
txt = ("Security Wise Delivery Position - Compulsory Rolling Settlement\n10,MTO,17112026,1,1\nTrade Date <17-NOV-2026>\n"
       "Record Type,Sr No,Name of Security,Quantity Traded,Deliverable Quantity,% of Deliverable\n"
       "20,1,AAA,EQ,1000,600,60.00\n20,2,BBB,BE,500,500,100.00\n")
X = S.parse_mto(txt, T("2026-11-17"))
check(list(X.symbol) == ["AAA"] and X.deliv_pct.iloc[0] == 60, "delivery file parsed (EQ series only)")
print(f"\n{ok} checks passed")

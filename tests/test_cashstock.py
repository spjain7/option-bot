"""Cash-stock positional engine (cashstock/): BUY-only ranking, corporate-action adjustment, market filter, lifecycle
messages, month-end / holiday catch-up, entry confirmation from the next day's open. Offline, synthetic bhavcopy.
Run: python tests/test_cashstock.py"""
import json, sys, tempfile
from pathlib import Path
from unittest import mock
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cashstock import momentum as M, run as RUN  # noqa: E402


def check(name, cond):
    assert cond, name
    print("✅", name)


def bhav(n_stocks=30, days=700, trend=0.0006, seed=1, split_on=None):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range(end="2026-10-30", periods=days)
    rows = []
    for k in range(n_stocks):
        drift = trend * (1 + k / 10)                       # higher k = stronger stock
        px = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, days)))
        prev = np.r_[px[0], px[:-1]]
        for i, t in enumerate(d):
            c = px[i]; pc = prev[i]
            if split_on is not None and k == 0 and i >= split_on:  # 1:1 bonus: raw prices halve from that day
                c = c / 2; pc = pc / 2
            rows.append((t, f"S{k:02d}", "EQ", f"INE{k:06d}01", c, c * 1.01, c * 0.99, c, pc, 1e7, c * 1e7))
    return pd.DataFrame(rows, columns=["date", "symbol", "series", "isin", "open", "high", "low", "close", "prevclose", "volume", "value"])


P = bhav()
C, T = M.panels(M.adjusted(P))
res = M.rank(C, T)
strong = {f"S{k:02d}" for k in range(15, 30)}
check("ranking returns 10 BUY candidates, mostly from the stronger half", res["market_on"] and len(res["picks"]) == 10
      and sum(p["symbol"] in strong for p in res["picks"]) >= 7)
Pd = bhav(trend=-0.0012)
Cd, Td = M.panels(M.adjusted(Pd))
rd = M.rank(Cd, Td)
check("falling market -> filter OFF, no BUY (never a SELL)", not rd["market_on"] and rd["picks"] == [])
text, hold = M.messages(rd, ["S29"])
check("filter off message exits holdings, contains no SELL call", "EXIT" in text and "S29" in text and "SELL" not in text and hold == [])
Ps = bhav(split_on=500)
As = M.adjusted(Ps)
d0 = list(As.values())[0]
check("1:1 bonus adjusted (no -50 % jump in adjusted closes)", (d0.close.pct_change().abs().max()) < 0.2)
Ps2 = Ps.copy(); Ps2.loc[(Ps2.symbol == "S00") & (Ps2.date == Ps2.date.unique()[500]), "prevclose"] *= 2   # UDiFF-style unadjusted prev close
d1 = list(M.adjusted(Ps2).values())[0]
check("unadjusted previous close (UDiFF) gap also adjusted", (d1.close.pct_change().abs().max()) < 0.2)
t2, h2 = M.messages(res, [res["picks"][0]["symbol"], "OLD"])
check("lifecycle text: CONFIRMED SETUP buys, HOLD, EXIT, no-chase limit, live-monitoring label",
      all(x in t2 for x in ("CONFIRMED SETUP", "HOLD", "EXIT", "do not chase", "live-monitoring")) and len(h2) == 10)
check("month-end detection", M.is_month_end("2026-10-30", "2026-11-02") and not M.is_month_end("2026-10-29", "2026-10-30"))

# run.main: month-end rebalance, then next day's entry confirmation from the actual open
tmp = Path(tempfile.mkdtemp()) / "state.json"
RUN.STATE = tmp
with mock.patch.object(RUN, "load", return_value=P):
    RUN.main(dry=True)
st = json.loads(tmp.read_text())
check("month-end run stores holdings and a pending entry for the next session", len(st["holdings"]) == 10 and st["pending"]["entry_day"] == "2026-11-02")
nxt = P[P.date == P.date.max()].copy(); nxt["date"] = pd.Timestamp("2026-11-02")
nxt.loc[nxt.symbol == st["pending"]["buys"][0]["symbol"], "open"] *= 1.10       # one name gaps +10 %
P2 = pd.concat([P, nxt])
out = []
with mock.patch.object(RUN, "load", return_value=P2), mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
    RUN.main(dry=True)
txt = "\n".join(out)
check("next day: ACTIONABLE fills at the actual open, gap beyond the no-chase limit INVALIDATED", "ACTIONABLE BUY" in txt and "INVALIDATED" in txt)
check("no rebalance repeated on the next day", json.loads(tmp.read_text())["last_rebalance"] == "2026-10-30")
Pf = pd.concat([P, P[P.symbol == "S29"].assign(symbol="LIQUIDBEES", isin="INF000LIQ01", close=lambda x: x.close)])
check("ETF / fund units (ISIN INF...) are never ranked", all(p["symbol"] != "LIQUIDBEES" for p in M.rank(*M.panels(M.adjusted(Pf)))["picks"]))
st0 = {"holdings": [], "last_rebalance": "2026-09-30", "pending": None}
tmp.write_text(json.dumps(st0)); out = []
early = P[P.date <= "2026-10-05"]
with mock.patch.object(RUN, "load", return_value=early), mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
    RUN.main(dry=True)
check("no EARLY WARNING 19 sessions before month-end (6-Nov bug)", "EARLY WARNING" not in "\n".join(out))
late = P[P.date <= "2026-10-27"]; out = []; tmp.write_text(json.dumps(st0))
with mock.patch.object(RUN, "load", return_value=late), mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
    RUN.main(dry=True)
check("EARLY WARNING exactly 3 weekdays before month-end", "EARLY WARNING" in "\n".join(out))
print("all cash-stock checks passed")

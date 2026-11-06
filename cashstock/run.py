"""Daily evening job for the cash-stock positional engine (NSE bhavcopy only – no Angel API calls).

1. load the last ~3 years of NSE cash bhavcopies (restored by the workflow from the research-nse-cm branch) and fetch any
   missing days up to today from the NSE archive (research/adapters/nse_cm.py)
2. if today is the last trading session of the month: rank, diff against the holdings in the state file, send the
   monthly message (CONFIRMED SETUP / HOLD / EXIT); three sessions before month-end: EARLY WARNING preview (info only)
3. the session after a rebalance: record the actual opening prices (ACTIONABLE entry confirmed, or INVALIDATED if the
   open gapped beyond the no-chase limit) from that day's bhavcopy
State: CASHSTOCK_STATE (json). Telegram via crude.run.telegram when CASHSTOCK_TELEGRAM=1.
python -m cashstock.run [--dry]"""
import json
import os
import sys
import datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cashstock import momentum as M  # noqa: E402

DATA = ROOT / "research/data/nse_cm"
STATE = Path(os.getenv("CASHSTOCK_STATE", str(ROOT / "state/cashstock/state.json")))


def load(years=3):
    from research.adapters import nse_cm as N
    N.TMP.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    start = today - dt.timedelta(days=21)
    for i in range((today - start).days + 1):                    # top up the last three weeks from the NSE archive
        d = start + dt.timedelta(i)
        if d.weekday() < 5:
            N.fetch(d)
    fs = sorted(DATA.glob("20*.csv.gz"))[-years:]
    parts = [pd.read_csv(f, parse_dates=["date"], low_memory=False) for f in fs]
    parts += [pd.read_csv(f, parse_dates=["date"], low_memory=False) for f in sorted(N.TMP.glob("*.csv.gz"))]
    P = pd.concat(parts, ignore_index=True).drop_duplicates(["date", "symbol", "series"], keep="last")
    return P


def next_session(day, days):
    """next weekday that is not a known exchange holiday (approximation for the calendar: weekend skip)."""
    d = pd.Timestamp(day) + pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d += pd.Timedelta(days=1)
    return d


def main(dry=False):
    P = load()
    A = M.adjusted(P)
    C, T = M.panels(A)
    last = C.index[-1]
    st = json.loads(STATE.read_text()) if STATE.exists() else dict(holdings=[], last_rebalance=None, pending=None)
    msgs = []
    # entry confirmation for the previous rebalance (actual open from today's bhavcopy)
    pend = st.get("pending")
    if pend and pd.Timestamp(pend["entry_day"]) <= last:
        rows = P[(P.date == pd.Timestamp(pend["entry_day"])) & P.symbol.isin([b["symbol"] for b in pend["buys"]])]
        L_ = [f"📋 CASH POSITIONAL – entries on {pend['entry_day']} (actual NSE opening prices)"]
        for b in pend["buys"]:
            r = rows[rows.symbol == b["symbol"]]
            if r.empty:
                L_.append(f"⛔ INVALIDATED {b['symbol']}: no trade that day"); continue
            o = float(r.open.iat[0])
            if o > b["close"] * 1.03:
                L_.append(f"⛔ INVALIDATED {b['symbol']}: opened ₹{o:,.2f}, above the no-chase limit ₹{b['close'] * 1.03:,.2f} – skip")
            else:
                L_.append(f"⚡ ACTIONABLE BUY filled at the open {b['symbol']} ₹{o:,.2f}")
        msgs.append("\n".join(L_)); st["pending"] = None
    nxt = next_session(last, C.index)
    days_left = sum(1 for i in range(1, 6) if (pd.Timestamp(last) + pd.Timedelta(days=i)).weekday() < 5
                    and (pd.Timestamp(last) + pd.Timedelta(days=i)).month == pd.Timestamp(last).month)
    prev_me = C.index[C.index.to_period("M") < last.to_period("M")]
    catch_up = (len(prev_me) and st.get("last_rebalance") is not None
                and pd.Timestamp(st["last_rebalance"]).to_period("M") < prev_me[-1].to_period("M"))   # month-end was a holiday
    if (M.is_month_end(last, nxt) and st.get("last_rebalance") != str(last.date())) or catch_up:
        asof = prev_me[-1] if catch_up and not M.is_month_end(last, nxt) else last
        res = M.rank(C, T, asof=asof)
        last = asof if catch_up else last
        text, hold = M.messages(res, st.get("holdings", []))
        msgs.append(text)
        st["pending"] = dict(entry_day=str(nxt.date()), buys=[p for p in res["picks"] if p["symbol"] not in st.get("holdings", [])])
        st["holdings"], st["last_rebalance"] = hold, str(last.date())
    elif days_left == 3 and st.get("early") != str(last.date()):
        res = M.rank(C, T)
        msgs.append("👀 EARLY WARNING (info only – NOT a trade) · cash positional month-end re-ranking in 3 sessions. "
                    f"Market filter now {'ON' if res['market_on'] else 'OFF'}; current top 10: "
                    + (", ".join(p["symbol"] for p in res["picks"]) or "none (cash)"))
        st["early"] = str(last.date())
    print(f"[cashstock] data to {last.date()} · next session {nxt.date()} · messages {len(msgs)}")
    for m in msgs:
        print(m)
        if not dry and os.getenv("CASHSTOCK_TELEGRAM") == "1":
            from crude.run import telegram
            print("telegram:", telegram(m))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, default=str))


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)

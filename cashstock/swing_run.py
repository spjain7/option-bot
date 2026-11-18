"""Evening job for the weekly / monthly cash swing calls (cashstock/swing.py). NSE bhavcopy + NSE delivery files only – no
Angel API calls, no orders. Runs as its own workflow step after cashstock.run, so a failure here cannot stop the daily
cash alerts. State: CASHSTOCK_SWING_STATE (json). Telegram via crude.run.telegram when CASHSTOCK_TELEGRAM=1.
python -m cashstock.swing_run [--dry]"""
import json
import os
import sys
import datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cashstock import momentum as M, breakout as B, swing as S  # noqa: E402
from cashstock.run import load  # noqa: E402

STATE = Path(os.getenv("CASHSTOCK_SWING_STATE", str(ROOT / "state/cashstock/swing.json")))
DCACHE = ROOT / "research/data/nse_deliv_days"


def main(dry=False):
    today = pd.Timestamp(os.getenv("CASHSTOCK_TODAY") or dt.date.today())
    month_end = S.complete(today - pd.Timedelta(days=1) if today.weekday() >= 5 else today, today, "M")
    nfiles = len(list((ROOT / "research/data/nse_cm").glob("20*.csv.gz")))
    years = 40 if (month_end and nfiles >= 5) else 3                       # full history only for the monthly ATH check
    P = load(years=years)
    A = M.adjusted(P); del P
    F = S.daily(B.wide(A)); del A
    if os.getenv("CASHSTOCK_SWING_ASOF"):                              # replay / dry-run aid: cut the data at a past date
        cut = pd.Timestamp(os.getenv("CASHSTOCK_SWING_ASOF"))
        F = {k: (v.loc[:cut] if isinstance(v, pd.DataFrame) else v) for k, v in F.items()}
    last = F["close"].index[-1]
    full = years > 3 and (F["close"].index[-1] - F["close"].index[0]).days > 4 * 365
    weekly = S.complete(last, today, "W")
    span = 85 if weekly else 3
    days = [d for d in F["close"].index if d >= last - pd.Timedelta(days=span)]
    X = S.fetch_delivery(days, cache=DCACHE)
    dp = S.deliv_panel(F, X)
    fo = S.fo_symbols(last)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    msgs = []
    S.step(st, F, today, dp, msgs, fo=fo, full=full)
    if os.getenv("CASHSTOCK_ALERTS", "1") == "0":
        msgs = []
    print(f"[cash-swing] data to {last.date()} · weekly candle complete {weekly} · monthly check {full and S.complete(last, today, 'M')} · "
          f"delivery days {X.date.nunique() if len(X) else 0} · F&O list {len(fo)} · candidates {st.get('last_candidates')} · "
          f"pending {len(st['pending'])} · open {len(st['open'])} · closed {len(st['closed'])} · messages {len(msgs)}")
    for m in msgs:
        print(m)
        if not dry and os.getenv("CASHSTOCK_TELEGRAM") == "1":
            from crude.run import telegram
            print("telegram:", telegram(m))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, default=str))


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)

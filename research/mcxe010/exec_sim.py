"""MCXE-010: H1.12L research fills vs LIVE alert execution (diagnostic, all 306 historical trades, Angel 5-minute data).
Live rules (production rulebook + four_hour.track, scans at minutes 02/17/32/47 IST):
  entry  = live price ~2 min after the 1h signal candle closes  -> close of the first 5-minute bar of the next hour (:05)
  stop   = checked only at scans -> snapshot = close of the 5-minute bar ending at :00/:15/:30/:45; exit at that price
           when it is at/below the stop (a dip below the stop between scans that recovers is NOT a stop)
  trail  = best completed 1h close - 4 ATR(signal), applied from the next scan (as in rulebook._trail_update)
  time   = 240 one-hour candles; costs = same MCX model
python research/mcxe010/exec_sim.py -> research/mcxe010/exec_sim.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe007.shadow import h112l_tracker as TR  # noqa: E402
from research.program import mcx_disc as MD, liqtl_mcx5 as LM  # noqa: E402


def live_trade(m5, f1, r):
    t_sig = pd.Timestamp(r.signal_time); a = r.atr
    after = m5[m5.time >= t_sig + pd.Timedelta(hours=1)]
    if after.empty:
        return None
    e = float(after.close.iat[0])                       # LTP ~ :02-:05 after the candle close
    st = e - 2 * a; R = e - st; best = e
    cost = MD.real_cost(r.commodity, r.signal_close)
    from research.mcxe006 import engine as EN6
    i = int(np.flatnonzero(f1.time.values == np.datetime64(t_sig))[0])
    ie = int(EN6.iend_positional(f1, 240)[i])                      # same cap as research: 240 bars or before the contract switch
    cap_t = f1.time.iat[ie] + pd.Timedelta(hours=1)
    snaps = after[(after.time + pd.Timedelta(minutes=5)).dt.minute.isin([0, 15, 30, 45])]
    closes_1h = f1.set_index("time").close
    for _, s in snaps.iterrows():
        ts = s.time + pd.Timedelta(minutes=5)
        # trailing update from 1h candles that have completed before this scan
        done = closes_1h[(closes_1h.index > t_sig) & (closes_1h.index + pd.Timedelta(hours=1) <= ts)]
        if len(done):
            best = max(best, float(done.max())); st = max(st, best - 4 * a)
        if s.close <= st:
            g = (s.close - e) / R
            return dict(live_entry=e, live_exit=s.close, live_reason="trail" if st > e - 2 * a + 1e-9 else "stop", live_R1=g - cost / R,
                        live_R2=g - 2 * cost / R, live_slip_entry_R=(e - r.entry_price) / R)
        if ts >= cap_t:
            g = (s.close - e) / R
            return dict(live_entry=e, live_exit=s.close, live_reason="time", live_R1=g - cost / R, live_R2=g - 2 * cost / R,
                        live_slip_entry_R=(e - r.entry_price) / R)
    return None


def main():
    L = pd.read_csv(ROOT / "research/mcxe007/shadow/ledger_h112l.csv", parse_dates=["signal_time", "entry_time", "exit_time"])
    T = L[(L.status == "trade") & (L.side == "BUY") & (~L.forward)]
    rows = []
    for name, g in T.groupby("commodity"):
        f1, d = TR.frame(name)
        m5 = d[["time", "open", "high", "low", "close"]].sort_values("time").reset_index(drop=True)
        for r in g.itertuples():
            x = live_trade(m5, f1, r)
            if x:
                rows.append(dict(commodity=name, signal_time=r.signal_time, period=r.period, research_R1=r.net_R_1x, research_R2=r.net_R_2x,
                                 research_reason=r.exit_reason, **x))
    X = pd.DataFrame(rows)
    X.to_csv(ROOT / "research/mcxe010/exec_sim.csv", index=False)
    S = X.groupby("period")[["research_R2", "live_R2", "live_slip_entry_R"]].mean().round(3)
    S["n"] = X.groupby("period").size()
    print(S.to_string()); print("all:", X[["research_R2", "live_R2", "live_slip_entry_R"]].mean().round(3).to_dict(), len(X))
    stops = X[X.research_reason.isin(["stop", "gap"])]
    print("research-stopped trades: avg research R2", round(stops.research_R2.mean(), 3), "live R2", round(stops.live_R2.mean(), 3),
          "| share survived a research stop live:", round((stops.live_R2 > -0.9).mean(), 3))


if __name__ == "__main__":
    main()

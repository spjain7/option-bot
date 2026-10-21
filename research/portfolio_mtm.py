"""Chronological, mark-to-market portfolio simulation (v2).

Every trading day: open positions are valued at that day's close; entries happen on their entry day at the entry
price if, at that moment, all limits pass:
  * size  = floor(risk% x CURRENT equity / (R points x rupees per point)) lots, main contract, else mini (MCX)
  * margin: approx. initial margin (MARGIN_PCT x contract value) of all open positions <= max_capital_use x equity
  * max open positions, max open risk, max open risk per correlated group (precious / energy / base / index)
  * daily loss limit: no new entries the day after equity fell more than daily_loss% in one day
  * one position per instrument
Skipped trades are counted by reason. Costs are charged at exit. Invalid trades (data holes) are excluded.
"""
import numpy as np
import pandas as pd
from research.instruments import REGISTRY, MARGIN_PCT, GROUP


def simulate(trades, frames, capital=2_500_000, risk_pct=0.01, max_pos=5, max_open_risk=0.05, group_risk=0.02,
             max_capital_use=0.5, daily_loss=0.03, size_on_equity=True):
    t = trades[trades.get("valid", True) != False].copy() if "valid" in trades else trades.copy()  # noqa: E712
    if t.empty:
        return pd.DataFrame(), pd.DataFrame(), dict(taken=0)
    t["entry_time"] = pd.to_datetime(t["entry_time"]); t["exit_time"] = pd.to_datetime(t["exit_time"])
    closes = {n: f.set_index(pd.to_datetime(f["time"]))["close"] for n, f in frames.items()}
    days = sorted(set().union(*[set(c.index) for c in closes.values()]))
    days = [d for d in days if d >= t["entry_time"].min()]
    by_day = {d: g for d, g in t.sort_values("entry_time").groupby("entry_time")}
    cash = capital; open_ = []; log = []; eq_rows = []
    skip = dict(size=0, margin=0, max_pos=0, risk=0, group=0, held=0, daily_loss=0)
    prev_eq, block = capital, False
    last_px = {}
    for d in days:
        for n, c in closes.items():
            if d in c.index:
                last_px[n] = c.at[d]
        # 1) exits scheduled today
        for o in [o for o in open_ if o["exit_time"] == d]:
            pnl = o["lots"] * o["mult"] * o["net_pts"]
            cash += pnl; o["pnl_rs"] = pnl; log.append(o); open_.remove(o)
        # 2) entries today
        eq_now = cash + sum(o["lots"] * o["mult"] * o["side"] * (last_px.get(o["instrument"], o["entry_adj"]) - o["entry_adj"]) for o in open_)
        for _, x in (by_day.get(d, pd.DataFrame()).iterrows() if d in by_day else []):
            if block:
                skip["daily_loss"] += 1; continue
            if any(o["instrument"] == x["instrument"] for o in open_):
                skip["held"] += 1; continue
            if len(open_) >= max_pos:
                skip["max_pos"] += 1; continue
            r = REGISTRY[x["instrument"]]
            budget = risk_pct * (eq_now if size_on_equity else capital)
            mult, lots = r["mult"], int(budget // (x["R_pts"] * r["mult"]))
            if lots == 0 and r.get("mini"):
                mult, lots = r["mini_mult"], int(budget // (x["R_pts"] * r["mini_mult"]))
            if lots == 0:
                skip["size"] += 1; continue
            m_used = sum(o["margin"] for o in open_)
            m_lot = MARGIN_PCT[x["instrument"]] * abs(x["entry_px"]) * mult
            lots = min(lots, int(max(max_capital_use * eq_now - m_used, 0) // m_lot))
            if lots == 0:
                skip["margin"] += 1; continue
            risk = lots * x["R_pts"] * mult
            if sum(o["risk"] for o in open_) + risk > max_open_risk * eq_now:
                skip["risk"] += 1; continue
            grp = GROUP[x["instrument"]]
            if sum(o["risk"] for o in open_ if o["group"] == grp) + risk > group_risk * eq_now:
                skip["group"] += 1; continue
            o = dict(x); o.update(lots=lots, mult=mult, risk=risk, margin=lots * m_lot, group=grp,
                                  side=1 if x["side"] == "LONG" else -1, risk_pct_equity=risk / eq_now)
            if o["exit_time"] == d:                          # same-day stop: book immediately
                pnl = lots * mult * o["net_pts"]; cash += pnl; o["pnl_rs"] = pnl; log.append(o)
            else:
                open_.append(o)
        # 3) mark to market
        unreal = sum(o["lots"] * o["mult"] * o["side"] * (last_px.get(o["instrument"], o["entry_adj"]) - o["entry_adj"]) for o in open_)
        eq = cash + unreal
        block = (eq / prev_eq - 1) < -daily_loss if prev_eq > 0 else False
        prev_eq = eq
        eq_rows.append(dict(date=d, equity=eq, cash=cash, open_positions=len(open_),
                            margin_used=sum(o["margin"] for o in open_), open_risk=sum(o["risk"] for o in open_)))
    eqdf = pd.DataFrame(eq_rows)
    tl = pd.DataFrame(log)
    if eqdf.empty:
        return tl, eqdf, dict(taken=0, **{f"skip_{k}": v for k, v in skip.items()})
    peak = eqdf["equity"].cummax(); dd = eqdf["equity"] / peak - 1
    yrs = max((eqdf["date"].iloc[-1] - eqdf["date"].iloc[0]).days / 365.25, 0.1)
    m = eqdf.set_index("date")["equity"].resample("ME").last().pct_change()
    s = dict(taken=len(tl), **{f"skip_{k}": v for k, v in skip.items()},
             final_equity=round(eqdf["equity"].iloc[-1]), return_pct=round((eqdf["equity"].iloc[-1] / capital - 1) * 100, 1),
             cagr_pct=round(((eqdf["equity"].iloc[-1] / capital) ** (1 / yrs) - 1) * 100, 2) if eqdf["equity"].iloc[-1] > 0 else np.nan,
             max_dd_pct=round(dd.min() * 100, 1), worst_month_pct=round(m.min() * 100, 1),
             max_margin_use_pct=round((eqdf["margin_used"] / eqdf["equity"]).max() * 100, 1),
             win_pct=round((tl["pnl_rs"] > 0).mean() * 100, 1) if not tl.empty else np.nan,
             long_rs=round(tl.loc[tl.side == 1, "pnl_rs"].sum()) if not tl.empty else 0,
             short_rs=round(tl.loc[tl.side == -1, "pnl_rs"].sum()) if not tl.empty else 0)
    return tl, eqdf, s

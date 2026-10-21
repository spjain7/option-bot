"""Portfolio simulation with simultaneous-position and risk limits (fixed capital, no compounding).

Trades are taken in entry order. Size = floor(risk budget / (R points x rupees per point)) lots of the main
contract, else of the mini contract (MCX), else the trade is SKIPPED (1 lot would risk more than the budget).
Also skipped when max open positions or max total open risk would be exceeded, or the instrument is already held.
Equity is booked on exit (closed-trade equity)."""
import numpy as np
import pandas as pd
from research.instruments import REGISTRY


def simulate(trades, capital=2_500_000, risk_pct=0.02, max_pos=6, max_open_risk_pct=0.08):
    if trades is None or trades.empty:
        return pd.DataFrame(), dict(taken=0)
    t = trades.sort_values("entry_time").reset_index(drop=True)
    open_, taken, skip = [], [], {"size": 0, "max_pos": 0, "risk": 0, "held": 0}
    budget = capital * risk_pct
    for _, x in t.iterrows():
        now = pd.Timestamp(x["entry_time"])
        open_ = [o for o in open_ if pd.Timestamp(o["exit_time"]) > now]
        r = REGISTRY[x["instrument"]]
        sc = float(x.get("pt_scale", 1.0) or 1.0)              # proxy points -> MCX rupee points
        Rr = x["R_pts"] * sc
        mult, lots = r["mult"], int(budget // (Rr * r["mult"]))
        if lots == 0 and r.get("mini"):
            mult, lots = r["mini_mult"], int(budget // (Rr * r["mini_mult"]))
        if lots == 0:
            skip["size"] += 1; continue
        if any(o["instrument"] == x["instrument"] for o in open_):
            skip["held"] += 1; continue
        if len(open_) >= max_pos:
            skip["max_pos"] += 1; continue
        risk = lots * Rr * mult
        if sum(o["risk"] for o in open_) + risk > capital * max_open_risk_pct:
            skip["risk"] += 1; continue
        y = dict(x); y.update(lots=lots, lot_mult=mult, risk=risk, pnl_rs=lots * x["net_pts"] * sc * mult,
                              gross_rs=lots * x["gross_R"] * Rr * mult)
        open_.append(y); taken.append(y)
    p = pd.DataFrame(taken)
    if p.empty:
        return p, dict(taken=0, **{f"skip_{k}": v for k, v in skip.items()})
    p = p.sort_values("exit_time")
    eq = capital + p["pnl_rs"].cumsum()
    dd = eq - eq.cummax().clip(lower=capital)
    yrs = max((pd.Timestamp(p["exit_time"].max()) - pd.Timestamp(p["entry_time"].min())).days / 365.25, 0.1)
    s = dict(taken=len(p), **{f"skip_{k}": v for k, v in skip.items()},
             net_rs=round(p["pnl_rs"].sum()), gross_rs=round(p["gross_rs"].sum()),
             return_pct=round(p["pnl_rs"].sum() / capital * 100, 1),
             cagr_pct=round(((eq.iloc[-1] / capital) ** (1 / yrs) - 1) * 100, 2) if eq.iloc[-1] > 0 else np.nan,
             max_dd_rs=round(dd.min()), max_dd_pct=round(dd.min() / capital * 100, 1),
             net_R=round(p["net_R"].sum(), 1), win_pct=round((p["pnl_rs"] > 0).mean() * 100, 1))
    p["equity_rs"] = eq.values
    return p, s

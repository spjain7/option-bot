"""Option-BUYING idea attached to a futures call: BUY call -> buy CE, SELL call -> buy PE.
Strike ~0.55 delta (at / slightly in the money), liquid only (OI, bid-ask), premium levels estimated from delta/gamma
for the futures stop and targets. Read-only market data; no orders."""
import pandas as pd
import market as M

MIN_DTE = {"intraday": 2, "positional": 15}
MAX_BA_PCT, MIN_OI = 6.0, {"MCX": 50, "NFO": 500}


def idea(api, master, name, exch, side, fut_price, stop_pts, t1_pts=None, t2_pts=None, mode="intraday", risk_budget=None):
    ex = "MCX" if exch == "MCX" else "NFO"
    exps = [e for e in M.expiries(master, name, ex) if M.dte(e) >= MIN_DTE[mode]]
    if mode == "positional":
        exps = [e for e in M.monthly_expiries(exps) if M.dte(e) >= MIN_DTE[mode]] or exps
    if not exps:
        return dict(note="no option expiry far enough")
    ch = M.build_chain(api, master, name, exps[0], fut_price, width_pct=0.04 if ex == "MCX" else 0.03, exch=ex)
    if not ch:
        return dict(note="option chain unavailable")
    typ = "CE" if side == "BUY" else "PE"
    d = ch["df"]
    d = d[(d.typ == typ) & d["delta"].notna() & (d["oi"] >= MIN_OI[ex]) & (d["ba_pct"] <= MAX_BA_PCT) & (d["ask"] > 0)]
    if d.empty:
        return dict(note="options illiquid now – use the future")
    o = d.iloc[(d["delta"].abs() - 0.55).abs().argsort().iloc[0]]
    prem, delta, gamma = float(o["ask"]), abs(float(o["delta"])), float(o["gamma"] or 0)
    mv = lambda pts: delta * pts + 0.5 * gamma * pts * pts
    sl = max(prem - mv(stop_pts), prem * 0.6)                          # also never more than a 40% premium loss
    rpp = ch["lot"]
    out = dict(symbol=o["symbol"], token=str(o["token"]), strike=float(o["K"]), typ=typ,
               expiry=f"{pd.Timestamp(ch['expiry']):%d-%b-%Y}", entry=round(prem, 2), delta=round(delta, 2),
               iv=round(float(o["iv"]), 1) if o["iv"] else None, sl=round(sl, 2),
               t1=round(prem + mv(t1_pts), 2) if t1_pts else None, t2=round(prem + mv(t2_pts), 2) if t2_pts else None,
               cost_lot=round(prem * rpp), risk_lot=round((prem - sl) * rpp), rs_per_point=rpp)
    if risk_budget:
        out["lots"] = int(risk_budget // max(out["risk_lot"], 1))
    return out

"""H1.12L research-only forward tracker (protocol: research/mcxe007/SHADOW_TRACKING_PROTOCOL.md, frozen 2026-11-07).
Uses the frozen MCXE-006 code unchanged (strategies.donchian, engine._run / iend_positional) and only adds logging.
No network, no alerts, no orders.  python research/mcxe007/shadow/h112l_tracker.py [--until YYYY-MM-DD]"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.mcxe005 import frames as FR  # noqa: E402
from research.mcxe006 import engine as EN, strategies as ST  # noqa: E402
from research.mcxe006.experiments import EXPS  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402
from research.program import liqtl_mcx5 as LM, mcx_disc as MD  # noqa: E402

OUT = ROOT / "research/mcxe007/shadow"
SPEC = EXPS["H1.12L"]
FWD_START = pd.Timestamp("2026-11-04 09:00")
assert SPEC["fn"] == "donchian" and SPEC["params"] == dict(n=20, k=2.0) and SPEC["exit"] == dict(trail=4.0, maxbars=240) \
    and SPEC["side_only"] == 1 and SPEC["tf"] == 60, "frozen H1.12L spec changed"


def cost_breakdown(name, p):
    """per-lot rupee components of mcx_disc.real_cost (must sum to real_cost x mult)."""
    r = MD.REG[name]; c = MD.COSTS[r["exchange"]]; m = r["mult"]; tb = ts = p * m
    exch = (tb + ts) * c["exch"]; sebi = (tb + ts) * c["sebi"]; brk = 2 * c["brokerage"]
    gst = c["gst"] * (brk + exch + sebi); ctt = ts * c["tax_sell"]; stamp = tb * c["stamp_buy"]; slip = 2 * 1.5 * r["tick"] * m
    d = dict(brokerage=brk, exchange=exch, sebi=sebi, gst=gst, ctt=ctt, stamp=stamp, slippage_spread=slip)
    tot = sum(d.values())
    assert abs(tot / m - MD.real_cost(name, p)) < 1e-6 * max(1, tot)
    return d, m


WS_FROM = pd.Timestamp("2026-11-04 00:00")      # MCXE-010: bars from this time may come from the live WebSocket recordings


def ws_bars(name):
    """5-minute bars of the front (nearest unexpired) MCX contract from the live bot's WebSocket recordings (branch ws-bars;
    validated vs Angel 5-minute closes in research/mcxe010/ws_validation.csv). Only complete 5-minute bars are used."""
    from research.mcxe010 import ws_mcx as WS
    if not hasattr(ws_bars, "B"):
        ws_bars.B = WS.to5m(WS.load_ws())
    b = ws_bars.B[(ws_bars.B.name == name) & (ws_bars.B.minutes == 5)].copy()
    b["exp"] = pd.to_datetime(b.expiry)
    b = b[b.exp >= b.time.dt.normalize()]
    b = b.sort_values(["time", "exp"]).drop_duplicates("time", keep="first")
    return b[["time", "open", "high", "low", "close", "volume", "symbol"]]


def frame(name, until=None, ws=False):
    d = LM.load(name, "FIVE_MINUTE")
    if ws:                                          # MCXE-010: forward bars after the Angel store ends (source tagged)
        from research.search import strategy_search as SS
        b = ws_bars(name)
        b = b[(b.time > d.time.max()) & (b.time >= WS_FROM)]
        if len(b):
            d = pd.concat([d.assign(src="angel"), b.drop(columns="symbol").assign(src="ws")], ignore_index=True)
            sw = SS.switch_days(name, "MCX", d)
            day = d["time"].dt.normalize()
            d["switch"] = day.isin(sw) & (day != day.shift(1))
    w = W.get("MCX")
    d = d[d.time >= w["start"]]
    if until is not None:
        d = d[d.time < pd.Timestamp(until) + pd.Timedelta(days=1)]
    d = d.reset_index(drop=True)
    d["switch"] = d.switch.fillna(False).astype(bool)
    f = FR.mcx_positional(name, 60, d)
    f.attrs["wkey"] = "MCX"
    return f, d


def replay(f, contract):
    """same filters and engine call as mcxe006 engine.run(oos=True) + logging of every candidate signal."""
    s = ST.donchian(f, extra=None, **SPEC["params"])
    side = np.asarray(s["side"], np.int64)
    n = len(f); idx = np.arange(n)
    a = f.atr.values.astype(float)
    o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
    IE = EN.iend_positional(f, SPEC["exit"]["maxbars"])
    cand = np.flatnonzero(side != 0)    # frozen semantics: the two-sided rule occupies the slot; SELL legs are not traded
    rows = []
    busy = -1
    name = f.attrs["name"]
    for i in cand:
        t = f.time.iat[i]
        sd = int(side[i])
        rec = dict(signal_time=t, commodity=name, contract=contract, side="BUY" if sd > 0 else "SELL_LEG_NOT_TRADED",
                   forward=bool(t >= FWD_START), signal_close=c[i],
                   data_source="ws (live bot WebSocket)" if (USE_WS and t >= WS_FROM) else "angel 5m store",
                   level_20bar_high=float(pd.Series(h).shift(1).rolling(20).max().iat[i]), atr=a[i])
        if not f.sig_ok.iat[i]:
            rec["status"] = "rejected_switch_day"
        elif i < s.get("warm", 60) or not (np.isfinite(a[i]) and a[i] > 0):
            rec["status"] = "rejected_warmup"
        elif i >= n - 1:
            rec["status"] = "rejected_no_next_bar"
        elif not IE[i] > i:
            rec["status"] = "rejected_roll_cap"
        elif i <= busy:
            rec["status"] = "rejected_position_open"
        else:
            cost = MD.real_cost(name, c[i])
            r = EN._sim(o, h, l, c, i, sd, np.nan, s["dist"][i], IE[i], cost, a[i], 0.0, 0.5, False, 0.0,
                        SPEC["exit"]["trail"], np.zeros(n, np.bool_), np.zeros(n, np.bool_))
            if r[2] < 0:
                rec["status"] = "rejected_gap_below_stop"
            else:
                net, gross, kx, k0, mae, mfe, et = r
                kx, k0 = int(kx), int(k0)
                busy = kx
                e = o[k0]; st0 = e - sd * 2.0 * a[i]; R = sd * (e - st0)
                if sd > 0:
                    best = max(e, c[k0:kx + 1].max()) if kx > k0 else e
                    trail_final = max(st0, best - 4.0 * a[i])
                else:
                    best = min(e, c[k0:kx + 1].min()) if kx > k0 else e
                    trail_final = min(st0, best + 4.0 * a[i])
                still_open = (kx == n - 1) and (EN.ETYPE[int(et)] == "time") and (kx - k0 < SPEC["exit"]["maxbars"] - 1)
                comp, mult = cost_breakdown(name, c[i])
                tot = sum(comp.values())
                stt = ("open" if still_open else "trade") if sd > 0 else ("sell_leg_open" if still_open else "sell_leg_blocking")
                rec.update(status=stt, entry_time=f.time.iat[k0], entry_price=e, initial_stop=st0,
                           R_points=R, trail_stop_final=trail_final, exit_time=f.time.iat[kx],
                           exit_reason="open" if still_open else EN.ETYPE[int(et)],
                           exit_price=e + sd * gross * R if not still_open else np.nan, hold_bars=kx - k0,
                           hold_hours=(f.time.iat[kx] - f.time.iat[k0]).total_seconds() / 3600, mae_R=mae, mfe_R=mfe,
                           gross_R=gross, net_R_1x=net, net_R_2x=net - cost / R, cost_R=cost / R,
                           cost_rs_per_lot=tot, net_rs_per_lot_1x=net * R * mult, **{f"cost_{k}": v for k, v in comp.items()})
                rec["period"] = "FORWARD" if rec["forward"] else str(W.period([t], "MCX")[0])
                if not rec["forward"] and t < FWD_START and f.time.iat[kx] >= FWD_START:
                    rec["carry_over"] = True
        rows.append(rec)
    return rows


def data_issues(name, d, f):
    iss = []
    dup = 0  # loader already dropped duplicates; count them from the raw file
    man = pd.read_csv(LM.DATA / "manifest.csv")
    m = man[(man.exch == "MCX") & (man.name == name) & (man.interval == "FIVE_MINUTE") & (man.front_stitched.astype(str) == "True")]
    raw = pd.read_csv(LM.DATA / "MCX" / f"{m.symbol.iat[0]}_FIVE_MINUTE.csv", usecols=["time"], parse_dates=["time"])
    raw = raw[raw.time >= W.get("MCX")["start"]]
    dup = int(raw.time.duplicated().sum())
    if dup:
        iss.append(dict(commodity=name, kind="duplicate_5m_timestamps_dropped", detail=dup))
    per_day = f.groupby(f.day).size()
    med = per_day.median()
    for day, k in per_day[per_day < med - 2].items():
        iss.append(dict(commodity=name, kind="short_session_1h_bars", detail=f"{day.date()} {k} bars (median {med:.0f})"))
    days = pd.Series(sorted(f.day.unique()))
    gaps = days.diff().dt.days
    for dd, g in zip(days, gaps):
        if g and g > 4:
            iss.append(dict(commodity=name, kind="gap_in_sessions", detail=f"{g:.0f} days before {dd.date()}"))
    last = f.time.max()
    stale = (pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize() - last.normalize()).days
    if stale > 3:
        iss.append(dict(commodity=name, kind="stale_data", detail=f"last bar {last} ({stale} days old)"))
    return iss, m.symbol.iat[0]


USE_WS = False


def main(until=None):
    allrows, issues = [], []
    for name in FR.MCX7:
        f, d = frame(name, until, ws=USE_WS)
        iss, contract = data_issues(name, d, f)
        issues += iss
        allrows += replay(f, contract)
    L = pd.DataFrame(allrows).sort_values("signal_time").reset_index(drop=True)
    L.to_csv(OUT / "ledger_h112l.csv", index=False)
    pd.DataFrame(issues).to_csv(OUT / "data_issues.csv", index=False)
    F = L[(L.forward) & (L.status == "trade")]
    last_bar = max(frame(n, until, ws=USE_WS)[0].time.max() for n in FR.MCX7[:1])
    st = [f"# H1.12L shadow status (generated {pd.Timestamp.now(tz='Asia/Kolkata'):%Y-%m-%d %H:%M} IST)", "",
          f"- Data available to: {last_bar} (first commodity checked); forward period starts {FWD_START}",
          f"- Forward signals logged: {int(L.forward.sum())} · closed forward trades: {len(F)} on {F.signal_time.dt.normalize().nunique() if len(F) else 0} dates"
          f" · open: {int(((L.forward) & (L.status == 'open')).sum())}",
          f"- Checkpoint 1 (≥ 30 trades, ≥ 20 dates): {'reached' if len(F) >= 30 and F.signal_time.dt.normalize().nunique() >= 20 else 'NOT reached'}",
          f"- Data issues logged: {len(issues)} (see data_issues.csv)"]
    if len(F):
        st.append(f"- Forward net R per trade: 1x {F.net_R_1x.mean():+.3f}, 2x {F.net_R_2x.mean():+.3f}; win {100 * (F.net_R_1x > 0).mean():.1f}%")
    (OUT / "STATUS.md").write_text("\n".join(st) + "\n")
    print("\n".join(st))
    return L


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--until"); ap.add_argument("--ws", action="store_true"); a = ap.parse_args()
    USE_WS = a.ws
    main(a.until)

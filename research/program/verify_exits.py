"""VERIFY-EXITS (28-Oct-2026) – owner's cross-check after the 360ONE case: independently re-walk EVERY logged call candle by
candle and classify how it ended, so no exit depends on a hidden assumption.

For each call (hourly hammer/hanging-man log and daily pattern log) the candles from entry to exit are re-read from the raw
data and the exit candle is classified:
  gap target    – the candle OPENED beyond the target (target filled at the open)          → win, certain
  gap stop      – the candle OPENED beyond the stop                                         → loss, certain
  clean target  – the candle touched the target but not the stop                          → win, certain
  clean stop    – the candle touched the stop but not the target                          → loss, certain
  both touched  – the same candle touched the stop AND the target, opening between them;
                  the order inside the candle is unknown. The backtest books it as a STOP (cautious).
                  If 15-minute candles exist for that time (Aug–Oct 2026, 44 NSE + 4 MCX contracts) the order is
                  resolved from them; otherwise it stays unknown and is shown both ways.
  time / roll / data end
It also checks that no EARLIER candle in the trade already touched the stop or target (would be a logic error).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import reversal as RV, emax as EX  # noqa: E402
from research.search import strategy_search as SS, stock_search as SR  # noqa: E402

OUT = ROOT / "research/program/results"
M15 = {p.stem[4:]: p for d in ("obuy", "obuy_mcx") for p in (ROOT / "research/data" / d).glob("fut_*.csv")}
_m15 = {}


def m15(name):
    if name not in _m15:
        p = M15.get(name)
        _m15[name] = None if p is None else pd.read_csv(p, parse_dates=["time"]).sort_values("time").reset_index(drop=True)
    return _m15[name]


def resolve(name, t0, t1, side, st, tp):
    """Order of stop/target inside [t0, t1) from 15-minute candles. Returns 'target', 'stop', 'both' or None."""
    d = m15(name)
    if d is None:
        return None
    x = d[(d["time"] >= t0) & (d["time"] < t1)]
    if x.empty:
        return None
    for o, h, l in zip(x["open"], x["high"], x["low"]):
        s_hit = (l <= st) if side > 0 else (h >= st)
        t_hit = (h >= tp) if side > 0 else (l <= tp)
        if side * (o - tp) >= 0:
            return "target"
        if side * (o - st) <= 0:
            return "stop"
        if s_hit and t_hit:
            return "both"
        if s_hit:
            return "stop"
        if t_hit:
            return "target"
    return None


def check(L, frame_of, tcol, step):
    out = []
    for (seg, name), g in L.groupby(["segment", "instrument"]):
        f = frame_of(seg, name)
        if f is None:
            continue
        idx = pd.Series(np.arange(len(f)), index=pd.to_datetime(f["time"]).values)
        o, h, l, c = (f[x].values for x in ("open", "high", "low", "close"))
        for r in g.itertuples():
            side = 1 if r.call.startswith("BUY") else -1
            j0, j = idx.get(pd.Timestamp(getattr(r, f"entry_{tcol}"))), idx.get(pd.Timestamp(getattr(r, f"exit_{tcol}")))
            if j0 is None or j is None:
                out.append(dict(segment=seg, instrument=name, kind="not found")); continue
            st, tp = r.stop, r.target_2R
            early = False
            for k in range(j0 + 1, j):
                if (side * (o[k] - st) <= 0) or (side * (o[k] - tp) >= 0) or ((l[k] <= st) if side > 0 else (h[k] >= st)) or \
                        ((h[k] >= tp) if side > 0 else (l[k] <= tp)):
                    early = True; break
            s_hit = (l[j] <= st) if side > 0 else (h[j] >= st)
            t_hit = (h[j] >= tp) if side > 0 else (l[j] <= tp)
            if j > j0 and side * (o[j] - tp) >= 0:
                kind = "gap target"
            elif j > j0 and side * (o[j] - st) <= 0:
                kind = "gap stop"
            elif s_hit and t_hit:
                kind = "both touched"
            elif t_hit:
                kind = "clean target"
            elif s_hit:
                kind = "clean stop"
            else:
                kind = "time / roll / end"
            res = None
            if kind == "both touched":
                t0 = pd.Timestamp(f["time"].iat[j]); t1 = t0 + step
                res = resolve(name, t0, t1, side, st, tp)
            win_net = (side * (tp - r.entry) - r.cost_pts) / r.risk_pts
            out.append(dict(segment=seg, instrument=name, call=r.call, pattern_time=getattr(r, f"pattern_{'time' if tcol == 'time' else 'day'}"),
                            kind=kind, booked=r.exit_reason, net_R=r.net_R, net_R_if_target=round(win_net, 2), early_touch=early,
                            m15=res))
    return pd.DataFrame(out)


def hourly_frame(seg, name):
    if seg in ("MCX", "INDEX"):
        ex = dict((n, e) for e, n in SS.NAMES)[name]
        return RV.mcx_index_1h(name, ex)[1]
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")
    d = RV.stock_1h(name, int(man.loc[name, "lot"]))
    return None if d is None else d[1]


_daily = {}


def daily_frame(seg, name):
    if name not in _daily:
        if seg in ("MCX", "INDEX"):
            ex = dict((n, e) for e, n in SS.NAMES)[name]
            job = ("mi", name, ex)
        else:
            man = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")
            job = ("stk", name, int(man.loc[name, "lot"]))
        fr = [x for x in EX.frames(job) if x[0].endswith("1d")]
        _daily[name] = fr[0][1].reset_index(drop=True) if fr else None
    return _daily[name]


def summary(V, label):
    rows = []
    for (seg, call), g in V.groupby(["segment", "call"]):
        both = g["kind"] == "both touched"
        resolved_t = both & (g["m15"] == "target")
        lo = g["net_R"].mean()
        mid = np.where(resolved_t, g["net_R_if_target"], g["net_R"]).mean()
        hi = np.where(both, g["net_R_if_target"], g["net_R"]).mean()
        rows.append(dict(log=label, segment=seg, call=call, trades=len(g),
                         gap_target=int((g["kind"] == "gap target").sum()), clean_target=int((g["kind"] == "clean target").sum()),
                         clean_stop=int((g["kind"] == "clean stop").sum()), gap_stop=int((g["kind"] == "gap stop").sum()),
                         both_touched=int(both.sum()), resolved_by_15m=int((both & g["m15"].isin(["target", "stop"])).sum()),
                         of_which_target=int(resolved_t.sum()), time_or_roll=int((g["kind"] == "time / roll / end").sum()),
                         logic_errors=int(g["early_touch"].sum()), not_found=int((g["kind"] == "not found").sum()),
                         avg_R_booked=round(lo, 3), avg_R_with_15m=round(mid, 3), avg_R_if_all_both_were_targets=round(hi, 3)))
    return pd.DataFrame(rows)


def main():
    H = pd.read_csv(OUT / "ham_log_all.csv.gz")
    H["call"] = H["call"].str.split(" ").str[0]
    VH = check(H, hourly_frame, "time", pd.Timedelta(hours=1))
    D = pd.read_csv(OUT / "dcp_log_all.csv.gz")
    D["segment"] = D["segment"].str.replace(" 1d", "")
    D["call"] = D["call"] + " " + D["pattern"]
    VD = check(D, daily_frame, "day", pd.Timedelta(days=1))
    VH.to_csv(OUT / "verify_hourly.csv.gz", index=False); VD.to_csv(OUT / "verify_daily.csv.gz", index=False)
    S = pd.concat([summary(VH, "hourly hammer / hanging man"), summary(VD, "daily patterns")])
    S.to_csv(OUT / "verify_summary.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 30)
    print(S.to_string(index=False))


if __name__ == "__main__":
    main()

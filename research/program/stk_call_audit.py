"""STK-CALL-AUDIT-001 (19-Nov-2026, owner: "too many calls, they hit SL – find the exact cause, track which loses and why,
resolve"). Live stock-futures SELL rules re-simulated trade by trade on the research data (Angel 1-hour stock futures
2022-26, 181 F&O stocks, 2x costs, next-open entry, stop first – the SEARCH-V2 harness), then the PORTFOLIO filters that
would cut the number of calls are tested, each judged in all three periods (p1 / p2 / p3 as in SEARCH-V2):
  live rules  RB_STK_3h_MACD0_SELL (1.5 ATR / 2R) · RB_STK_3h_EMA921_SELL (2/3) · RB_STK_2h_SQZ_SELL (2/3, day-anchored 2h)
              RB_STK_4h_MACD0_SELL (1.5/2, day-anchored 4h) · FH NFO 4h breakdown (BO N5 vol2, 2/2) · FH NFO3H (BO N5 vol2, 1.5/2)
  P0  as live: one open call per stock + direction + timeframe (alerts/strategies.conflict)
  P1  one open call per stock (any timeframe / rule)
  MKT SELL only when market breadth is weak: >= 55 % of the 181 stocks closed below their 50-day EMA the previous session
  NIF SELL only when NIFTY futures closed below their 20-day EMA the previous session
  CAP at most N (3 / 5) new stock calls per day (first come; same candle -> rule with the higher research R first)
  CD  no new call on a stock for 5 sessions after a stop-loss on it
python research/program/stk_call_audit.py -> results/stk_call_audit_trades.csv.gz, results/stk_call_audit_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402

OUT = ROOT / "research/program/results"
# id, tf, fam, par, filt, k, r, research R (priority)
LIVE = [("RB_STK_2h_SQZ_SELL", "2h", "SQZ", "BB20", "DT", 2.0, 3.0, 0.27), ("RB_STK_4h_MACD0_SELL", "4h", "MACD", "zero", "DT", 1.5, 2.0, 0.19),
        ("RB_STK_3h_MACD0_SELL", "3h", "MACD", "zero", "DT", 1.5, 2.0, 0.17), ("RB_STK_3h_EMA921_SELL", "3h", "EMAX", "9/21", "DT", 2.0, 3.0, 0.15),
        ("FH_NFO_4h_SELL", "4h", "BO", "N5 vol2", "DT", 2.0, 2.0, 0.14), ("FH_NFO3H_SELL", "3h", "BO", "N5 vol2", "DT", 1.5, 2.0, 0.13)]
PRI = {x[0]: x[7] for x in LIVE}


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1 = seg["STOCKS 1h"]; fd = seg["STOCKS 1d"][0]
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    frames = {}
    if "STOCKS 3h" in seg:
        frames["3h"] = seg["STOCKS 3h"]
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs)
        frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C, cost) in frames.items():
        rules = [r for r in LIVE if r[1] == tf]
        if not rules or len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        sets = {(a, b, c): (x, y) for a, b, c, x, y in SV.signal_sets(f, dtr, tf)}
        sets.update({(a, b, c): (x, y) for a, b, c, x, y in SA.signal_sets(f, dtr)})
        t = pd.to_datetime(f["time"]).values
        for rid, _, fam, par, flt, k, r, _ in rules:
            if (fam, par, flt) not in sets:
                print("missing", rid, flush=True); continue
            s = sets[(fam, par, flt)][1]
            sig = np.where(np.nan_to_num(np.asarray(s, float)) > 0, -1, 0)
            for x in H.simulate(f, sig, -1, k, r, SV.MAXH[tf], 0, np.asarray(cost, float), start=210):
                if x["status"] == "trade":
                    j = min(x["i"] + x["bars"], len(t) - 1)
                    rows.append((rid, tf, job[1], t[x["i"]], t[j], x["r2"], x["exit"]))
    d = fd[["time", "close"]].copy(); d["time"] = pd.to_datetime(d["time"]).dt.normalize()
    d["below50"] = d["close"] < d["close"].ewm(span=50, adjust=False).mean()
    return rows, d.set_index("time")["below50"].rename(job[1])


def stats(r):
    r = np.asarray(r, float)
    if not len(r):
        return dict(n=0)
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    ls = cur = 0
    for v in r:
        cur = cur + 1 if v <= 0 else 0; ls = max(ls, cur)
    gw, gl = r[r > 0].sum(), -r[r <= 0].sum()
    return dict(n=len(r), win=round((r > 0).mean() * 100, 1), expR=round(r.mean(), 3), PF=round(gw / gl, 2) if gl > 0 else np.inf,
                totalR=round(r.sum(), 1), maxDD_R=round(dd, 1), lose_streak=ls)


def portfolio(T, per_tf=True, mkt=None, cap=None, cooldown=0):
    T = T.sort_values(["t_in", "pri"], ascending=[True, False])
    keep = []; open_until = {}; day_n = {}; stop_day = {}
    days = pd.DatetimeIndex(sorted(T.day.unique()))
    pos = {d: i for i, d in enumerate(days)}
    for i, x in T.iterrows():
        if mkt is not None and not bool(mkt.get(x.day, False)):
            continue
        k = (x["name"], x["tf"]) if per_tf else x["name"]
        if k in open_until and x["t_in"] <= open_until[k]:
            continue
        if cooldown and x["name"] in stop_day and pos[x.day] - pos[stop_day[x["name"]]] <= cooldown:
            continue
        if cap and day_n.get(x.day, 0) >= cap:
            continue
        open_until[k] = x["t_out"]; day_n[x.day] = day_n.get(x.day, 0) + 1; keep.append(i)
        if x["exit"] == "stop":
            stop_day[x["name"]] = pd.Timestamp(x["t_out"]).normalize() if pd.Timestamp(x["t_out"]).normalize() in pos else x.day
    return T.loc[keep]


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        parts = [x for x in p.imap_unordered(one, J, chunksize=2) if x is not None]
    T = pd.DataFrame([r for rows, _ in parts for r in rows], columns=["rule", "tf", "name", "t_in", "t_out", "r", "exit"])
    T["day"] = pd.to_datetime(T.t_in).dt.normalize(); T["pri"] = T.rule.map(PRI)
    tv = T.t_in.values.astype("datetime64[ns]")
    T["split"] = np.where(tv < SV.P1, "p1", np.where(tv < SV.P2, "p2", "p3"))
    B = pd.concat([b for _, b in parts], axis=1).sort_index()
    breadth = B.mean(axis=1).shift(1)                                         # previous session
    weak = (breadth >= 0.55)
    try:
        nf = H.nseidx("NIFTY"); nf["time"] = pd.to_datetime(nf["time"]).dt.normalize()
        nfs = nf.set_index("time")["close"]; nif = (nfs < nfs.ewm(span=20, adjust=False).mean()).shift(1)
    except Exception as e:  # noqa: BLE001
        print("NIFTY unavailable", e); nif = None
    T.to_csv(OUT / "stk_call_audit_trades.csv.gz", index=False)
    print("exit reasons:", T.exit.value_counts().to_dict(), "days", T.day.nunique(), "range", T.day.min().date(), T.day.max().date(), flush=True)
    ndays = len(pd.bdate_range(T.day.min(), T.day.max()))
    cfg = {"P0 live (stock+dir+tf)": dict(per_tf=True), "P1 one per stock": dict(per_tf=False),
           "P1 + MKT breadth": dict(per_tf=False, mkt=weak), "P1 + CAP3": dict(per_tf=False, cap=3), "P1 + CAP5": dict(per_tf=False, cap=5),
           "P1 + CD5": dict(per_tf=False, cooldown=5), "P1 + MKT + CAP3": dict(per_tf=False, mkt=weak, cap=3),
           "P1 + MKT + CAP5 + CD5": dict(per_tf=False, mkt=weak, cap=5, cooldown=5), "P1 + MKT + CAP3 + CD5": dict(per_tf=False, mkt=weak, cap=3, cooldown=5)}
    if nif is not None:
        cfg.update({"P1 + NIF": dict(per_tf=False, mkt=nif), "P1 + NIF + CAP3 + CD5": dict(per_tf=False, mkt=nif, cap=3, cooldown=5),
                    "P1 + NIF + MKT + CAP3 + CD5": dict(per_tf=False, mkt=(nif & weak.reindex(nif.index).fillna(False)), cap=3, cooldown=5)})
    rows = []
    for name, kw in cfg.items():
        P = portfolio(T, **kw)
        row = dict(config=name, calls_per_day=round(len(P) / ndays, 2), max_calls_one_day=int(P.groupby("day").size().max()), **stats(P.sort_values("t_in").r))
        for sp in ("p1", "p2", "p3"):
            s = stats(P[P.split == sp].sort_values("t_in").r); row[f"{sp}_n"] = s["n"]; row[f"{sp}_win"] = s.get("win"); row[f"{sp}_R"] = s.get("expR")
        s = P[P.day >= "2026-01-01"]; row["y2026_n"] = len(s); row["y2026_R"] = round(s.r.mean(), 3) if len(s) else None
        rows.append(row)
    S = pd.DataFrame(rows); S.to_csv(OUT / "stk_call_audit_summary.csv", index=False)
    pd.set_option("display.width", 260)
    print(S.to_string(index=False))
    print("\nper rule (standalone):")
    print(pd.DataFrame([dict(rule=k, **stats(g.sort_values("t_in").r)) for k, g in T.groupby("rule")]).to_string(index=False))
    # clustering: results on days with many signals
    P0 = portfolio(T, per_tf=True); n = P0.groupby("day").size(); P0["day_n"] = P0.day.map(n)
    P0["bucket"] = pd.cut(P0.day_n, [0, 2, 5, 10, 1000], labels=["1-2", "3-5", "6-10", ">10"])
    print("\nlive-style calls by how many calls fired that day:")
    print(P0.groupby("bucket", observed=True).r.agg(calls="size", win=lambda x: round(100 * (x > 0).mean(), 1), expR=lambda x: round(x.mean(), 3)).to_string())
    P0["weak"] = P0.day.map(weak).fillna(False)
    print("\nlive-style calls by market breadth (prev. session >= 55 % of stocks below EMA50):")
    print(P0.groupby("weak").r.agg(calls="size", win=lambda x: round(100 * (x > 0).mean(), 1), expR=lambda x: round(x.mean(), 3)).to_string())


if __name__ == "__main__":
    main()

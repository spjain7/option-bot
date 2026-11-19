"""SELL-CALLS-001 (19-Nov-2026, owner: "give me an artifact to see how calls perform – high / low after the call, best profit
and loss"). Trade-by-trade lists (research data 2022-26, 181 F&O stock futures, 2x costs, next-open entry, stop first, never
through a roll) for:
  CONF6_1R   6+ of the 19 TradingView / Chartink SELL scripts agree within 3 four-hour candles, stock in a daily downtrend,
             SL 2 ATR, target 1R                                         (tv_confluence.py: 58 % won, +0.09R)
  CONF6_2R   same signal, target 2R                                     (51 % won, +0.11R)
  LIVE6      the 6 live stock SELL rules with their live stops / targets (stk_call_audit.LIVE)
All three pass the LIVE gate (one open call per stock, max 5 new calls a day, 5-session cooldown after a stop-loss).
Per call: entry, SL, target, exit, highest high and lowest low between entry and exit, best profit / worst loss and P&L
per LOT (lot = today's NSE lot size, NewBrdLotQty of 18-Nov-2026; old lots differed) after 2x costs.
python research/program/sell_call_lists.py <lots.csv> -> results/sell_call_lists.json"""
import json
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.tv_scripts import signals  # noqa: E402
from research.program.stk_call_audit import LIVE, PRI, portfolio  # noqa: E402

OUT = ROOT / "research/program/results"
LABEL = {"CONF6_1R": "6+ scripts agree · 4-hour · target 1R", "CONF6_2R": "6+ scripts agree · 4-hour · target 2R",
         "LIVE6": "Live stock SELL rules (6)"}
RNAME = {"RB_STK_2h_SQZ_SELL": "2-hour squeeze", "RB_STK_4h_MACD0_SELL": "4-hour MACD", "RB_STK_3h_MACD0_SELL": "3-hour MACD",
         "RB_STK_3h_EMA921_SELL": "3-hour EMA 9/21", "FH_NFO_4h_SELL": "Swing (4-hour)", "FH_NFO3H_SELL": "Swing (3-hour)"}


def trades(setup, rule, tf, f, sig, k, r, cost, name):
    o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    sw = f["switch"].values.astype(np.bool_); t = pd.to_datetime(f["time"])
    out = []
    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, sig, k, r, SV.MAXH.get(tf, 40), cost, 0.0, 0.0, 0.0, H.CHASE):
        e0 = o[i + 1]; R = k * at[i]; g = rr + 2 * cost[i] / R; px = e0 - g * R
        hi = h[i + 1:j + 1].max(); lo = l[i + 1:j + 1].min()
        out.append(dict(setup=setup, rule=rule, tf=tf, name=name, t_sig=t.iat[i], t_in=t.iat[i + 1], t_out=t.iat[j], entry=e0, sl=e0 + R,
                        target=e0 - r * R, exit=px, high=hi, low=lo, r=rr, cost_pts=2 * cost[i],
                        result={1: "stop-loss", 2: "target", 3: "time exit", 4: "roll (expiry)", 5: "open"}.get(int(why), "?")))
    return out


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
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        cost = np.asarray(cost, float)
        if len(cost) != len(f):
            cost = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost)
        sets = {(a, b, cc): (x, y) for a, b, cc, x, y in SV.signal_sets(f, dtr, tf)}
        sets.update({(a, b, cc): (x, y) for a, b, cc, x, y in SA.signal_sets(f, dtr)})
        for rid, _, fam, par, flt, k, r, _ in [x for x in LIVE if x[1] == tf]:
            if (fam, par, flt) in sets:
                sig = np.nan_to_num(np.asarray(sets[(fam, par, flt)][1], float)) > 0
                rows += trades("LIVE6", RNAME[rid], tf, f, sig, k, r, cost, job[1])
        if tf == "4h":
            down = (pd.to_datetime(f["time"]).dt.normalize().map(dtr) < 0).values
            S = signals(C, True); S.pop("RANDOM", None)
            M = np.column_stack([s.values for s in S.values()]).astype(int)
            recent = pd.DataFrame(M).rolling(3, min_periods=1).max().values.sum(axis=1)
            hit = recent >= 6; sig = hit & ~np.r_[False, hit[:-1]] & down
            names = list(S)
            for setup, tgt in (("CONF6_1R", 1.0), ("CONF6_2R", 2.0)):
                for x in trades(setup, "", tf, f, sig, 2.0, tgt, cost, job[1]):
                    i = int(np.flatnonzero(pd.to_datetime(f["time"]).values == np.datetime64(x["t_sig"]))[0])
                    fired = [n.replace("TV ", "").replace("Chartink ", "CK ") for q, n in enumerate(names) if M[max(0, i - 2):i + 1, q].any()]
                    x["rule"] = f"{len(fired)} agree: " + ", ".join(fired)
                    rows.append(x)
    return rows


def main():
    lots = pd.read_csv(sys.argv[1], index_col=0).iloc[:, 0].to_dict()
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        T = pd.DataFrame([r for x in p.imap_unordered(one, J, chunksize=2) if x for r in x])
    T["day"] = pd.to_datetime(T.t_sig).dt.normalize(); T["exit_kind"] = np.where(T.result == "stop-loss", "stop", "other")
    keep = []
    for s, G in T.groupby("setup"):
        G = G.rename(columns={"t_in": "t_in_", "t_sig": "t_in"}).assign(exit=G.result.map(lambda z: "stop" if z == "stop-loss" else "other"),
                                                                        pri=G.rule.map(lambda z: PRI.get(next((k for k, v in RNAME.items() if v == z), ""), 0.1)))
        P = portfolio(G.assign(t_out=G.t_out), per_tf=False, cap=5, cooldown=5)
        keep.append(T.loc[P.index])
    T = pd.concat(keep).sort_values("t_sig")
    T["lot"] = T.name.map(lots)
    T = T[T.lot.notna()].copy()
    pts = lambda x: x * T.lot
    T["best_profit_lot"] = pts(T.entry - T.low).round(0); T["worst_loss_lot"] = pts(T.entry - T.high).round(0)
    T["pnl_lot"] = pts(T.entry - T.exit - T.cost_pts).round(0); T["risk_lot"] = pts(T.sl - T.entry).round(0)
    T["year"] = pd.to_datetime(T.t_sig).dt.year
    T["period"] = np.where(T.t_sig < SV.P1, "2022-24", np.where(T.t_sig < SV.P2, "2024-25", "2025-26"))
    rows = []
    for n, x in enumerate(T.itertuples(), 1):
        rows.append(dict(id=f"S{n}", setup_id=x.setup, setup=LABEL[x.setup], signal=x.rule, symbol=x.name, tf=x.tf,
                         signal_time=str(x.t_sig)[:16], entry_time=str(x.t_in)[:16], exit_time=str(x.t_out)[:16],
                         entry=round(x.entry, 2), sl=round(x.sl, 2), target=round(x.target, 2), exit=round(x.exit, 2),
                         high_after=round(x.high, 2), low_after=round(x.low, 2), lot=int(x.lot), risk_lot=int(x.risk_lot),
                         best_profit_lot=int(x.best_profit_lot), worst_loss_lot=int(x.worst_loss_lot), pnl_lot=int(x.pnl_lot),
                         R=round(x.r, 2), result=x.result, year=int(x.year), period=x.period))
    meta = [{"label": "Data", "value": "Angel One 1-hour stock-futures candles 2022-10 to 2026-10, 181 F&O stocks, front month (research data, branch exp/stock-call-audit)"},
            {"label": "Rules", "value": "Signal at the candle close, entry next candle's open (skipped if it opens > 0.5 ATR away), stop checked first inside a candle, never held through expiry, 2x costs. One open call per stock, max 5 new calls a day, 5-session pause after a stop-loss on the stock."},
            {"label": "Lot", "value": "P&L per lot uses TODAY's NSE lot size (18-Nov-2026); lots were different in earlier years, so old ₹ figures are indicative. R = P&L / risk."},
            {"label": "Not live", "value": "CONF6 setups are research only (not sent). LIVE6 = the 6 rules that are live today (backtest, not the live record)."}]
    (OUT / "sell_call_lists.json").write_text(json.dumps(dict(rows=rows, meta=meta), allow_nan=False))
    D = pd.DataFrame(rows)
    print(D.groupby("setup_id").agg(n=("id", "size"), win=("R", lambda r: round(100 * (r > 0).mean(), 1)), R=("R", "mean"), pnl=("pnl_lot", "sum"),
                                    best=("best_profit_lot", "max"), worst=("worst_loss_lot", "min")).round(3).to_string())


if __name__ == "__main__":
    main()

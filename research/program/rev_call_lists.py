"""REV-CALLS-001 (19-Nov-2026, owner: "give me the artifact of the result"). Trade-by-trade lists for the best reversal SELL
setups of rev_ind.py (stock in a daily downtrend; research data 2022-26, 181 F&O stock futures, 2x costs, next-open entry,
stop first, never through a roll, one call at a time per stock and setup - the same trades rev_ind.py scored), plus the
per-indicator summary table. P&L per lot uses today's NSE lot size (18-Nov-2026).
python research/program/rev_call_lists.py <lots.csv> -> results/rev_call_lists.json, results/rev_ind_table.json"""
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
from research.program.rev_ind import tops  # noqa: E402

OUT = ROOT / "research/program/results"
# id: (indicator, tf, stop ATR, target R, label[, filter])   filter "A200" = stock above its daily EMA200 (previous day)
SETUPS = {"TD9P_4H_EMA200_1R": ("TD9P", "4h", 2.0, 1.0, "TD Sequential 9 perfected · 4-hour · above daily EMA200 · SL 2 ATR · 1R", "A200"),
          "WPR20_1D_EMA200_1R": ("WPR20", "1d", 2.0, 1.0, "Williams %R below −20 · daily · above daily EMA200 · SL 2 ATR · 1R", "A200"),
          "TD9P_4H_1.5_2R": ("TD9P", "4h", 1.5, 2.0, "TD Sequential 9 perfected · 4-hour · SL 1.5 ATR · 2R"),
          "TD9P_4H_2_1R": ("TD9P", "4h", 2.0, 1.0, "TD Sequential 9 perfected · 4-hour · SL 2 ATR · 1R"),
          "FISHER_4H_2_2R": ("FISHER", "4h", 2.0, 2.0, "Fisher Transform down from +2 · 4-hour · SL 2 ATR · 2R"),
          "STOCH80_4H_2_1.5R": ("STOCH80", "4h", 2.0, 1.5, "Stochastic down from 80 · 4-hour · SL 2 ATR · 1.5R"),
          "WPR20_1D_1.5_2R": ("WPR20", "1d", 1.5, 2.0, "Williams %R below −20 · daily · SL 1.5 ATR · 2R"),
          "CCI200_4H_2_3R": ("CCI200", "4h", 2.0, 3.0, "CCI back below +100 after +200 · 4-hour · SL 2 ATR · 3R")}
# REV-MORE-001 basket: any of these, stock above daily EMA200 and daily trend down, SL 2 ATR, 1R; one open call per stock
BASKET_ID = "BASKET_EMA200_1R"
BASKET = [("TD9P", "4h"), ("TD9", "4h"), ("CCI200", "4h"), ("TD9P", "1d"), ("TD9", "1d"), ("WPR20", "1d"), ("STOCH80", "1d"), ("FISHER", "1d")]
SIGNAME = {"TD9P": "TD9 perfected", "TD9": "TD9", "CCI200": "CCI 200", "WPR20": "Williams %R", "STOCH80": "Stochastic 80", "FISHER": "Fisher"}
RES = {1: "stop-loss", 2: "target", 3: "time exit", 4: "roll (expiry)", 5: "open"}


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1 = seg["STOCKS 1h"]; fd, cd = seg["STOCKS 1d"]
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    dcl = fd["close"].astype(float).reset_index(drop=True)
    a200 = pd.Series((dcl > dcl.ewm(span=200, adjust=False).mean()).values.astype(float),
                     index=pd.to_datetime(fd["time"]).dt.normalize().values).shift(1)
    a200 = a200[~a200.index.duplicated(keep="last")]
    C4, first = anchored(f1, 4)
    frames = {"1d": (fd, cd), "4h": (C4, c1[first[:len(C4)]])}
    rows = []
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_); t = pd.to_datetime(f["time"])
        down = (t.dt.normalize().map(dtr) < 0).values
        ab = (t.dt.normalize().map(a200) > 0).values
        S = tops(C)
        todo = [(sid, v[0], v[2], v[3], v[5] if len(v) > 5 else None) for sid, v in SETUPS.items() if v[1] == tf]
        todo += [(BASKET_ID, ind, 2.0, 1.0, "A200") for ind, btf in BASKET if btf == tf]
        for sid, ind, k, r, flt in todo:
            m = S[ind].values & down & (ab if flt == "A200" else True)
            for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, k, r, 10 if tf == "1d" else SV.MAXH.get(tf, 40), cost, 0.0, 0.0, 0.0, H.CHASE):
                e0 = o[i + 1]; R = k * at[i]; px = e0 - (rr + 2 * cost[i] / R) * R
                rows.append(dict(setup_id=sid, signal=SIGNAME.get(ind, ind), symbol=job[1], tf=tf, t_sig=t.iat[i], t_in=t.iat[i + 1], t_out=t.iat[j], entry=e0, sl=e0 + R,
                                 target=e0 - r * R, exit=px, high=h[i + 1:j + 1].max(), low=l[i + 1:j + 1].min(), r=rr, cost_pts=2 * cost[i],
                                 result=RES.get(int(why), "?")))
    return rows


def main():
    lots = pd.read_csv(sys.argv[1], index_col=0).iloc[:, 0].to_dict()
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        T = pd.DataFrame([r for x in p.imap_unordered(one, J, chunksize=2) if x for r in x])
    T["lot"] = T.symbol.map(lots); T = T[T.lot.notna()].sort_values(["t_sig", "tf"]).copy()
    # basket: one open call per stock (a signal while that stock's call is still open is skipped)
    B = T[T.setup_id == BASKET_ID]; keep, last = [], {}
    for ix, x in B.iterrows():
        if x.symbol in last and pd.Timestamp(x.t_in) <= last[x.symbol]:
            continue
        keep.append(ix); last[x.symbol] = pd.Timestamp(x.t_out)
    T = pd.concat([T[T.setup_id != BASKET_ID], B.loc[keep]]).sort_values("t_sig")
    tm = lambda s: str(s)[:16] if " " in str(s) and not str(s).endswith("00:00:00") else str(s)[:10]
    rows = []
    for n, x in enumerate(T.itertuples(), 1):
        rows.append(dict(id=f"V{n}", setup_id=x.setup_id, signal=f"{x.signal} {x.tf}", symbol=x.symbol, tf=x.tf, signal_time=tm(x.t_sig), entry_time=tm(x.t_in), exit_time=tm(x.t_out),
                         entry=round(x.entry, 2), sl=round(x.sl, 2), target=round(x.target, 2), exit=round(x.exit, 2),
                         high_after=round(x.high, 2), low_after=round(x.low, 2), lot=int(x.lot), risk_lot=int(round((x.sl - x.entry) * x.lot)),
                         best_profit_lot=int(round((x.entry - x.low) * x.lot)), worst_loss_lot=int(round((x.entry - x.high) * x.lot)),
                         pnl_lot=int(round((x.entry - x.exit - x.cost_pts) * x.lot)), R=round(x.r, 2), result=x.result,
                         year=int(pd.Timestamp(x.t_sig).year)))
    meta = [{"label": "Data", "value": "Angel One 1-hour stock-futures candles Oct-2022 to Oct-2026, 181 F&O stocks, front month (research data, branch exp/stock-call-audit)"},
            {"label": "Rules", "value": "SELL only when the stock's daily trend is already down (EMA20 < EMA50, close < EMA50, previous day). Signal at the candle close, entry next candle's open (skipped if > 0.5 ATR away), stop checked first inside a candle, never held through expiry, 2x costs. One call at a time per stock and setup. EMA200 setups and the basket also need the stock above its daily EMA200 (previous day); the basket takes any of its 8 signals with one open call per stock."},
            {"label": "Lot", "value": "P&L per lot uses TODAY's NSE lot size (18-Nov-2026); older lots differed, so old ₹ figures are indicative."},
            {"label": "Code", "value": "research/program/rev_ind.py (signals) and rev_call_lists.py (this file)"}]
    (OUT / "rev_call_lists.json").write_text(json.dumps(dict(rows=rows, meta=meta), allow_nan=False))
    L = pd.read_csv(OUT / "rev_ind_summary.csv")
    L = L[L.ind != "RANDOM"].copy()
    NAMES = {"TD9": "TD Sequential 9", "TD9P": "TD Sequential 9 perfected", "TD13": "TD Sequential 13 countdown", "RSI_DIV": "RSI divergence",
             "MACD_DIV": "MACD histogram divergence", "STOCH80": "Stochastic cross from 80 / 20", "CCI200": "CCI back inside ±100 after ±200",
             "FISHER": "Fisher Transform cross from ±2", "BB_REJECT": "Bollinger band rejection", "WPR20": "Williams %R cross of −20 / −80",
             "VOL_CLIMAX": "Volume climax with wick", "SFP": "Swing failure (fake breakout)", "BAR3": "3-bar reversal"}
    CTX = {"none": "any", "UP": "at an extended top / bottom", "DT": "with the daily trend"}
    best = L.sort_values("minR", ascending=False).groupby(["ind", "side"]).head(1)
    tab = []
    for n, x in enumerate(best.sort_values(["side", "minR"], ascending=[False, False]).to_dict("records"), 1):
        x = pd.Series(x)
        tab.append(dict(id=f"I{n}", indicator=NAMES.get(x.ind, x.ind), side=x.side, timeframe=x.tf, context=CTX[x.ctx], stop_atr=x.k, target_R=x.r,
                        calls=int(x.n), win_pct=x.win, avg_R=x.R, p1_win=x.p1_win, p2_win=x.p2_win, p3_win=x.p3_win, p1_R=x.p1_R, p2_R=x.p2_R, p3_R=x.p3_R,
                        passed="yes" if bool(x["pass"]) else "no", passes_total=int(L[(L.ind == x.ind) & (L.side == x.side)]["pass"].sum()),
                        combos_tested=int(((L.ind == x.ind) & (L.side == x.side)).sum())))
    (OUT / "rev_ind_table.json").write_text(json.dumps(dict(rows=tab, meta=[{"label": "Method", "value": "Best of 1d/4h/2h/1h x 3 contexts x 5 exits per indicator and side, ranked by its worst period. Passed = R > 0 and above random entries in 2022-24, 2024-25 and 2025-26 with >= 40 trades each."}]), allow_nan=False, default=float))
    D = pd.DataFrame(rows)
    print(D.groupby("setup_id").agg(n=("id", "size"), win=("R", lambda r: round(100 * (r > 0).mean(), 1)), R=("R", "mean"), best=("best_profit_lot", "mean"), worst=("worst_loss_lot", "mean")).round(3))
    print(pd.DataFrame(tab)[["indicator", "side", "timeframe", "context", "calls", "win_pct", "avg_R", "passed", "passes_total"]].to_string(index=False))


if __name__ == "__main__":
    main()

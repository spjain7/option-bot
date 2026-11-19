"""REV-BUY-CALLS-001 (19-Nov-2026, owner: "where is the buy setup calls"). Trade-by-trade lists for the best BUY setups of
rev_bottom.py / rev_buy.py (research only – none passed well enough to go live), same fields as rev_call_lists.json:
  BOT_IBS20_1D_PREVHI  IBS < 0.2 after 3 lower closes, above EMA200 · daily · stock in a daily uptrend AND > 50 % of F&O
                       stocks in a daily uptrend · SL 2 ATR · exit at the first close above the previous candle's high
  BOT_RSI2_5_1D_SMA5   RSI(2) < 5, above EMA200 · daily · > 50 % of stocks in an uptrend · SL 2 ATR · exit close > SMA(5)
  BOT_GAPREV_1D_1R     gap down >= 1 ATR, closes above its open · daily · stock in a daily uptrend · SL 2 ATR · 1R
  REVB_CCI200_4H_1R    CCI back above -100 after -200 · 4-hour · daily uptrend, above daily EMA200 · SL 2 ATR · 1R
Simulator rev_bottom.sim (next open, 0.5-ATR chase limit, stop first, 2x costs, never through a roll, max 10 candles).
python research/program/rev_buy_calls.py <lots.csv> -> results/rev_buy_calls.json"""
import json
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.rev_bottom import signals, sim  # noqa: E402

OUT = ROOT / "research/program/results"
RES = {1: "stop-loss", 2: "target / exit signal", 3: "time exit", 4: "roll (expiry)"}


def cci_bottom(C):
    h, l, c = (C[x].astype(float) for x in ("high", "low", "close"))
    tp = (h + l + c) / 3
    cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True))
    return ((cci > -100) & (cci.shift(1) <= -100) & (cci.rolling(5).min() < -200)).fillna(False).values


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
        cost = np.asarray(cost, float)
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        f = H.features(C)
        sw = (C["switch"].values if "switch" in C else np.zeros(len(C), bool)).astype(bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        tt = pd.to_datetime(f["time"]); day = tt.dt.normalize()
        ut = (day.map(dtr) > 0).values; ab = (day.map(a200) > 0).values
        if tf == "1d":
            S = signals(f)
            todo = [("BOT_IBS20_1D_PREVHI", S["IBS20"] & ut, "PREVHI", True), ("BOT_RSI2_5_1D_SMA5", S["RSI2_5"], "SMA5", True),
                    ("BOT_GAPREV_1D_1R", S["GAPREV"] & ut, "SL2_1R", False)]
        else:
            todo = [("REVB_CCI200_4H_1R", cci_bottom(C) & ut & ab, "SL2_1R", False)]
        for sid, sig, mode, need_b in todo:
            for i, j, rr, why in sim(f, np.asarray(sig, bool), mode, cost, sw):
                e = o[i + 1]; R = 2.0 * at[i]
                px = e + (rr + 2 * cost[i] / R) * R
                rows.append(dict(setup_id=sid, need_b=need_b, symbol=job[1], tf=tf, t_sig=tt.iat[i], t_in=tt.iat[i + 1], t_out=tt.iat[j],
                                 entry=e, sl=e - R, target=(e + R) if mode == "SL2_1R" else None, exit=px,
                                 high=h[i + 1:j + 1].max(), low=l[i + 1:j + 1].min(), r=rr, cost_pts=2 * cost[i], result=RES.get(int(why), "?")))
    return rows, dtr.rename(job[1])


def main():
    lots = pd.read_csv(sys.argv[1], index_col=0).iloc[:, 0].to_dict()
    J = [j for j in EX.jobs() if j[0] == "stk"]
    rows, trends = [], []
    with Pool(2) as p:
        for x in p.imap_unordered(one, J, chunksize=2):
            if x:
                rows += x[0]; trends.append(x[1])
    T = pd.DataFrame(rows)
    B = pd.concat(trends, axis=1); breadth = (B > 0).sum(axis=1) / B.notna().sum(axis=1)
    T["breadth_up"] = pd.to_datetime(T.t_sig).dt.normalize().map(breadth)
    T = T[~T.need_b | (T.breadth_up > 0.5)].copy()
    T["lot"] = T.symbol.map(lots); T = T[T.lot.notna()].sort_values("t_sig")
    tm = lambda s: str(s)[:16] if not str(s).endswith("00:00:00") else str(s)[:10]
    SIG = {"BOT_IBS20_1D_PREVHI": "IBS bottom", "BOT_RSI2_5_1D_SMA5": "RSI(2) below 5", "BOT_GAPREV_1D_1R": "Gap-down reversal",
           "REVB_CCI200_4H_1R": "CCI from −200"}
    out = []
    for n, x in enumerate(T.to_dict("records"), 1):
        x = pd.Series(x)
        out.append(dict(id=f"U{n}", setup_id=x.setup_id, side="BUY", signal=f"{SIG[x.setup_id]} {x.tf}", symbol=x.symbol, tf=x.tf,
                        signal_time=tm(x.t_sig), entry_time=tm(x.t_in), exit_time=tm(x.t_out), entry=round(x.entry, 2), sl=round(x.sl, 2),
                        target=None if x.target is None or x.target != x.target else round(x.target, 2), exit=round(x.exit, 2),
                        high_after=round(x.high, 2), low_after=round(x.low, 2), lot=int(x.lot), risk_lot=int(round((x.entry - x.sl) * x.lot)),
                        best_profit_lot=int(round((x.high - x.entry) * x.lot)), worst_loss_lot=int(round((x.low - x.entry) * x.lot)),
                        pnl_lot=int(round((x.exit - x.entry - x.cost_pts) * x.lot)), R=round(x.r, 2), result=x.result, year=int(pd.Timestamp(x.t_sig).year)))
    (OUT / "rev_buy_calls.json").write_text(json.dumps(dict(rows=out), allow_nan=False))
    D = pd.DataFrame(out)
    print(D.groupby("setup_id").agg(n=("id", "size"), win=("R", lambda r: round(100 * (r > 0).mean(), 1)), R=("R", "mean"),
                                    sl=("result", lambda s: round(100 * (s == "stop-loss").mean(), 1))).round(3))


if __name__ == "__main__":
    main()

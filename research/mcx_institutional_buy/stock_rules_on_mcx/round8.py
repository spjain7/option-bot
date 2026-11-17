"""ROUND 8 (owner 17-Nov-2026): SCORECARD -- every setup (live stock / index futures rules + everything tried on MCX) on every
commodity, every candle size, BUY and SELL, with ONE standard exit so results are comparable:
  entry  next candle open after the signal (stop-order setups: at the level)    stop 2 ATR    target 3R    max 40 candles
  (weekly: 26)    costs real MCX (weekly x2)
Per combination: trades, win %, average R, total Rs per lot, average best gain after the call (max favourable move, Rs) and
average worst move after the call (max adverse, Rs), biggest win / loss, periods (TRAIN / VALID / OOS) and random entries
with the same side, stop and exit for comparison.
Setups
  stock / index rulebook  BO10 BO20 BO55 EMAX 9/21 13/48 20/50, MACD zero / signal, RSI 70, Bollinger squeeze,
                          momentum candle, Supertrend, breakout retest  (alerts/rulebook.raw, unchanged)
  stock 4h / 3h swing     5-candle breakdown / breakout with volume >= 2x (alerts/four_hour rules, both sides)
  stock daily OI          20-day breakout + volume 1.5x + open interest up 2 % + EMA200 (alerts/stocks.py)
  MCX research            strong-candle breakout, previous week / month high, trendline breakout (whole candle / close),
                          divergence 2+, Hull cross, DMO zero cross, engulfing, hammer, liquidity sweep,
                          1h: first-hour / 17:00-hour range, previous-day high (stop orders);  daily: NR7, inside-NR7
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round8 -> reports/mcx_scorecard.csv, mcx_scorecard_trades.json"""
import json
import warnings
import numpy as np
import pandas as pd
from alerts import rulebook as RB, four_hour as FH
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4, round5 as R5, round7 as R7, patterns as PT
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames, dtrend, daily_oi_rule

warnings.filterwarnings("ignore")
TFS = ["1h", "2h", "3h", "4h", "1d", "1w"]
K_, R_ = 2.0, 3.0
MAXH = {"1h": 40, "2h": 40, "3h": 40, "4h": 40, "1d": 40, "1w": 26}
CMUL = {"1h": 1, "2h": 1, "3h": 1, "4h": 1, "1d": 1, "1w": 2}
TFN = {"1h": "1 hour", "2h": "2 hour", "3h": "3 hour", "4h": "4 hour", "1d": "Daily", "1w": "Weekly"}
RBF = [("BO", "N10 vol0", "10-candle breakout"), ("BO", "N20 vol0", "20-candle breakout"), ("BO", "N55 vol0", "55-candle breakout"),
       ("EMAX", "9/21", "EMA 9/21 cross"), ("EMAX", "13/48", "EMA 13/48 cross"), ("EMAX", "20/50", "EMA 20/50 cross"),
       ("MACD", "zero", "MACD zero cross"), ("MACD", "signal", "MACD signal cross"), ("RSICONT", "70/30", "RSI 70 momentum"),
       ("SQZ", "BB20", "Bollinger squeeze"), ("MOMO", "1.5ATR", "Momentum candle"), ("ST", "10/3", "Supertrend flip"),
       ("RETEST", "20/5", "Breakout retest")]
SRC = {**{lab: "Stock / index rule" for _, _, lab in RBF}, "Stock swing 5-candle + volume 2x": "Stock / index rule",
       "Stock daily OI breakout": "Stock / index rule"}
NAN = {}


def sim(f, arr, side, sig, name, tf, lvl=None, win=3):
    o, h, l, c, a = arr["o"], arr["h"], arr["l"], arr["c"], arr["a"]; n = len(c)
    NAN.setdefault(n, np.full(n, np.nan))
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * side * CMUL[tf]
    if lvl is None:
        stop = c - K_ * a; el = NAN[n]
    else:
        stop = lvl - K_ * a; el = lvl
    return S.simulate(o, h, l, c, a, f["seg"].values.astype(np.int64), costf, np.nan_to_num(sig).astype(bool), stop, el, NAN[n],
                      0, R_, MAXH[tf], MAXH[tf], 3.0, int(win), 0.25, 6.0, 1.0)[:8], stop, el


def supertrend(f, n=10, m=3.0):
    """Supertrend 10/3. alerts.rulebook._supertrend never flips (the first ATR values are NaN and the NaN carries through the
    bands), so the research uses this NaN-safe copy; no live rule uses the Supertrend family."""
    h, l, c = (f[x].values.astype(float) for x in ("high", "low", "close"))
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[np.nan, c[:-1]]), np.abs(l - np.r_[np.nan, c[:-1]])))
    a = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().values
    hl2 = (h + l) / 2; ub, lb = hl2 + m * a, hl2 - m * a
    fu, fl = ub.copy(), lb.copy(); d = np.ones(len(c))
    for i in range(1, len(c)):
        if not np.isfinite(fu[i - 1]):
            continue
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        d[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else d[i - 1])
    dp = np.r_[d[0], d[:-1]]
    return (d > 0) & (dp < 0), (d < 0) & (dp > 0)


def setups(name, d, dd, tf, side):
    f = d["f"]
    P0, cond, arr = R4.signals(d, side)
    out = {}
    g = RB.features(f[["time", "open", "high", "low", "close", "volume"]].copy())
    for fam, par, lab in RBF:
        try:
            b, s_ = RB.raw(g, fam, par)
            if fam == "ST":
                b, s_ = supertrend(f)
            out[lab] = (np.asarray(b if side > 0 else s_, float), None, 3)
        except Exception:
            pass
    # stock 4h / 3h swing (four_hour.py): N-candle breakout / breakdown with volume >= 2x
    c, v = f["close"], f["volume"].astype(float)
    hh, ll = f["high"].shift(1).rolling(5).max(), f["low"].shift(1).rolling(5).min()
    vx = v / v.rolling(20).mean().shift(1)
    out["Stock swing 5-candle + volume 2x"] = (((c > hh) if side > 0 else (c < ll)) & (vx >= 2.0), None, 3)
    if tf == "1d":
        gg = g.assign(volx=g["volx"])
        out["Stock daily OI breakout"] = (daily_oi_rule(name, gg, side), None, 3)
    P5, cond5, _ = R5.parts(d, side)
    for k_, lab in (("MARU20", "Strong-candle breakout"), ("PWK", "Previous-week high break"), ("PMO", "Previous-month high break"),
                    ("TLB", "Trendline breakout (candle)"), ("TLC", "Trendline breakout (close)"), ("DIV2", "Divergence 2+ indicators"),
                    ("HULL", "Hull trend cross"), ("DMOX", "DMO zero cross")):
        if k_ in P5:
            out[lab] = (P5[k_], None, 3)
    pp = PT.parts(arr["o"], arr["h"], arr["l"], arr["c"], arr["a"], f["volx"].values if "volx" in f else g["volx"].values,
                  arr["c"] * 0 - np.inf, np.ones(len(arr["c"]), bool), np.zeros(len(arr["c"]), bool))
    for k_, lab in (("ENGULF", "Engulfing candle"), ("PIN", "Hammer / pin bar"), ("SWEEP", "Liquidity sweep")):
        out[lab] = (pp[k_], None, 3)
    if tf == "1h":
        for fam, sig, lvl, st, win in R7.setups_1h(f, dd, side):
            lab = {"ORB1": "First-hour range break", "ORBE": "17:00-hour range break", "PDH": "Previous-day high break"}.get(fam)
            if lab:
                out[lab] = (sig, lvl, win)
    if tf == "1d":
        for fam, sig, lvl, st, win in R7.setups_1d(f, side):
            lab = {"NR7": "NR7 day break", "IDNR7": "Inside + NR7 day break"}.get(fam)
            if lab:
                out[lab] = (sig, lvl, win)
    return out, arr


def main():
    rows = []; keep = {}; rng = np.random.default_rng(37)
    for name in D.INTRA:
        B = R4.build(name, TFS); F, dd = frames(name)
        for tf in TFS:
            d = B[tf]; f = d["f"]
            for side in (1, -1):
                S_, arr = setups(name, d, dd, tf, side)
                # random baseline: 50 draws, every bar 3 % chance
                rr = []
                for _ in range(50):
                    x = sim(f, arr, side, rng.random(len(arr["c"])) < 0.03, name, tf)[0]
                    if len(x[4]):
                        rr.append(x[4].mean())
                rand = round(float(np.mean(rr)), 3) if rr else np.nan
                fac = f["raw_close"].values / f["close"].values
                t = pd.to_datetime(f["time"])
                for lab, (sig, lvl, win) in S_.items():
                    sig = np.nan_to_num(np.asarray(sig, float)).astype(bool)
                    if sig.sum() < 5:
                        continue
                    (si, ei, xi, g, nr, mfe, mae, why), stop, el = sim(f, arr, side, sig, name, tf, lvl, win)
                    if len(nr) < 5:
                        continue
                    px = arr["o"][ei] if lvl is None else np.maximum(arr["o"][ei], el[si])
                    risk = px - stop[si]; M = R4.MULT[name] * fac[ei]
                    rs = nr * risk * M; best = mfe * risk * M; worst = mae * risk * M
                    pe = d["per"][ei]
                    row = dict(commodity=name, timeframe=TFN[tf], side="BUY" if side > 0 else "SELL", setup=lab,
                               source=SRC.get(lab, "MCX research"), trades=int(len(nr)), win_pct=round(100 * float((nr > 0).mean()), 1),
                               avg_R=round(float(nr.mean()), 3), total_rs=int(rs.sum()), avg_rs=int(rs.mean()),
                               avg_best_after_call_rs=int(best.mean()), avg_worst_after_call_rs=int(worst.mean()),
                               biggest_win_rs=int(rs.max()), biggest_loss_rs=int(rs.min()),
                               profit_factor=round(float(rs[rs > 0].sum() / -rs[rs <= 0].sum()), 2) if (rs <= 0).any() and (rs > 0).any() else None,
                               random_avg_R=rand, first_trade=str(t.iloc[ei[0]])[:10], last_trade=str(t.iloc[ei[-1]])[:10])
                    for p in ("TRAIN", "VAL", "OOS"):
                        x = nr[pe == p]
                        row[f"{p.lower()}_trades"] = int(len(x)); row[f"{p.lower()}_avg_R"] = round(float(x.mean()), 3) if len(x) else None
                    row["all_periods_positive"] = "yes" if all((row[f"{p}_avg_R"] or -1) > 0 for p in ("train", "val", "oos")) else "no"
                    row["beats_random"] = "yes" if row["avg_R"] > (rand if rand == rand else 9) else "no"
                    row["id"] = f"{name}|{tf}|{row['side']}|{lab}"
                    rows.append(row)
                    keep[row["id"]] = [dict(id=f"{row['id']}|{i}", key=row["id"], commodity=name, timeframe=TFN[tf], side=row["side"], setup=lab,
                                            entry=str(t.iloc[ei[i]])[:16], exit=str(t.iloc[xi[i]])[:16],
                                            entry_px=round(float(side * px[i] * fac[ei[i]]), 2),
                                            exit_px=round(float(side * (px[i] + g[i] * risk[i]) * fac[ei[i]]), 2),
                                            R=round(float(nr[i]), 2), pnl_rs=int(round(rs[i])), best_after_call_rs=int(round(best[i])),
                                            worst_after_call_rs=int(round(worst[i])), period={"VAL": "VALID"}.get(str(pe[i]), str(pe[i])),
                                            result={1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll"}.get(int(why[i]), "exit"))
                                       for i in range(len(nr))]
            print(name, tf, len(rows), flush=True)
    L = pd.DataFrame(rows)
    L.to_csv(RN.REPORTS / "mcx_scorecard.csv", index=False)
    # trades: the 6 best (all periods positive, beats random, by total Rs) per commodity and side
    top = L[(L.all_periods_positive == "yes") & (L.beats_random == "yes") & (L.trades >= 20)]
    top = top.sort_values("total_rs", ascending=False).groupby(["commodity", "side"]).head(6)
    L["has_trades"] = L.id.isin(top.id).map({True: "yes", False: "no"})
    L.to_csv(RN.REPORTS / "mcx_scorecard.csv", index=False)
    T = [x for i in top.id for x in keep[i]]
    (RN.REPORTS / "mcx_scorecard_trades.json").write_text(json.dumps(T))
    print("rows", len(L), "trade rows", len(T))
    pd.set_option("display.width", 250)
    for n, g in L.groupby("commodity"):
        print("\n", n); print(g.sort_values("total_rs", ascending=False).head(8)[["timeframe", "side", "setup", "trades", "win_pct", "avg_R",
              "total_rs", "avg_best_after_call_rs", "avg_worst_after_call_rs", "train_avg_R", "val_avg_R", "oos_avg_R", "random_avg_R"]].to_string(index=False))


if __name__ == "__main__":
    main()

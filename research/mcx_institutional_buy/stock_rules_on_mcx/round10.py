"""ROUND 10 (owner 17-Nov-2026): stop-loss and target from SUPPORT / RESISTANCE, LIQUIDITY and SUPPLY / DEMAND zones instead of ATR.
Applied to each script's 3 best consistent setups from the round-8 scorecard (same entries), BUY and SELL (mirror image).
Levels known at the signal candle's close (pivots 5/5 confirmed 5 candles later; zones from completed candles only):
  support      the nearest confirmed swing low below the close        resistance  the nearest confirmed swing high above it
  demand zone  base (2 candles) before the last strong up-candle (range >= 1.2 ATR, body >= 60 %) below the close: its low
  supply zone  base before the last strong down-candle above the close: its low edge (where sellers start)
  liquidity    just beyond the swing high (+0.25 ATR), where buy-stops sit
Stops (buffer 0.25 ATR): ATR (2 ATR, baseline) / SWING (below support) / DEMAND (below the demand zone)
Targets: 3R (baseline) / RES (0.1 ATR before resistance) / LIQ (resistance + 0.25 ATR) / SUPPLY (supply zone low edge)
         when there is no level above (new highs), the target falls back to 3R; a trade needs reward >= 1.5 x risk at entry.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round10 -> reports/mcx_round10.csv"""
import warnings
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.feature_engineering import ind as I
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4, round8 as R8
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames

warnings.filterwarnings("ignore")
TFI = {v: k for k, v in R8.TFN.items()}
NAN = {}


def levels(o, h, l, c, a, depth=12):
    n = len(c)
    pl, ph = I.pivots(l, h, 5, 5)
    lo, _ = I.known_levels(pl, l, 5, depth); hi, _ = I.known_levels(ph, h, 5, depth)
    cc = c[:, None]
    sup = np.where(lo < cc, lo, -np.inf).max(1); sup[~np.isfinite(sup)] = np.nan
    res = np.where(hi > cc, hi, np.inf).min(1); res[~np.isfinite(res)] = np.nan
    rng_ = h - l; body = np.abs(c - o)
    up_imp = (c > o) & (rng_ >= 1.2 * a) & (body >= 0.6 * rng_)
    dn_imp = (c < o) & (rng_ >= 1.2 * a) & (body >= 0.6 * rng_)
    dem = np.full(n, np.nan); sup_z = np.full(n, np.nan)
    last_dem = []; last_sup = []          # (zone low, zone high)
    for t in range(n):
        if t >= 2 and up_imp[t]:
            last_dem.append((min(l[t - 2], l[t - 1]), max(h[t - 2], h[t - 1]))); last_dem = last_dem[-10:]
        if t >= 2 and dn_imp[t]:
            last_sup.append((min(l[t - 2], l[t - 1]), max(h[t - 2], h[t - 1]))); last_sup = last_sup[-10:]
        cand = [z[0] for z in last_dem if z[0] < c[t]]
        dem[t] = max(cand) if cand else np.nan
        cand = [z[0] for z in last_sup if z[0] > c[t]]
        sup_z[t] = min(cand) if cand else np.nan
    return sup, res, dem, sup_z


def run(f, arr, side, sig, name, stop, tgt, kind):
    o, h, l, c, a = arr["o"], arr["h"], arr["l"], arr["c"], arr["a"]; n = len(c); NAN.setdefault(n, np.full(n, np.nan))
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * side
    return S.simulate(o, h, l, c, a, f["seg"].values.astype(np.int64), costf, np.asarray(sig, bool), stop, NAN[n], tgt, kind, 3.0,
                      40, 40, 3.0, 3, 0.25, 6.0, 1.5)[:8]


def main():
    SCR = pd.read_csv(RN.REPORTS / "mcx_scorecard.csv")
    TOP = SCR[(SCR.all_periods_positive == "yes") & (SCR.beats_random == "yes") & (SCR.trades >= 30) & (SCR.timeframe != "Weekly")]
    TOP = TOP[~TOP.setup.isin(["First-hour range break", "17:00-hour range break", "Previous-day high break", "NR7 day break", "Inside + NR7 day break"])]
    TOP = TOP.sort_values("total_rs", ascending=False).groupby("commodity").head(3)
    rows = []
    for name, G in TOP.groupby("commodity"):
        B = R4.build(name, sorted(set(TFI[x] for x in G.timeframe))); F, dd = frames(name)
        for _, s in G.iterrows():
            tf = TFI[s.timeframe]; side = 1 if s.side == "BUY" else -1; d = B[tf]; f = d["f"]; per = d["per"]
            SU, arr = R8.setups(name, d, dd, tf, side)
            sig = np.nan_to_num(np.asarray(SU[s.setup][0], float)).astype(bool)
            o, h, l, c, a = arr["o"], arr["h"], arr["l"], arr["c"], arr["a"]
            sup, res, dem, supz = levels(o, h, l, c, a)
            STOPS = {"ATR 2": c - 2 * a, "Swing low (support)": sup - 0.25 * a, "Demand zone": dem - 0.25 * a}
            fb = lambda lvl, stop: np.where(np.isfinite(lvl), lvl, c + 3 * (c - stop))
            for sl_name, stop in STOPS.items():
                TG = {"3R": (None, 0), "Resistance": (fb(res - 0.1 * a, stop), 1), "Liquidity above resistance": (fb(res + 0.25 * a, stop), 1),
                      "Supply zone": (fb(supz, stop), 1)}
                for tg_name, (tgt, kind) in TG.items():
                    t_ = np.full(len(c), np.nan) if tgt is None else tgt
                    si, ei, xi, g, nr, mfe, mae, why = run(f, arr, side, sig & np.isfinite(stop), name, np.nan_to_num(stop, nan=-1e18) if False else stop, t_, kind)
                    if len(nr) < 10:
                        continue
                    fac = f["raw_close"].values / f["close"].values; risk = o[ei] - stop[si]; rs = nr * risk * R4.MULT[name] * fac[ei]
                    pe = per[ei]; row = dict(commodity=name, timeframe=s.timeframe, side=s.side, setup=s.setup, stop=sl_name, target=tg_name,
                                            trades=len(nr), win_pct=round(100 * float((nr > 0).mean()), 1), avg_R=round(float(nr.mean()), 3),
                                            total_rs=int(rs.sum()), avg_risk_rs=int((risk * R4.MULT[name] * fac[ei]).mean()),
                                            biggest_loss_rs=int(rs.min()), reach_1R_pct=round(100 * float((mfe >= 1).mean()), 1))
                    for p in ("TRAIN", "VAL", "OOS"):
                        x = nr[pe == p]; y = rs[pe == p]
                        row[f"{p}_n"] = len(x); row[f"{p}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                        row[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else None; row[f"{p}_rs"] = int(y.sum())
                    rows.append(row)
            print(name, s.timeframe, s.side, s.setup, flush=True)
    L = pd.DataFrame(rows); L.to_csv(RN.REPORTS / "mcx_round10.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
    # per setup: baseline vs the best exit chosen on TRAIN + VALID Rs (no OOS look)
    out = []
    for k, g in L.groupby(["commodity", "timeframe", "side", "setup"]):
        base = g[(g.stop == "ATR 2") & (g.target == "3R")]
        g = g.assign(tv=g.TRAIN_rs + g.VAL_rs)
        best = g.sort_values("tv", ascending=False).iloc[0]
        b = base.iloc[0] if len(base) else None
        out.append(dict(commodity=k[0], tf=k[1], side=k[2], setup=k[3], best_stop=best.stop, best_target=best.target,
                        base_win=b.win_pct if b is not None else None, best_win=best.win_pct,
                        base_OOS_rs=int(b.OOS_rs) if b is not None else None, best_OOS_rs=int(best.OOS_rs),
                        base_OOS_R=b.OOS_R if b is not None else None, best_OOS_R=best.OOS_R,
                        base_total_rs=int(b.total_rs) if b is not None else None, best_total_rs=int(best.total_rs),
                        base_risk_rs=int(b.avg_risk_rs) if b is not None else None, best_risk_rs=int(best.avg_risk_rs)))
    O = pd.DataFrame(out); O.to_csv(RN.REPORTS / "mcx_round10_best.csv", index=False)
    print(O.to_string(index=False))
    # which stop / target works across all setups (sum of OOS Rs relative to baseline, count of setups improved)
    L["key"] = L.commodity + L.timeframe + L.side + L.setup
    base = L[(L.stop == "ATR 2") & (L.target == "3R")].set_index("key")
    L["dOOS"] = L.OOS_rs - L.key.map(base.OOS_rs); L["dTV"] = (L.TRAIN_rs + L.VAL_rs) - L.key.map(base.TRAIN_rs + base.VAL_rs)
    print(L.groupby(["stop", "target"]).agg(setups=("key", "nunique"), better_TV=("dTV", lambda x: int((x > 0).sum())), better_OOS=("dOOS", lambda x: int((x > 0).sum())),
                                            mean_win=("win_pct", "mean"), mean_OOS_R=("OOS_R", "mean"), sum_dOOS_rs=("dOOS", "sum")).round(2).to_string())


if __name__ == "__main__":
    main()

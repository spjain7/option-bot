"""ROUND 6 (owner 17-Nov-2026): "at least 70 % accuracy for every script, as per its nature".
A 70 %+ win rate needs a different trade shape from breakouts: buy a PULLBACK inside a trend and take a small target or a
quick time exit (mean reversion). Per commodity, no pooling.
  setups   RSI2_10 / RSI2_5 (RSI(2) below 10 / 5), BBL (close below the lower Bollinger band 20,2), EMA20PB (dips to EMA20 and
           closes back above it, green candle), DOWN3 (3 lower closes in a row), MARU20 (strong-candle 20-candle breakout),
           BO10 (10-candle breakout)      SELL = the mirror image (rallies in a down-trend)
  filters  none / TREND (EMA200 side) / HT1 (higher-timeframe trend) / TREND+HT1
  exits    stop 1.5 / 2 / 3 ATR x target 0.5 / 0.75 / 1 R;  or stop 2 / 3 ATR + exit at the close after 3 / 5 / 10 candles
  candles  3h, 4h, daily
  pick     per commodity, on TRAIN + VALID only: win >= 70 % in BOTH, average R > 0 in both, enough trades, neighbour exits
           agree, and better than random entries (same filter, stop, exit, rate; 200 draws) in both. OOS then shown unchanged.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round6 -> reports/mcx_round6.csv, mcx_round6_pick.json"""
import json
import warnings
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4, round5 as R5

warnings.filterwarnings("ignore")
TFS = ["3h", "4h", "1d"]
FAMS = ["RSI2_10", "RSI2_5", "BBL", "EMA20PB", "DOWN3", "MARU20", "BO10"]
FILTS = [(), ("TREND",), ("HT1",), ("TREND", "HT1")]
EXITS = [(k, r, 0, 0) for k in (1.5, 2.0, 3.0) for r in (0.5, 0.75, 1.0)] + [(k, 0.0, 3, n) for k in (2.0, 3.0) for n in (3, 5, 10)]
MIN = {"3h": (30, 15), "4h": (30, 15), "1d": (30, 15)}
NAN = {}


def ex_label(k, r, kind, n):
    return f"SL {k:g} ATR · " + (f"target {r:g}R" if kind == 0 else f"exit after {n} candles")


def run(arr, d, sig, side, k, r, kind, n, tf, name):
    f = d["f"]; L = len(arr["c"]); NAN.setdefault(L, np.full(L, np.nan))
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * side
    out = S.simulate(arr["o"], arr["h"], arr["l"], arr["c"], arr["a"], f["seg"].values.astype(np.int64), costf, np.asarray(sig, bool),
                     arr["c"] - k * arr["a"], NAN[L], NAN[L], kind, float(r), 40, int(n if kind == 3 else 40), 3.0, 3, 0.25, 6.0, 1.5)
    return out[:8]


def setups(d, side):
    P0, cond, arr = R4.signals(d, side)
    o, h, l, c = arr["o"], arr["h"], arr["l"], arr["c"]
    r2 = R5.rsi(c, 2)
    m20 = pd.Series(c).rolling(20).mean().values; sd = pd.Series(c).rolling(20).std().values
    e20 = R5.ema(c, 20); e200 = R5.ema(c, 200)
    pc = np.r_[np.nan, c[:-1]]; ppc = np.r_[np.nan, np.nan, c[:-2]]; pppc = np.r_[np.nan, np.nan, np.nan, c[:-3]]
    P = dict(RSI2_10=r2 < 10, RSI2_5=r2 < 5, BBL=c < m20 - 2 * sd, EMA20PB=(l <= e20) & (c > e20) & (c > o),
             DOWN3=(c < pc) & (pc < ppc) & (ppc < pppc), MARU20=P0["MARU20"], BO10=P0["BO10"])
    cond = dict(TREND=c > e200, HT1=cond["HT1"])
    return {k: np.nan_to_num(np.asarray(v, float)).astype(bool) for k, v in P.items()}, cond, arr


def stats(nr, pe):
    o = {}
    for p in ("TRAIN", "VAL", "OOS"):
        x = nr[pe == p]; o[f"{p}_n"] = len(x)
        o[f"{p}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else np.nan
        o[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else np.nan
    return o


def main():
    rows = []; B = {}
    for name in D.INTRA:
        B[name] = R4.build(name)
        for tf in TFS:
            d = B[name][tf]
            for side in (1, -1):
                P, cond, arr = setups(d, side)
                for fam in FAMS:
                    for flt in FILTS:
                        m = P[fam].copy()
                        for c_ in flt:
                            m &= cond[c_]
                        if m.sum() < 20:
                            continue
                        for k, r, kind, n in EXITS:
                            si, ei, xi, g, nr, mfe, mae, why = run(arr, d, m, side, k, r, kind, n, tf, name)
                            if not len(nr):
                                continue
                            rows.append(dict(name=name, tf=tf, side="BUY" if side > 0 else "SELL", fam=fam, filt="+".join(flt) or "none",
                                             k=k, r=r, kind=kind, n=n, **stats(nr, d["per"][ei])))
        print(name, len(rows), flush=True)
    L = pd.DataFrame(rows); L.to_csv(RN.REPORTS / "mcx_round6.csv", index=False)
    ent = ["name", "tf", "side", "fam", "filt"]
    L["nb"] = L.assign(ok=(L.TRAIN_win >= 65) & (L.VAL_win >= 65) & (L.TRAIN_R > 0) & (L.VAL_R > 0)).groupby(ent).ok.transform("mean")
    L["score"] = np.minimum(L.TRAIN_R * np.sqrt(L.TRAIN_n), L.VAL_R * np.sqrt(L.VAL_n))
    C = L[(L.TRAIN_win >= 70) & (L.VAL_win >= 70) & (L.TRAIN_R > 0) & (L.VAL_R > 0) & (L.TRAIN_n >= 30) & (L.VAL_n >= 15) & (L.nb >= 0.3)]
    C = C.sort_values("score", ascending=False)
    print("candidates with 70 %+ in TRAIN and VALID:", len(C), C.groupby("name").size().to_dict())
    rng = np.random.default_rng(29); out = {}; trades = []
    for name in D.INTRA:
        cand = C[C.name == name].drop_duplicates(["tf", "side", "fam", "filt"]).head(10); tried = []; pick = None
        for _, x in cand.iterrows():
            side = 1 if x.side == "BUY" else -1; d = B[name][x.tf]
            P, cond, arr = setups(d, side)
            base = np.ones(len(arr["c"]), bool)
            for c_ in ([] if x.filt == "none" else x.filt.split("+")):
                base &= cond[c_]
            m = P[x.fam] & base
            si, ei, xi, g, nr, mfe, mae, why = run(arr, d, m, side, x.k, x.r, int(x.kind), int(x.n), x.tf, name)
            pe = d["per"][ei]; st = stats(nr, pe)
            rate = m.sum() / max(base.sum(), 1); dr = {p: [] for p in ("TRAIN", "VAL", "OOS")}; dw = {p: [] for p in dr}
            for _ in range(200):
                y = run(arr, d, base & (rng.random(len(base)) < rate), side, x.k, x.r, int(x.kind), int(x.n), x.tf, name)
                yp = d["per"][y[1]]
                for p in dr:
                    z = y[4][yp == p]; dr[p].append(z.mean() if len(z) else np.nan); dw[p].append(100 * (z > 0).mean() if len(z) else np.nan)
            f = d["f"]; c = f["close"].values.astype(float); o = f["open"].values.astype(float); at = f["atr"].values.astype(float)
            fac = f["raw_close"].values / c; rk = side * (o[ei] - (c[si] - side * x.k * at[si])); rs = nr * rk * fac[ei] * R4.MULT[name]
            lab = f"{R4.TFN[x.tf] if hasattr(R4, 'TFN') else x.tf} {x.fam} {x.side} · {x.filt} · {ex_label(x.k, x.r, int(x.kind), int(x.n))}"
            rec = dict(strategy=lab, tf=x.tf, side=x.side, fam=x.fam, filt=x.filt, k=x.k, r=x.r, kind=int(x.kind), n=int(x.n), **st,
                       ALL_n=len(nr), ALL_win=round(100 * float((nr > 0).mean()), 1), ALL_R=round(float(nr.mean()), 3), rs=int(rs.sum()),
                       worst_rs=int(rs.min()), avg_win_rs=int(rs[rs > 0].mean()) if (rs > 0).any() else 0,
                       avg_loss_rs=int(rs[rs <= 0].mean()) if (rs <= 0).any() else 0)
            for p in dr:
                a = np.array(dr[p], float); rec[f"{p}_random_R"] = round(float(np.nanmean(a)), 3)
                rec[f"{p}_random_win"] = round(float(np.nanmean(dw[p])), 1)
                rec[f"{p}_beats_pct"] = int(100 * np.nanmean(a < st[f"{p}_R"])) if st[f"{p}_R"] == st[f"{p}_R"] else None
            tried.append(rec)
            if pick is None and (rec["TRAIN_beats_pct"] or 0) >= 80 and (rec["VAL_beats_pct"] or 0) >= 80:
                pick = rec
                t = pd.to_datetime(f["time"])
                for i in range(len(nr)):
                    trades.append(dict(strategy=f"Round 6 · {name} 70 % setup · {lab}", commodity=name, side=x.side, entry=str(t.iloc[ei[i]])[:16],
                                       exit=str(t.iloc[xi[i]])[:16], entry_px=round(float(o[ei[i]] * fac[ei[i]]), 2),
                                       exit_px=round(float((o[ei[i]] + side * g[i] * rk[i]) * fac[ei[i]]), 2), R=round(float(nr[i]), 2),
                                       pnl_rs=int(round(rs[i])), best_rs=int(round(mfe[i] * rk[i] * fac[ei[i]] * R4.MULT[name])),
                                       worst_rs=int(round(mae[i] * rk[i] * fac[ei[i]] * R4.MULT[name])), period=str(pe[i]),
                                       result={1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll"}.get(int(why[i]), "exit")))
        out[name] = dict(pick=pick, tried=tried)
        print(f"\n{name}: " + (f"PICK {pick['strategy']}" if pick else "NO PICK"))
        for r_ in tried:
            print(f"  {r_['strategy'][:80]:80s} T {r_['TRAIN_n']}/{r_['TRAIN_win']}%/{r_['TRAIN_R']:+.2f} (rnd {r_['TRAIN_random_win']}%/{r_['TRAIN_random_R']:+.2f} b{r_['TRAIN_beats_pct']})"
                  f" V {r_['VAL_n']}/{r_['VAL_win']}%/{r_['VAL_R']:+.2f} (b{r_['VAL_beats_pct']}) O {r_['OOS_n']}/{r_['OOS_win']}%/{r_['OOS_R']} (rnd {r_['OOS_random_win']}%/{r_['OOS_random_R']} b{r_['OOS_beats_pct']}) Rs {r_['rs']:,}", flush=True)
    (RN.REPORTS / "mcx_round6_pick.json").write_text(json.dumps(dict(picks=out, trades=trades), default=lambda v: None))


if __name__ == "__main__":
    main()

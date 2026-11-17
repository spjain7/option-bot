"""STOCK / INDEX RULES ON MCX (owner 17-Nov-2026: "apply the same strategy of stock and index futures on MCX").
Every live stock / index futures rule is run UNCHANGED on the 7 MCX commodities (same signal code = alerts/rulebook.raw and
alerts/four_hour.evaluate logic, same stop / target / time exit), plus the mirrored side for information. Research only.
  candles   1h Angel (Jul-2022 ->), MCX day-anchored 2h / 3h / 4h blocks from 09:00 (= live MCX candles), daily 2006 ->
  entry     next candle open · stop k x ATR from the signal close · target r x risk · time exit as the live rule
  costs     real MCX fees + live-spread slippage (research/mcx_institutional_buy/backtesting/costs.py)
  periods   intraday TRAIN 2022-07..2024-06 / VALID 2024-07..2025-06 / OOS 2025-07..2026-10; daily 2006-16 / 2017-21 / 2022-26
  verdict   WORKS = positive with PF >= 1.2 in all three periods (>= 30 trades each) AND better than random entries with the
            same side, stop and exit in all three periods.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.run -> reports/stock_rules_on_mcx.csv"""
import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from alerts import rulebook as RB, four_hour as FH  # noqa: E402
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN, metrics as M  # noqa: E402

warnings.filterwarnings("ignore")
CPD = {"2h": 8, "3h": 5, "4h": 4, "1d": 1}         # MCX candles per session
OUT = RN.REPORTS


def blocks(h1, hours):
    """day-anchored MCX n-hour candles from 1-hour candles (09:00 anchor, as rulebook.blocks for MCX)."""
    d = h1.copy(); day = d["time"].dt.normalize()
    k = ((d["time"].dt.hour - 9).clip(lower=0) // hours).astype(int)
    return d.groupby([day, k], sort=True).agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                              close=("close", "last"), volume=("volume", "sum"), seg=("seg", "max"),
                                              raw_close=("raw_close", "last")).reset_index(drop=True)


def frames(name):
    h = D.bars(name, "1h"); d = D.bars(name, "1d")
    h1 = pd.DataFrame(dict(time=h.time, open=h.a_open, high=h.a_high, low=h.a_low, close=h.a_close, volume=h.volume, seg=h.seg,
                           raw_close=h.close))
    dd = pd.DataFrame(dict(time=d.time, open=d.a_open, high=d.a_high, low=d.a_low, close=d.a_close, volume=d.volume, seg=d.seg,
                           raw_close=d.close))
    # 17-Nov: the Angel files have holes (all commodities Jan-Apr 2022 on daily, gold Aug-Oct 2022): a gap starts a new
    # segment, so no trade is ever held across missing data (the simulator closes it at the last bar before the gap)
    for x, days in ((h1, 4), (dd, 7)):
        gap = pd.to_datetime(x["time"]).diff().dt.days.fillna(0) > days
        x["seg"] = x["seg"].values + np.cumsum(gap.values) * 100000
    fr = {"2h": blocks(h1, 2), "3h": blocks(h1, 3), "4h": blocks(h1, 4), "1d": dd}
    return {k: RB.features(v).assign(seg=v.seg.values, raw_close=v.raw_close.values) for k, v in fr.items()}, dd


def dtrend(f, dd):
    m = RB.daily_trend_map(dd.reset_index(drop=True))
    return np.nan_to_num(pd.to_datetime(f["time"]).dt.normalize().map(m).values.astype(float))


def daily_oi_rule(name, f, side):
    """stocks.py OI-breakout: close beyond the 20-day high/low, volume > 1.5x, price and total OI move (OI up >= 2 %), EMA200 side."""
    oi = D.daily_oi(name)
    if oi is None or not len(oi):
        return np.zeros(len(f), bool)
    day = pd.to_datetime(f["time"]).dt.normalize()
    o = day.map(oi.oi).values.astype(float); po = np.r_[np.nan, o[:-1]]
    c = f["close"].values; pc = np.r_[np.nan, c[:-1]]
    hh = f["high"].shift(1).rolling(20).max().values; ll = f["low"].shift(1).rolling(20).min().values
    up_oi = (o / po - 1) >= 0.02
    if side > 0:
        return (c > hh) & (f["volx"].values > 1.5) & (c > pc) & up_oi & (c > f["ema200"].values)
    return (c < ll) & (f["volx"].values > 1.5) & (c < pc) & up_oi & (c < f["ema200"].values)


def rules():
    out = []
    for rid, r in RB.RULES.items():
        if r["mkt"] in ("STOCKS", "INDEX") and not r.get("experimental"):
            out.append(dict(id=rid, src="rulebook", tf=r["tf"], side=1 if r["side"] == "BUY" else -1, k=r["k"], r=r["r"],
                            maxh=r["maxh"], fam=r["fam"], par=r["par"], filt=r["filt"], kind=0))
    for key, tf in (("NFO", "4h"), ("NFO3H", "3h")):
        r = FH.RULES[key]
        out.append(dict(id=f"STK_{tf}_SELL_FOURHOUR", src="four_hour", tf=tf, side=-1, k=r["k"], r=r["r"], maxh=r["max_days"] * CPD[tf],
                        N=r["N"], vol=r["vol"], ema=r.get("ema", True), dt=r.get("dtrend"), kind=0))
    for sd in (1, -1):
        out.append(dict(id=f"STK_1d_OIBO_{'BUY' if sd > 0 else 'SELL'}", src="stocks_oi", tf="1d", side=sd, k=2.0, r=0.0, maxh=40, kind=2))
    return out


def signal(rule, f, dd, name, side):
    if rule["src"] == "rulebook":
        b, s_ = RB.raw(f, rule["fam"], rule["par"])
        m = (b if side > 0 else s_).copy()
        if rule["filt"] == "EMA200":
            m &= side * (f["close"].values - f["ema200"].values) > 0
        if rule["filt"].startswith("DT"):
            m &= dtrend(f, dd) == side
        return m
    if rule["src"] == "four_hour":
        c, v = f["close"], f["volume"].astype(float)
        hh, ll = f["high"].shift(1).rolling(rule["N"]).max(), f["low"].shift(1).rolling(rule["N"]).min()
        vx = v / v.rolling(20).mean().shift(1)
        m = ((c < ll) if side < 0 else (c > hh)) & (vx >= rule["vol"])
        if rule["ema"]:
            m &= (c < f["ema200"]) if side < 0 else (c > f["ema200"])
        if rule.get("dt"):
            m &= pd.Series(dtrend(f, dd) == side)
        return m.fillna(False).values
    return daily_oi_rule(name, f, side)


def simulate(f, sig, side, k, r, maxh, kind, name, tf):
    """SELL trades via mirrored prices: the BUY simulator on -price is a short on price (costs kept positive)."""
    s_ = 1 if side > 0 else -1
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = f["atr"].values.astype(float)
    if s_ < 0:
        o, h, l, c = -o, -l, -h, -c
    stop = c - k * a
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * (1 if s_ > 0 else -1)
    si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(o, h, l, c, a, f["seg"].values.astype(np.int64), costf, np.asarray(sig, bool),
                                                       stop, np.full(len(c), np.nan), np.full(len(c), np.nan), kind, float(r),
                                                       int(maxh), int(maxh), 3.0, 3, 0.25, 6.0, 1.5)
    t = pd.to_datetime(f["time"]).values
    return pd.DataFrame(dict(name=name, entry=t[ei], exit_t=t[xi], netR=nr, grossR=g, mfeR=mfe, maeR=mae, bars=xi - ei + 1))


def main():
    R = rules(); rows = []; all_t = []
    for name in D.INTRA:
        F, dd = frames(name)
        for rule in R:
            f = F[rule["tf"]]
            every = np.zeros(len(f), bool); every[::10] = True
            for side, lab in ((rule["side"], "AS LIVE"), (-rule["side"], "MIRRORED")):
                sig = signal(rule, f, dd, name, side)
                for kind_lab, s_ in (("rule", sig), ("random", every)):
                    T = simulate(f, s_, side, rule["k"], rule["r"], rule["maxh"], rule["kind"], name, rule["tf"])
                    T["rule"], T["tf"], T["side"], T["variant"], T["what"] = rule["id"], rule["tf"], "BUY" if side > 0 else "SELL", lab, kind_lab
                    all_t.append(T)
        print(name, "done", flush=True)
    T = pd.concat(all_t, ignore_index=True)
    T["period"] = [RN.period_of(tf, x)[0] if False else None for tf, x in zip(T.tf, T.entry)] if False else None
    T["period"] = np.where(T.tf == "1d", RN.period_of("1d", T.entry), RN.period_of("1h", T.entry))
    oi_rows = T.rule.str.contains("OIBO")
    T.loc[oi_rows, "period"] = RN.period_of("1h", T.loc[oi_rows, "entry"])        # OI exists from Jul-2022 only
    T.to_parquet(D.CACHE / "stock_rules_on_mcx_trades.parquet", index=False)
    for (rid, tf, side, var), g in T.groupby(["rule", "tf", "side", "variant"]):
        r = dict(rule=rid, tf=tf, side=side, variant=var)
        for p in ("TRAIN", "VAL", "OOS"):
            s = M.summary(g[(g.what == "rule") & (g.period == p)]); b = M.summary(g[(g.what == "random") & (g.period == p)])
            r.update({f"{p}_n": s.get("n", 0), f"{p}_win": s.get("win"), f"{p}_R": s.get("R"), f"{p}_PF": s.get("PF"), f"{p}_random_R": b.get("R")})
        s = M.summary(g[g.what == "rule"])
        r.update(ALL_n=s.get("n", 0), ALL_win=s.get("win"), ALL_R=s.get("R"), ALL_PF=s.get("PF"), maxDD_R=s.get("maxDD_R"))
        gr = g[g.what == "rule"]
        r["per_commodity"] = "; ".join(f"{n}:{x.mean():+.2f}({len(x)})" for n, x in gr.groupby("name").netR)
        r["commodities_positive"] = f"{int((gr.groupby('name').netR.mean() > 0).sum())}/{gr.name.nunique()}"
        ok = all((r[f"{p}_n"] or 0) >= 30 and (r[f"{p}_R"] or -9) > 0 and (r[f"{p}_PF"] or 0) >= 1.2 for p in ("TRAIN", "VAL", "OOS"))
        beat = all((r[f"{p}_R"] or -9) > (r[f"{p}_random_R"] if r[f"{p}_random_R"] is not None else 9) for p in ("TRAIN", "VAL", "OOS"))
        r["verdict"] = ("WORKS" if ok and beat else "POSITIVE BUT NOT BETTER THAN RANDOM" if ok else
                        "MIXED" if (r["ALL_R"] or -9) > 0 else "FAILS")
        rows.append(r)
    L = pd.DataFrame(rows).sort_values(["variant", "ALL_R"], ascending=[True, False])
    L.to_csv(OUT / "stock_rules_on_mcx.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
    print(L[["rule", "tf", "side", "variant", "TRAIN_n", "TRAIN_R", "VAL_n", "VAL_R", "OOS_n", "OOS_win", "OOS_R", "OOS_random_R",
             "ALL_n", "ALL_win", "ALL_R", "commodities_positive", "verdict"]].to_string(index=False))


if __name__ == "__main__":
    main()

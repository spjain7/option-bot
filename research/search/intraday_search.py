"""INTRADAY-001 – see REGISTRY_INTRADAY.md.  python -m research.search.intraday_search"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import stock_check as SC, stock_search as SR, strategy_search as SS, stock_oi_search as SO  # noqa

SPLIT = pd.Timestamp("2024-07-01")
OUT = ROOT / "research" / "search" / "results_intraday"
FAM = ["orb_trend", "gap_hold", "pdh_break", "vwap_pullback", "oi_orb", "dip_buy"]


def prep(h, oi=None):
    h = h[(h["time"].dt.hour >= 9)].copy().reset_index(drop=True)
    h["day"] = h["time"].dt.normalize()
    h["k"] = h.groupby("day").cumcount()
    d = h.groupby("day").agg(o=("open", "first"), hi=("high", "max"), lo=("low", "min"), c=("close", "last"))
    d["e50"] = I.ema(d["c"], 50)
    d["trend"] = np.sign(d["c"] - d["e50"]).shift(1)            # known before the session
    d["pc"], d["ph"], d["pl"] = d["c"].shift(1), d["hi"].shift(1), d["lo"].shift(1)
    if oi is not None:
        o = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last()
        d["doi"] = o.reindex(d.index).pct_change()
        d["dp"] = d["c"].pct_change()
        d["lb_y"] = ((d["dp"] > 0) & (d["doi"] >= 0.02)).shift(1).fillna(False)
        d["sb_y"] = ((d["dp"] < 0) & (d["doi"] >= 0.02)).shift(1).fillna(False)
    h = h.join(d, on="day")
    h["atr"] = I.atr(h, 14)
    h["rsi"] = I.rsi(h["close"], 14)
    key = h["time"].dt.hour * 60 + h["time"].dt.minute
    v = h["volume"].astype(float)
    h["volx"] = v / v.groupby(key).transform(lambda s: s.shift(1).rolling(10, min_periods=5).mean())
    tp = (h["high"] + h["low"] + h["close"]) / 3
    h["vwap"] = (tp * v).groupby(h["day"]).cumsum() / v.groupby(h["day"]).cumsum().replace(0, np.nan)
    f = h[h["k"] == 0].set_index("day")
    h["fh_hi"], h["fh_lo"], h["fh_c"] = h["day"].map(f["high"]), h["day"].map(f["low"]), h["day"].map(f["close"])
    return h


def day_trades(g, fam, tgt, mcx):
    """At most one trade per day. g = one session's 1-hour candles (prepared)."""
    n = len(g)
    if n < 3 or pd.isna(g["trend"].iat[0]) or pd.isna(g["atr"].iat[0]):
        return None
    t = g["trend"].iat[0]
    for i in range(1, n - 1):
        x = g.iloc[i]
        s, stop, tp = 0, None, None
        if fam in ("orb_trend", "oi_orb"):
            if x.close > x.fh_hi and x.volx > 1.5 and t > 0:
                s, stop = 1, x.fh_lo
            elif x.close < x.fh_lo and x.volx > 1.5 and t < 0:
                s, stop = -1, x.fh_hi
            if fam == "oi_orb" and s and not (x.lb_y if s > 0 else x.sb_y):
                s = 0
        elif fam == "gap_hold":
            if i == 1 and abs(x.o / x.pc - 1) >= 0.01:
                if x.o > x.pc and t > 0 and x.fh_c > x.o:
                    s, stop = 1, x.fh_lo
                elif x.o < x.pc and t < 0 and x.fh_c < x.o:
                    s, stop = -1, x.fh_hi
        elif fam == "pdh_break":
            if x.close > x.ph and x.volx > 1.5 and t > 0:
                s, stop = 1, None
            elif x.close < x.pl and x.volx > 1.5 and t < 0:
                s, stop = -1, None
        elif fam == "vwap_pullback":
            late = x.time.hour * 60 + x.time.minute >= 11 * 60 + 15
            if late and t > 0 and x.low <= x.vwap < x.close and g["close"].iloc[:i].gt(g["vwap"].iloc[:i]).all():
                s = 1
            elif late and t < 0 and x.high >= x.vwap > x.close and g["close"].iloc[:i].lt(g["vwap"].iloc[:i]).all():
                s = -1
        elif fam == "dip_buy":
            if i == 1 and t > 0 and (x.pc - x.fh_lo) > 1.5 * x.atr and x.rsi < 30:
                s, tp = 1, x.pc
        if not s:
            continue
        e0 = g["open"].iat[i + 1]
        if stop is None:
            stop = e0 - s * x.atr
        risk = s * (e0 - stop)
        if risk <= 0 or risk > 3 * x.atr:
            return None
        if tp is None:
            tp = e0 + s * tgt * risk
        if s * (tp - e0) <= 0:
            return None
        for j in range(i + 1, n):
            y = g.iloc[j]
            if (y.low <= stop) if s > 0 else (y.high >= stop):
                px = min(y.open, stop) if s > 0 else max(y.open, stop)
                return (x.time, s, s * (px - e0), risk, e0)
            if (y.high >= tp) if s > 0 else (y.low <= tp):
                return (x.time, s, s * (tp - e0), risk, e0)
        return (x.time, s, s * (g["close"].iat[-1] - e0), risk, e0)
    return None


def run_universe(items, mcx):
    rows = []
    for name, h, lot, oi in items:
        hp = prep(h, oi)
        for fam, tgt in itertools.product(FAM, (1.0, 1.5)):
            if fam == "oi_orb" and oi is None:
                continue
            if fam == "dip_buy" and tgt == 1.5:
                continue
            for day, g in hp.groupby("day"):
                r = day_trades(g.reset_index(drop=True), fam, tgt, mcx)
                if r:
                    t0, s, gross, risk, e0 = r
                    cp = INS.cost_points(name, e0) if mcx else SC.cost_frac(e0, lot)
                    rows.append((name, fam, tgt, t0, s, (gross - cp) / risk, (gross - 2 * cp) / risk))
        print(name, flush=True)
    return pd.DataFrame(rows, columns=["name", "fam", "tgt", "time", "side", "r1", "r2"])


def evaluate(T, label):
    T["period"] = np.where(T["time"] < SPLIT, "design", "holdout")
    res = {}
    for (fam, tgt), g in T.groupby(["fam", "tgt"]):
        d, ho = g[g["period"] == "design"], g[g["period"] == "holdout"]
        sd = SR.stats(d["r1"])
        short = (sd.get("trades", 0) >= 60 and sd["exp_r"] >= 0.10 and (sd["pf"] or 0) >= 1.2 and sd["p5"] > 0 and d["r2"].mean() > 0)
        row = dict(design=sd, design_2x=round(float(d["r2"].mean()), 3) if len(d) else None, shortlisted=bool(short))
        if short:
            sh = SR.stats(ho["r1"])
            row.update(holdout=sh, holdout_2x=round(float(ho["r2"].mean()), 3),
                       PASS=bool(sh.get("trades", 0) >= 60 and sh["exp_r"] >= 0.05 and (sh["pf"] or 0) >= 1.1 and ho["r2"].mean() > 0))
        res[f"{label}|{fam}|T{tgt}"] = row
        print(label, fam, tgt, sd, "2x", row["design_2x"], "| HO", row.get("holdout"), row.get("holdout_2x"), "PASS" if row.get("PASS") else "", flush=True)
    return res


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    stock_items = []
    for r in man.itertuples():
        f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if f.exists():
            h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
            stock_items.append((r.name, h, r.lot, pd.read_csv(fo) if fo.exists() else None))
    mcx_items = [(n, SS.load("MCX", n, "ONE_HOUR"), None, None) for n in ("CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM")]
    TS = run_universe(stock_items, False)
    TM = run_universe([x for x in mcx_items if x[1] is not None], True)
    res = evaluate(TS, "STOCKS")
    res.update(evaluate(TM, "MCX"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
    TS.assign(u="STOCKS").pipe(lambda x: pd.concat([x, TM.assign(u="MCX")])).to_csv(OUT / "trades.csv.gz", index=False)


if __name__ == "__main__":
    main()

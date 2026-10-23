"""STOCK-1H-002 – see REGISTRY_STOCK1H.md.  python -m research.search.stock_1h2"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research.search import stock_check as SC, stock_search as SR, strategy_search as SS  # noqa
from alerts.stocks import in_rollover_window  # noqa

SPLIT = pd.Timestamp("2024-07-01")
OUT = ROOT / "research" / "search" / "results_stock1h"


def load():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    out = {}
    for r in man.itertuples():
        f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if not f.exists():
            continue
        h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        h["day"] = h["time"].dt.normalize()
        h["k"] = h.groupby("day").cumcount()
        oi = pd.read_csv(fo) if fo.exists() else None
        out[r.name] = (h, r.lot, oi)
    return out


def daily(h, oi):
    d = h.groupby("day").agg(o=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                             v=("volume", "sum"))
    d["rsi2"] = I.rsi(d["close"], 2)
    d["sma5"] = d["close"].rolling(5).mean()
    d["e200"], d["e50"] = I.ema(d["close"], 200), I.ema(d["close"], 50)
    d["atr"] = I.atr(d.rename(columns={"o": "open"}), 14)
    d["vavg"] = d["v"].rolling(20).mean().shift(1)
    if oi is not None:
        o = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last().reindex(d.index)
        doi, dp = o.pct_change(), d["close"].pct_change()
        d["sb"], d["lb"] = (dp < 0) & (doi >= 0.02), (dp > 0) & (doi >= 0.02)
    else:
        d["sb"] = d["lb"] = False
    return d


def net(e, x, s, lot):
    c = SC.cost_frac(e, lot) / e
    g = s * (x - e) / e
    return g - c, g - 2 * c


def run():
    data = load()
    nifty = SS.load("NFO", "NIFTY", "ONE_HOUR")
    nifty["day"] = nifty["time"].dt.normalize()
    nd = nifty.groupby("day").agg(c=("close", "last"))
    n_fh = nifty[nifty["time"].dt.hour == 9].set_index("day")["close"]
    n_fh_ret = (n_fh / nd["c"].shift(1).reindex(n_fh.index) - 1)
    rows = []
    cs1, cs2 = [], []                                             # cross-sectional candidates
    for name, (h, lot, oi) in data.items():
        d = daily(h, oi)
        days = list(d.index)
        pos = {dd: i for i, dd in enumerate(days)}
        H = {dd: g.reset_index(drop=True) for dd, g in h.groupby("day")}
        for i, dd in enumerate(days[1:-1], start=1):
            g = H[dd]
            if len(g) < 6 or in_rollover_window(dd):
                continue
            pc = d["close"].iat[i - 1]
            # R1 / R2 candidates
            fh = g["close"].iat[0] / pc - 1
            cs1.append((dd, name, fh, g["open"].iat[1], g["close"].iat[-1],
                        H[days[i + 1]]["close"].iat[-1] if i + 1 < len(days) else np.nan, lot))
            if len(g) >= 7:
                r14 = g["close"].iat[4] / pc - 1
                cs2.append((dd, name, r14, g["open"].iat[5], g["close"].iat[-1], lot))
            # R3 overnight
            dr = d.iloc[i]
            nxt = H.get(days[i + 1]) if i + 1 < len(days) else None
            if nxt is not None and len(nxt) >= 2 and not in_rollover_window(days[i + 1]) and dr.vavg > 0:
                rngp = (dr.close - dr.low) / max(dr.high - dr.low, 1e-9)
                e = g["open"].iat[-1]
                for s, ok in ((1, rngp >= 0.8 and dr.v > 1.5 * dr.vavg and dr.close > dr.e50),
                              (-1, rngp <= 0.2 and dr.v > 1.5 * dr.vavg and dr.close < dr.e50)):
                    if ok:
                        for var, x in (("R3a", nxt["close"].iat[0]), ("R3b", nxt["close"].iat[-1])):
                            n1, n2 = net(e, x, s, lot)
                            rows.append(("R3", var, name, dd, s, n1, n2))
            # R4/R5/R6 rsi2 dip (signal at day close dd, entry next day)
            if i + 6 >= len(days) or pd.isna(dr.e200) or pd.isna(dr.atr):
                continue
            for s, ok in ((1, dr.rsi2 < 10 and dr.close > dr.e200), (-1, dr.rsi2 > 90 and dr.close < dr.e200)):
                if not ok:
                    continue
                span = days[i + 1:i + 7]
                if any(in_rollover_window(x) for x in span[:6]):
                    continue
                oi_ok = not (dr.sb if s > 0 else dr.lb)
                # R6 entry: first 1h hammer/engulf (long) on the next day, enter next candle open
                n0 = H[days[i + 1]]
                e6 = None
                for j in range(len(n0) - 1):
                    o_, h_, l_, c_ = n0.loc[j, ["open", "high", "low", "close"]]
                    body, rg = abs(c_ - o_), max(h_ - l_, 1e-9)
                    lo, up = min(o_, c_) - l_, h_ - max(o_, c_)
                    pat = (lo >= 2 * body and up <= 0.3 * rg) if s > 0 else (up >= 2 * body and lo <= 0.3 * rg)
                    if j > 0:
                        po, pc_ = n0.loc[j - 1, ["open", "close"]]
                        pat = pat or ((c_ > o_ and pc_ < po and c_ >= po and o_ <= pc_) if s > 0 else (c_ < o_ and pc_ > po and c_ <= po and o_ >= pc_))
                    if pat:
                        e6 = n0["open"].iat[j + 1]
                        break
                for var, stop_on in (("R4a", False), ("R4b", True)):
                    e = d["o"].iat[i + 1]
                    st = e - s * 3 * dr.atr
                    x = None
                    for k in range(i + 1, i + 6):
                        b = d.iloc[k]
                        if stop_on and ((b.low <= st) if s > 0 else (b.high >= st)):
                            x = st; break
                        if (b.close > b.sma5) if s > 0 else (b.close < b.sma5):
                            x = b.close; break
                    if x is None:
                        x = d["close"].iat[i + 5]
                    n1, n2 = net(e, x, s, lot)
                    rows.append(("R4", var, name, dd, s, n1, n2))
                    if oi_ok:
                        rows.append(("R5", var.replace("R4", "R5"), name, dd, s, n1, n2))
                    if e6 is not None and var == "R4a":
                        n1, n2 = net(e6, x, s, lot)
                        rows.append(("R6", "R6", name, dd, s, n1, n2))
        print(name, flush=True)
    # cross-sectional ranks
    C1 = pd.DataFrame(cs1, columns=["day", "name", "fh", "e", "x_a", "x_b", "lot"])
    C1["rel"] = C1["fh"] - C1["day"].map(n_fh_ret)
    C1["mkt"] = np.sign(C1["day"].map(n_fh_ret))
    for N in (3, 5):
        for dd, g in C1.dropna(subset=["rel", "mkt"]).groupby("day"):
            m = g["mkt"].iat[0]
            if m == 0 or len(g) < 30:
                continue
            pick = g.nlargest(N, "rel") if m > 0 else g.nsmallest(N, "rel")
            for r in pick.itertuples():
                for var, x in (("R1a", r.x_a), ("R1b", r.x_b)):
                    if x == x:
                        n1, n2 = net(r.e, x, int(m), r.lot)
                        rows.append(("R1", f"{var}_N{N}", r.name, dd, int(m), n1, n2))
    C2 = pd.DataFrame(cs2, columns=["day", "name", "r", "e", "x", "lot"])
    for N in (3, 5):
        for dd, g in C2.groupby("day"):
            if len(g) < 30:
                continue
            for s, pick in ((1, g.nlargest(N, "r")), (-1, g.nsmallest(N, "r"))):
                for r in pick.itertuples():
                    n1, n2 = net(r.e, r.x, s, r.lot)
                    rows.append(("R2", f"R2_N{N}", r.name, dd, s, n1, n2))
    return pd.DataFrame(rows, columns=["fam", "var", "name", "day", "side", "net", "net2"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    T = run()
    T.to_pickle(OUT / "trades.pkl")
    res = {}
    for keys, g in list(T.groupby(["var"])) + list(T.groupby(["var", "side"])):
        k = "|".join(str(x) for x in (keys if isinstance(keys, tuple) else (keys,)))
        D, Hh = g[g["day"] < SPLIT], g[g["day"] >= SPLIT]
        sd = SR.stats(D["net"] * 100)
        short = bool(sd.get("trades", 0) >= 100 and sd["exp_r"] > 0.05 and D["net2"].mean() > 0 and sd["p5"] > 0)
        sh = SR.stats(Hh["net"] * 100)
        row = dict(design=sd, design_2x_pct=round(float(D["net2"].mean() * 100), 3), shortlisted=short,
                   holdout=sh, holdout_2x_pct=round(float(Hh["net2"].mean() * 100), 3) if len(Hh) else None)
        row["PASS"] = bool(short and sh.get("trades", 0) >= 100 and row["holdout_2x_pct"] > 0)
        res[k] = row
        print(f"{k:14s} design n={sd.get('trades')} win={sd.get('win')} net%={sd.get('exp_r')} 2x={row['design_2x_pct']} "
              f"| HO n={sh.get('trades')} win={sh.get('win')} net%={sh.get('exp_r')} 2x={row['holdout_2x_pct']}"
              + ("  SHORTLIST" if short else "") + ("  PASS" if row["PASS"] else ""))
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()

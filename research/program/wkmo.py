"""WKMO-001 (6-Nov-2026, owner: "why not counting monthly / weekly breakout, why no trade?").
Weekly and monthly breakouts on long history: MCX front-month stitched daily 2006-2026 (7 commodities, NATURALGAS from 2016),
NIFTY / BANKNIFTY futures 2011-2026. Candles: weekly (Mon-Fri), monthly. Close beyond the N-candle high/low, entry next candle open
(skipped if > 0.5 ATR away), stop k × ATR14 of that timeframe, target r × R, max 26 weeks / 12 months; 2x costs; both sides.
Also the live monthly rule style: first DAILY close beyond last month's high/low (stop 1.5 / 3 daily ATR, 2R / 3R, max 40 days).
Filters: none / EMA20 of that timeframe / volume ≥ 1.5x.  Periods: 2006-12 · 2013-19 · 2020-26 (robust = all three > 0).
python research/program/wkmo.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

D = ROOT / "research/data/angel"
man = pd.read_csv(D / "manifest.csv")
INST = [("MCX", n) for n in ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]] + [("NFO", "NIFTY"), ("NFO", "BANKNIFTY")]


def daily(ex, nm):
    m = man[(man.exch == ex) & (man.name == nm) & (man.interval == "ONE_DAY")]
    m = m[m.front_stitched.astype(str) == "True"] if ex == "MCX" else m.sort_values("bars", ascending=False).head(1)
    d = pd.read_csv(D / ex / f"{m.symbol.iat[0]}_ONE_DAY.csv", parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
    d = d.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    d["volume"] = d["volume"].clip(lower=0)
    return d


def agg(d, rule):
    g = d.set_index("time").resample(rule, label="left", closed="left")
    x = g.agg(dict(open="first", high="max", low="min", close="last", volume="sum")).dropna().reset_index()
    return x


def per(t):
    y = pd.Timestamp(t).year
    return "2006-12" if y <= 2012 else ("2013-19" if y <= 2019 else "2020-26")


rows = []
for ex, nm in INST:
    d = daily(ex, nm)
    cost_fn = (lambda p: INS.cost_points(nm, p, 1.0)) if ex == "MCX" else (lambda p: p * 0.0004)
    frames = {"weekly": (agg(d, "W-MON"), (4, 10, 20, 52), 26, 52), "monthly": (agg(d, "MS"), (1, 3, 6, 12), 12, 20)}
    for tf, (f0, Ns, maxh, start) in frames.items():
        f = H.features(f0); f["switch"] = False
        f["ema20"] = I.ema(f.close, 20)
        cost = np.array([cost_fn(p) for p in f.close.values])
        for N in Ns:
            hh, ll = f.high.shift(1).rolling(N).max(), f.low.shift(1).rolling(N).min()
            for fl in ("none", "EMA20", "VOL1.5"):
                fb = (f.close > f.ema20) if fl == "EMA20" else ((f.volx >= 1.5) if fl == "VOL1.5" else True)
                fs = (f.close < f.ema20) if fl == "EMA20" else ((f.volx >= 1.5) if fl == "VOL1.5" else True)
                for side, ok in ((1, (f.close > hh) & fb), (-1, (f.close < ll) & fs)):
                    sig = np.where(np.asarray(ok, bool), side, 0)
                    for k, r in ((1.5, 2.0), (2.0, 3.0), (3.0, 2.0), (3.0, 6.0)):
                        for x in H.simulate(f, sig, side, k, r, maxh, 0, cost, start=start):
                            if x["status"] == "trade":
                                rows.append((tf, f"N{N}", fl, "BUY" if side > 0 else "SELL", f"{k:g}ATR/{r:g}R", ex, nm, x["time"], x["r2"]))
    # live-style monthly: first daily close beyond the previous month's high / low
    f = H.features(d); f["switch"] = False
    mo = d.set_index("time").resample("MS").agg(dict(high="max", low="min"))
    key = d.time.dt.to_period("M").dt.to_timestamp()
    ph = key.map(mo.high.shift(1)).values; pl = key.map(mo.low.shift(1)).values
    c = f.close.values
    first_b = pd.Series((c > ph)).groupby(key.values).cumsum().values == 1
    first_s = pd.Series((c < pl)).groupby(key.values).cumsum().values == 1
    cost = np.array([cost_fn(p) for p in c])
    for side, ok in ((1, (c > ph) & first_b), (-1, (c < pl) & first_s)):
        sig = np.where(ok, side, 0)
        for k, r in ((1.5, 2.0), (1.5, 3.0), (3.0, 3.0)):
            for x in H.simulate(f, sig, side, k, r, 40, 0, cost, start=60):
                if x["status"] == "trade":
                    rows.append(("monthly-level (daily close)", "prev month", "none", "BUY" if side > 0 else "SELL", f"{k:g}ATR/{r:g}R", ex, nm, x["time"], x["r2"]))

T = pd.DataFrame(rows, columns=["tf", "N", "filt", "side", "exit", "ex", "name", "time", "r"])
T["per"] = T.time.map(per)
T["grp"] = np.where(T.ex == "MCX", "MCX", "INDEX")
K = ["grp", "tf", "N", "filt", "side", "exit"]
S = T.groupby(K).agg(n=("r", "size"), win=("r", lambda s: (s > 0).mean() * 100), R=("r", "mean"),
                     per_year=("time", lambda s: len(s) / max((s.max() - s.min()).days / 365, 1)))
S = S.join(T.pivot_table(index=K, columns="per", values="r", aggfunc="mean"))
S = S.join(T.groupby(K + ["name"]).r.mean().gt(0).groupby(level=list(range(len(K)))).mean().rename("names_pos"))
S["all3"] = (S[["2006-12", "2013-19", "2020-26"]].fillna(-1) > 0).all(axis=1)
S = S.reset_index()
S.to_csv(ROOT / "research/program/results/wkmo_summary.csv", index=False)
T.to_csv(ROOT / "research/program/results/wkmo_trades.csv.gz", index=False)
pd.set_option("display.width", 240); pd.set_option("display.max_rows", 200)
for g in ("MCX", "INDEX"):
    x = S[(S.grp == g) & S.all3 & (S.n >= (60 if g == "MCX" else 25))].sort_values("R", ascending=False)
    print(f"\n=== {g}: robust (all 3 periods), {len(x)} – top 15"); print(x.head(15).round(3).to_string(index=False))
    y = S[(S.grp == g)]
    print(f"--- {g} best SELL:"); print(y[y.side == "SELL"].sort_values("R", ascending=False).head(4).round(3).to_string(index=False))
print("\nLIVE-style rules:"); print(S[(S.tf == "monthly-level (daily close)") | ((S.tf == "weekly") & (S.N == "N20") & (S.filt == "none") & (S.exit == "3ATR/2R"))].round(3).to_string(index=False))

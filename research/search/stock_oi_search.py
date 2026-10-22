"""STOCK-OI-001 – stock futures with VOLUME + OI + support/resistance + trend + RSI (pre-registered here, research only).

Data: daily candles (from Angel 1-hour) + daily OI of the stitched front-month future (Angel getOIData, NFO), 181 stocks.
OI change is ignored in the 3 trading days before and the 2 after each monthly expiry (rollover makes OI collapse/jump).
Buildup on a day: price change and OI change ≥ threshold → Long buildup (P↑ OI↑), Short buildup (P↓ OI↑),
Short covering (P↑ OI↓), Long unwinding (P↓ OI↓).
Families (long version; short = mirror), parameters fixed in advance:
  O1 oi_breakout    close > 20-day high (resistance broken), volume > 1.5× avg, Long buildup, close > EMA200
  O2 oi_trend       close > EMA50 > EMA200, Long buildup with price ≥ +1%
  O3 oi_pullback    uptrend (EMA50 > EMA200), RSI(14) was < 40 in the last 3 days, today Long buildup
  O4 oi_support     close within 1 ATR above the 20-day low (support), RSI(14) < 35, today Short covering or Long buildup, close > EMA200
  O5 oi_market      O1 + NIFTY above its EMA50 (longs) / below (shorts)
OI threshold ∈ {2%, 5%}. Exits ∈ {trail: stop 2 ATR + 3 ATR trailing, max 40 days · t2r: stop 1.5 ATR, target 2R, max 15 ·
t1r: stop 2 ATR, target 1R, max 10}. Sides: long only, and long+short.
Split: design < 2024-07-01, hold-out ≥ 2024-07-01. Costs as STOCK-CHECK-001.
SHORTLIST (design): ≥ 80 trades, ≥ +0.10R, PF ≥ 1.20, bootstrap p5 > 0, > 0 at 2× costs.
PASS (hold-out, shortlisted only): ≥ 80 trades, ≥ +0.05R, PF ≥ 1.10, > 0 at 2× costs.
Only PASS rules may become live stock-futures alerts.
"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from alerts import stocks as STK  # noqa
from research.search import stock_check as SC, stock_search as SR  # noqa

DATA = SR.DATA
OUT = ROOT / "research" / "search" / "results_stock_oi"
SPLIT = pd.Timestamp("2024-07-01")
FAM = ["oi_breakout", "oi_trend", "oi_pullback", "oi_support", "oi_market"]
OITH = [0.02, 0.05]
EXITS = {"trail": (2.0, None, 3.0, 40), "t2r": (1.5, 2.0, None, 15), "t1r": (2.0, 1.0, None, 10)}


def load(name):
    f, fo = DATA / f"{name}_ONE_HOUR.csv", DATA / f"{name}_OI_ONE_DAY.csv"
    if not f.exists() or not fo.exists():
        return None
    d = SR.daily(pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]).reset_index(drop=True)
    o = pd.read_csv(fo)
    o["time"] = pd.to_datetime(o["time"].astype(str).str[:10])
    d = d.merge(o.groupby("time")["oi"].last().reset_index(), on="time", how="left")
    return d


def features(d, nf, roll_days):
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"].astype(float)
    f = pd.DataFrame(index=d.index)
    f["e50"], f["e200"] = I.ema(c, 50), I.ema(c, 200)
    f["rsi"] = I.rsi(c, 14)
    f["atr"] = I.atr(d, 14)
    f["volx"] = v / v.rolling(20).mean().shift(1)
    f["hh20"], f["ll20"] = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    f["dp"] = c.pct_change()
    f["doi"] = d["oi"].pct_change()
    days = d["time"].reset_index(drop=True)
    bad = pd.Series(False, index=d.index)
    for rdy in roll_days:                                    # rollover window: 3 sessions before .. 2 after the switch
        k = days.searchsorted(rdy)
        bad.iloc[max(0, k - 4):k + 2] = True
    f.loc[bad, "doi"] = np.nan
    mk = nf.reindex(d["time"].values)
    f["mkt_up"] = (mk["close"] > mk["e50"]).values
    f["mkt_dn"] = (mk["close"] < mk["e50"]).values
    return f


def signal(d, f, fam, th):
    c = d["close"]
    up_t = (c > f["e50"]) & (f["e50"] > f["e200"]); dn_t = (c < f["e50"]) & (f["e50"] < f["e200"])
    lb = (f["dp"] > 0) & (f["doi"] >= th); sb = (f["dp"] < 0) & (f["doi"] >= th)
    sc = (f["dp"] > 0) & (f["doi"] <= -th); lu = (f["dp"] < 0) & (f["doi"] <= -th)
    if fam in ("oi_breakout", "oi_market"):
        L = (c > f["hh20"]) & (f["volx"] > 1.5) & lb & (c > f["e200"])
        S = (c < f["ll20"]) & (f["volx"] > 1.5) & sb & (c < f["e200"])
        if fam == "oi_market":
            L &= f["mkt_up"]; S &= f["mkt_dn"]
    elif fam == "oi_trend":
        L = up_t & lb & (f["dp"] >= 0.01); S = dn_t & sb & (f["dp"] <= -0.01)
    elif fam == "oi_pullback":
        L = (f["e50"] > f["e200"]) & (f["rsi"].rolling(3).min() < 40) & lb
        S = (f["e50"] < f["e200"]) & (f["rsi"].rolling(3).max() > 60) & sb
    else:
        L = (c <= f["ll20"] + f["atr"]) & (f["rsi"] < 35) & (sc | lb) & (c > f["e200"])
        S = (c >= f["hh20"] - f["atr"]) & (f["rsi"] > 65) & (lu | sb) & (c < f["e200"])
    return np.where(L.fillna(False), 1, np.where(S.fillna(False), -1, 0))


def run(d, f, sig, lot, roll_days, ex, both):
    sk, tg, tr, mx = EXITS[ex]
    a = f["atr"].values
    o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
    rd = d["time"].isin(roll_days).values
    nx = np.r_[rd[1:], False]
    out, pos = [], None
    for i in range(210, len(d) - 1):
        if pos is not None:
            s, e0, st, risk, k0, best, tp = pos
            px = None
            if (o[i] <= st) if s > 0 else (o[i] >= st): px = o[i]
            elif (l[i] <= st) if s > 0 else (h[i] >= st): px = st
            elif tp is not None and ((h[i] >= tp) if s > 0 else (l[i] <= tp)): px = tp
            elif nx[i] or i - k0 >= mx: px = c[i] if nx[i] else o[i + 1]
            if px is not None:
                out.append((d["time"].iat[k0], s, s * (px - e0), SC.cost_frac(e0, lot), risk)); pos = None
            else:
                if tr:
                    best = max(best, c[i]) if s > 0 else min(best, c[i])
                    ns = best - s * tr * a[i]
                    if s * (ns - st) > 0: st = ns
                pos = (s, e0, st, risk, k0, best, tp)
            continue
        s = int(sig[i])
        if s == 0 or (s < 0 and not both) or rd[i] or nx[i] or not a[i] > 0:
            continue
        e0 = o[i + 1]; risk = sk * a[i]
        pos = (s, e0, e0 - s * risk, risk, i + 1, e0, e0 + s * tg * risk if tg else None)
    return out


def main():
    nf = SR.nifty_daily()
    man = pd.read_csv(DATA / "manifest_stocks.csv")
    rows, cover = [], []
    for r in man.itertuples():
        d = load(r.name)
        if d is None or len(d) < 260:
            continue
        cover.append(dict(name=r.name, oi_days=int(d["oi"].notna().sum()), first_oi=str(d.loc[d["oi"].notna(), "time"].min())[:10]))
        days = pd.Series(d["time"]); roll = set()
        for y in range(days.min().year, days.max().year + 1):
            for m in range(1, 13):
                e = STK.nfo_expiry(y, m); nxt = days[days > e]
                if len(nxt): roll.add(nxt.iloc[0])
        f = features(d, nf, sorted(roll))
        for fam, th in itertools.product(FAM, OITH):
            sig = signal(d, f, fam, th)
            for ex, both in itertools.product(EXITS, (False, True)):
                for t0, s, g, cp, risk in run(d, f, sig, r.lot, roll, ex, both):
                    rows.append((r.name, fam, th, ex, both, pd.Timestamp(t0), s, (g - cp) / risk, (g - 2 * cp) / risk))
    T = pd.DataFrame(rows, columns=["name", "fam", "th", "exit", "both", "time", "side", "r1", "r2"])
    T["period"] = np.where(T["time"] < SPLIT, "design", "holdout")
    T["combo"] = T["fam"] + "|oi" + (T["th"] * 100).astype(int).astype(str) + "%|" + T["exit"] + "|" + np.where(T["both"], "long+short", "long")
    res = {}
    for combo, g in T.groupby("combo"):
        d_, ho = g[g["period"] == "design"], g[g["period"] == "holdout"]
        sd = SR.stats(d_["r1"])
        short = (sd.get("trades", 0) >= 80 and sd["exp_r"] >= 0.10 and (sd["pf"] or 0) >= 1.2 and sd["p5"] > 0 and d_["r2"].mean() > 0)
        row = dict(design=sd, design_2x=round(float(d_["r2"].mean()), 3) if len(d_) else None, shortlisted=bool(short))
        if short:
            sh = SR.stats(ho["r1"])
            row.update(holdout=sh, holdout_2x=round(float(ho["r2"].mean()), 3),
                       PASS=bool(sh.get("trades", 0) >= 80 and sh["exp_r"] >= 0.05 and (sh["pf"] or 0) >= 1.1 and ho["r2"].mean() > 0))
        res[combo] = row
    sl = {k: v for k, v in res.items() if v["shortlisted"]}
    print(f"combos {len(res)} · shortlisted on design {len(sl)} · PASS on hold-out {sum(v.get('PASS', False) for v in sl.values())}")
    for k, v in sorted(res.items(), key=lambda kv: -(kv[1]['design'].get('exp_r') or -9))[:15]:
        print(k, v["design"], "2x", v["design_2x"], "| HOLDOUT", v.get("holdout"), v.get("holdout_2x"), "PASS" if v.get("PASS") else "")
    cv = pd.DataFrame(cover)
    print("OI coverage: stocks", len(cv), "median OI days", int(cv["oi_days"].median()), "earliest OI", cv["first_oi"].min())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(dict(results=res, coverage=cover), indent=1, default=str))
    T.to_csv(OUT / "trades.csv.gz", index=False)


if __name__ == "__main__":
    main()

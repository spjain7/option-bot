"""STRAT-SEARCH-003 – can a combination reach 70-80% win rate AND still make money after costs on unseen data?
Win rate is mostly set by target vs stop distance, so the grid varies those explicitly.
Entries: Donchian 20/55 breakout, EMA20/50 cross, RSI(2)<10 / >90 pullback in the 200-EMA trend, Bollinger(20,2) touch in trend,
RSI(14)<25 / >75 reversal (current alert idea). Filters: none / daily trend agree. Exit: target T×ATR, stop S×ATR, max 20 candles.
T ∈ {0.5, 1, 1.5, 2}, S ∈ {1, 2, 3}. Timeframes 1h, 3h, 1d. Same fills/costs/roll rules as STRAT-SEARCH-002.
A combo QUALIFIES only if win ≥ 70% AND expectancy > 0 at 2× costs in BOTH halves (before / after Jul-2024), ≥ 40 trades each.
"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from crude import indicators as I  # noqa
from research.search import strategy_search as SS, combo_search as C  # noqa
from alerts import stats as ST  # noqa

ENT = ["don20", "don55", "ema20_50", "rsi2_trend", "bb_trend", "rsi14_rev"]
FLT = ["none", "daily"]
TG, SL = [0.5, 1.0, 1.5, 2.0], [1.0, 2.0, 3.0]


def extra(df, f):
    c = df["close"]
    f["r2"], f["r14"] = I.rsi(c, 2).values, I.rsi(c, 14).values
    m, sd = c.rolling(20).mean(), c.rolling(20).std()
    f["bbl"], f["bbu"] = (m - 2 * sd).values, (m + 2 * sd).values


def sig(f, e, i):
    c = f["c"]
    if e == "rsi2_trend":
        return 1 if (f["r2"][i] < 10 and c[i] > f["e200"][i]) else -1 if (f["r2"][i] > 90 and c[i] < f["e200"][i]) else 0
    if e == "bb_trend":
        return 1 if (c[i] < f["bbl"][i] and c[i] > f["e200"][i]) else -1 if (c[i] > f["bbu"][i] and c[i] < f["e200"][i]) else 0
    if e == "rsi14_rev":
        return 1 if (f["r14"][i] < 25 and c[i] > f["h"][i - 1]) else -1 if (f["r14"][i] > 75 and c[i] < f["l"][i - 1]) else 0
    return C.entry_sig(f, e, i)


def run(f, swd, nx, e, flt, tg, sl, cost):
    o, h, l, c, a = f["o"], f["h"], f["l"], f["c"], f["atr"]
    out, pos = [], None
    for i in range(210, len(c) - 1):
        if pos is not None:
            s, e0, st, tp, risk, k0 = pos
            px = None
            if (o[i] <= st) if s > 0 else (o[i] >= st):
                px = o[i]
            elif (l[i] <= st) if s > 0 else (h[i] >= st):
                px = st
            elif (h[i] >= tp) if s > 0 else (l[i] <= tp):
                px = tp
            elif nx[i] or i - k0 >= 20:
                px = c[i] if nx[i] else o[i + 1]
            if px is not None:
                out.append((f["t"][k0], s * (px - e0), cost[k0], risk))
                pos = None
            continue
        if swd[i] or nx[i] or not a[i] > 0:
            continue
        s = sig(f, e, i)
        if s == 0 or (flt == "daily" and f["dtr"][i] != s):
            continue
        e0 = o[i + 1]
        pos = (s, e0, e0 - s * sl * a[i], e0 + s * tg * a[i], sl * a[i], i + 1)
    return out


def main():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR")
        sw = SS.switch_days(name, exch, h)
        for tf, df in (("1h", h), ("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True)
            f = C.features(df, h); extra(df, f)
            day = f["day"]; swd = np.array([pd.Timestamp(x) in sw for x in day])
            nx = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in f["c"]])
            for e, flt, tg, sl in itertools.product(ENT, FLT, TG, SL):
                for t0, g, cp, risk in run(f, swd, nx, e, flt, tg, sl, cost):
                    rows.append((name, tf, e, flt, tg, sl, t0, g, cp, risk))
        print(name, "done", flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "entry", "filter", "tg", "sl", "time", "gross", "cost", "risk"])
    T["time"] = pd.to_datetime(T["time"])
    T["r1"] = (T["gross"] - T["cost"]) / T["risk"]; T["r2"] = (T["gross"] - 2 * T["cost"]) / T["risk"]
    T["win"] = T["gross"] - T["cost"] > 0
    T["half"] = np.where(T["time"] < pd.Timestamp("2024-07-01"), "A", "B")
    T["combo"] = T["tf"] + "|" + T["entry"] + "|" + T["filter"] + "|T" + T["tg"].astype(str) + "|S" + T["sl"].astype(str)
    g = T.groupby(["combo", "half"]).agg(n=("r1", "size"), win=("win", "mean"), e1=("r1", "mean"), e2=("r2", "mean")).unstack()
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    g = g.dropna()
    g["win_all"] = T.groupby("combo")["win"].mean()
    g["e1_all"] = T.groupby("combo")["r1"].mean()
    out = Path(ROOT / "research/search/results_003"); out.mkdir(parents=True, exist_ok=True)
    g.round(3).to_csv(out / "combos.csv")
    big = g[(g["n_A"] >= 40) & (g["n_B"] >= 40)]
    hi = big[(big["win_A"] >= 0.7) & (big["win_B"] >= 0.7)]
    q = hi[(hi["e2_A"] > 0) & (hi["e2_B"] > 0)]
    print("combos with ≥40 trades in both halves:", len(big))
    print("win ≥70% in both halves:", len(hi), " of which profitable at 2× costs in both:", len(q))
    print("\nTop win-rate combos (both halves ≥40 trades):")
    print(big.sort_values("win_all", ascending=False).head(15)[["n_A", "n_B", "win_A", "win_B", "e1_A", "e1_B", "e2_A", "e2_B"]].round(3).to_string())
    print("\nBest win-rate among combos profitable at 2× costs in BOTH halves:")
    pp = big[(big["e2_A"] > 0) & (big["e2_B"] > 0)]
    print(pp.sort_values("win_all", ascending=False).head(15)[["n_A", "n_B", "win_A", "win_B", "e1_A", "e1_B", "e2_A", "e2_B"]].round(3).to_string())
    # relationship between win rate and expectancy
    b = pd.cut(big["win_all"], [0, .3, .4, .5, .6, .7, .8, 1])
    print("\nWin-rate band vs average expectancy (1× costs):")
    print(big.groupby(b, observed=True)["e1_all"].agg(["count", "mean"]).round(3).to_string())
    (out / "summary.json").write_text(json.dumps(dict(eligible=len(big), win70_both=len(hi), win70_and_profitable=len(q),
                                                      qualifying=q.round(3).reset_index().to_dict("records")), indent=1, default=str))


if __name__ == "__main__":
    main()

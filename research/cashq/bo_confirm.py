"""Which confirmations make the cash breakout calls more reliable? (owner 18-Nov-2026: "we need more sure-shot calls").
Takes every call of results/nse_bo_trades.json (6 setups, 2005-26) and the point-in-time daily features on the signal day:
  rs126     6-month return percentile among liquid stocks          adx      ADX(14) daily
  ext200    close / EMA200 − 1 (how extended)                      vol_pct  ATR(14) / close (volatility)
  ret20     20-day return before the signal (already ran?)         breadth  share of liquid stocks above EMA50
  mkt       top-100 index above its 200-day average                volx     daily volume / 20-day average
  wk_ath    the daily close is also a weekly all-time high (confluence)   to_cr  60-day median turnover (₹ cr)
For each setup, every single filter and pair of filters (terciles / thresholds) is scored by the win rate in 2005-14,
2015-19 and 2020-26; a confirmation counts only if it raises the win rate in ALL THREE periods and keeps the average
P&L positive with >= 20 calls per period.
python -m research.cashq.bo_confirm -> results/bo_confirm.csv"""
import itertools
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D, ind as I  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"


def main():
    T = pd.DataFrame(json.loads((OUT / "nse_bo_trades.json").read_text())["rows"])
    T = T[T.status == "closed"].copy()
    W = D.daily_panel()
    c, h, l, v = (W[x].astype("float64") for x in ("close", "high", "low", "volume")); e = W["elig"].fillna(False)
    sym = W["symbol"]; key_of = {s: k for k, s in sym.items()}
    ema50 = c.ewm(span=50, adjust=False, min_periods=50).mean(); ema200 = c.ewm(span=200, adjust=False, min_periods=200).mean()
    F = {"rs126": (c / c.shift(126) - 1).where(e).rank(axis=1, pct=True), "adx": I.adx(h, l, c, 14), "ext200": c / ema200 - 1,
         "vol_pct": I.atr(h, l, c, 14) / c, "ret20": c / c.shift(20) - 1, "volx": v / v.rolling(20).mean().shift(1),
         "to_cr": (c * v).rolling(60, min_periods=40).median().shift(1) / 1e7}
    br = ((c > ema50) & e).sum(axis=1) / e.sum(axis=1).replace(0, np.nan)
    mk = W["market"]["close"]; mkt = (mk > mk.rolling(200).mean()).reindex(c.index)
    g = c.index.to_period("W-FRI"); wmax = c.groupby(g).transform("max"); wk_ath = (c >= c.cummax()) & (c == wmax)
    idx = c.index
    rows = []
    for _, r in T.iterrows():
        k = key_of.get(r.symbol); d = pd.Timestamp(r.signal_date)
        if k is None or d not in idx:
            rows.append({}); continue
        i = idx.get_loc(d)
        x = {n: float(F[n][k].iloc[i]) for n in F}
        x.update(breadth=float(br.iloc[i]), mkt=bool(mkt.iloc[i]), wk_ath=bool(wk_ath[k].iloc[i]))
        rows.append(x)
    X = pd.concat([T.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    X["win"] = X.pnl_100 > 0
    X.to_csv(OUT / "bo_confirm_trades.csv.gz", index=False)
    # candidate filters (thresholds fixed in advance, not fitted)
    FL = {"RS>=0.80": X.rs126 >= .80, "RS>=0.90": X.rs126 >= .90, "ADX>=25": X.adx >= 25, "ADX>=30": X.adx >= 30,
          "not extended (ext200<=30%)": X.ext200 <= .30, "not extended (ext200<=20%)": X.ext200 <= .20,
          "low volatility (ATR%<=3%)": X.vol_pct <= .03, "calm (ATR%<=2.5%)": X.vol_pct <= .025,
          "not run up (20d ret<=10%)": X.ret20 <= .10, "not run up (20d ret<=5%)": X.ret20 <= .05,
          "breadth>=55%": X.breadth >= .55, "market up": X.mkt == True, "weekly ATH same day": X.wk_ath == True,
          "volume>=1.5x": X.volx >= 1.5, "large (turnover>=100cr)": X.to_cr >= 100}
    out = []
    for sid, G in X.groupby("setup_id"):
        base = {p: G[G.period == p].win.mean() for p in ("2005-14", "2015-19", "2020-26")}
        for combo in [(f,) for f in FL] + list(itertools.combinations(FL, 2)):
            m = np.ones(len(X), bool)
            for f in combo:
                m &= FL[f].fillna(False).values
            S = X[m & (X.setup_id == sid).values]
            row = dict(setup=sid, confirm=" + ".join(combo), calls=len(S), win=round(100 * S.win.mean(), 1) if len(S) else None,
                       avg_pct=round(S.pnl_pct.mean(), 2) if len(S) else None, base_win=round(100 * G.win.mean(), 1))
            ok = True
            for p in ("2005-14", "2015-19", "2020-26"):
                s = S[S.period == p]
                row[f"{p}_n"] = len(s); row[f"{p}_win"] = round(100 * s.win.mean(), 1) if len(s) else None
                row[f"{p}_avg"] = round(s.pnl_pct.mean(), 2) if len(s) else None
                ok &= len(s) >= 20 and s.win.mean() > base[p] and s.pnl_pct.mean() > 0
            r24 = S[S.year >= 2024]; row["2024_26_n"] = len(r24); row["2024_26_win"] = round(100 * r24.win.mean(), 1) if len(r24) else None
            row["2024_26_avg"] = round(r24.pnl_pct.mean(), 2) if len(r24) else None
            row["better_in_all_3"] = ok
            row["min_period_win"] = min([row[f"{p}_win"] or 0 for p in ("2005-14", "2015-19", "2020-26")])
            out.append(row)
    L = pd.DataFrame(out); L.to_csv(OUT / "bo_confirm.csv", index=False)
    pd.set_option("display.width", 270); pd.set_option("display.max_rows", 200)
    cols = ["setup", "confirm", "calls", "base_win", "win", "avg_pct", "2005-14_win", "2015-19_win", "2020-26_win", "2020-26_n", "2024_26_n", "2024_26_win", "2024_26_avg"]
    ok = L[L.better_in_all_3].sort_values("min_period_win", ascending=False)
    print("confirmations that raise the win rate in all 3 periods:", len(ok), "of", len(L))
    print(ok.groupby("setup").head(6)[cols].to_string(index=False))


if __name__ == "__main__":
    main()

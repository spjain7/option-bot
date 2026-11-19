"""RSIREV – RSI REVERSAL strategies separated from RSI CONTINUATION strategies (owner 11-Nov). Research only.
Ten pre-defined strategies, each labelled, BUY and SELL kept apart, run separately for MCX, NSE stock futures, NSE index
futures and NSE cash (cash = BUY only: delivery cannot be shorted). An RSI extreme alone is tested (S1, S2) only to show
the difference between an EXTREME READING and a CONFIRMED reversal – it is not assumed to be a signal.

  S1  REVERSAL BUY      RSI(14) enters <= 25 (first bar of the oversold reading)                    – extreme only
  S2  REVERSAL SELL     RSI enters >= 75                                                            – extreme only
  S3  REVERSAL BUY      RSI crosses back ABOVE 25 after being <= 25                                 – confirmation
  S4  REVERSAL SELL     RSI crosses back BELOW 75 after being >= 75                                 – confirmation
  S5  REVERSAL BUY      regular bullish RSI divergence, earlier pivot RSI <= 30 (near 25), known K bars after the low
  S6  REVERSAL SELL     regular bearish RSI divergence, earlier pivot RSI >= 70 (near 75)
  S7  REVERSAL BUY      RSI <= 25 within the last 3 bars + bullish reversal candle (engulfing / hammer) + volume >= 1.5x
  S8  REVERSAL SELL     RSI >= 75 within the last 3 bars + bearish reversal candle (engulfing / shooting star) + volume >= 1.5x
  S9  CONTINUATION SELL RSI <= 25 within the last 10 bars + close below the prior 5-bar low + bearish candle (breakdown)
  S10 CONTINUATION BUY  RSI >= 75 + ADX(14) >= 25 + close > EMA50 + close above the prior 20-bar high (trend breakout)
Each factor is varied independently on a full grid (results per cell are kept, nothing is dropped):
  entry   next_open (next bar's open) · confirm (a later close beyond the signal bar's high / low within 2 bars, then the
          next open)
  stop    structure (5-bar extreme + 0.1 ATR, 0.5–3 ATR) · atr (1.5 ATR) · candle (signal bar's extreme + 0.1 ATR, 0.3–3 ATR)
  target  1R · 2R · 3R
  regime  (at the decision bar) all · trend_up (close > EMA200 and EMA50 > EMA200) · trend_down (mirror) · range (ADX < 20)
Costs and execution as in research/rsidiv (real MCX costs; futures STT schedule + slippage; cash delivery 0.393 %).
Gate: profit and PF >= 1.2 in each period, >= 30 trades each and >= 100 in total; BH-FDR 10 % and Holm 5 % per market.
python -m research.rsirev.run [mcx|stockfut|index|cash]   ->  research/rsirev/results/<market>_grid.csv"""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)
LABEL = {"S1": "REVERSAL BUY", "S2": "REVERSAL SELL", "S3": "REVERSAL BUY", "S4": "REVERSAL SELL", "S5": "REVERSAL BUY", "S6": "REVERSAL SELL",
         "S7": "REVERSAL BUY", "S8": "REVERSAL SELL", "S9": "CONTINUATION SELL", "S10": "CONTINUATION BUY"}
SIDE = {k: (1 if v.endswith("BUY") else -1) for k, v in LABEL.items()}
DESC = {"S1": "RSI enters <= 25 (extreme only)", "S2": "RSI enters >= 75 (extreme only)", "S3": "RSI crosses back above 25",
        "S4": "RSI crosses back below 75", "S5": "bullish RSI divergence, earlier pivot RSI <= 30", "S6": "bearish RSI divergence, earlier pivot RSI >= 70",
        "S7": "RSI <= 25 (3 bars) + bullish reversal candle + volume 1.5x", "S8": "RSI >= 75 (3 bars) + bearish reversal candle + volume 1.5x",
        "S9": "RSI <= 25 (10 bars) + close < prior 5-bar low + bearish candle", "S10": "RSI >= 75 + ADX >= 25 + close > EMA50 + 20-bar high breakout"}
STOPS = ("structure", "atr", "candle")
REGIMES = ("all", "trend_up", "trend_down", "range")


def adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = c.shift(1); tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    atr = pd.Series(E.wilder(tr.values, n)); pdi = 100 * pd.Series(E.wilder(pdm, n)) / atr; mdi = 100 * pd.Series(E.wilder(mdm, n)) / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pd.Series(E.wilder(dx.fillna(0).values, n)), atr


def strategies(b, K):
    o, h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("open", "high", "low", "close", "volume"))
    n = len(c); r = E.rsi_of(c)
    os_, ob = r <= 25, r >= 75
    body, rng = (c - o).abs(), (h - l).replace(0, np.nan); lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    bull = ((c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1))) | ((lw >= 2 * body) & (uw <= 0.3 * rng))
    bear = ((c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))) | ((uw >= 2 * body) & (lw <= 0.3 * rng))
    vol15 = v >= 1.5 * v.rolling(20).mean().shift(1)
    ad, atr = adx(h, l, c)
    e50, e200 = c.ewm(span=50, adjust=False).mean(), c.ewm(span=200, adjust=False).mean()
    D = E.divergences(h, l, {"rsi": r}, K)
    s = {"S1": os_ & ~os_.shift(1, fill_value=False), "S2": ob & ~ob.shift(1, fill_value=False),
         "S3": (r > 25) & (r.shift(1) <= 25), "S4": (r < 75) & (r.shift(1) >= 75),
         "S5": pd.Series(D["rsi", "regular", 1] & (D["_rsi_at_prev", 1] <= 30)),
         "S6": pd.Series(D["rsi", "regular", -1] & (D["_rsi_at_prev", -1] >= 70)),
         "S7": (os_.rolling(3).max() > 0) & bull & vol15, "S8": (ob.rolling(3).max() > 0) & bear & vol15,
         "S9": (os_.rolling(10).max() > 0) & (c < l.shift(1).rolling(5).min()) & (c < o),
         "S10": ob & (ad >= 25) & (c > e50) & (c > h.shift(1).rolling(20).max())}
    s = {k: x.fillna(False).astype(bool).values for k, x in s.items()}
    reg = {"all": np.ones(n, bool), "trend_up": ((c > e200) & (e50 > e200)).values, "trend_down": ((c < e200) & (e50 < e200)).values,
           "range": (ad < 20).fillna(False).values}
    lo5, hi5 = l.rolling(5).min(), h.rolling(5).max()
    risk = {"structure": {1: (c - lo5 + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values, -1: (hi5 - c + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values},
            "atr": {1: (1.5 * atr).values, -1: (1.5 * atr).values},
            "candle": {1: (c - l + 0.1 * atr).clip(lower=0.3 * atr, upper=3 * atr).values, -1: (h - c + 0.1 * atr).clip(lower=0.3 * atr, upper=3 * atr).values}}
    # confirmation: a later close beyond the SIGNAL bar's high (BUY) / low (SELL) within 2 bars -> decision on that bar
    conf = {}
    for k, x in s.items():
        z = np.zeros(n, bool); sd = SIDE[k]
        for i in np.where(x)[0]:
            for j in (i + 1, i + 2):
                if j < n and ((sd > 0 and c.iloc[j] > h.iloc[i]) or (sd < 0 and c.iloc[j] < l.iloc[i])):
                    z[j] = True; break
        conf[k] = z
    return s, conf, reg, risk


def build(frames, K, sides_ok=(1, -1)):
    """frames: list of dict(b=bars, live=bool array, costf, expid, grp, name) -> {stop: Pool}"""
    pools = {st: E.Pool() for st in STOPS}
    for f in frames:
        b = f["b"].reset_index(drop=True)
        s, conf, reg, risk = strategies(b, K)
        live = np.asarray(f["live"], bool)
        S = {}
        for k in s:
            if SIDE[k] not in sides_ok:
                continue
            for entry, arr in (("next_open", s[k]), ("confirm", conf[k])):
                for rg, m in reg.items():
                    S[(k, entry, rg, SIDE[k])] = arr & m & live
        for st in STOPS:
            pools[st].add(b, S, risk[st], f["grp"], f["costf"], f["expid"], f["name"])
    return {st: p.freeze() for st, p in pools.items()}


def evaluate(pools, cuts, hold, tf, market, sides=(1, -1)):
    rows = []
    grid = [(k, en, rg, SIDE[k]) for k in LABEL if SIDE[k] in sides for en in ("next_open", "confirm") for rg in REGIMES]
    for st, P in pools.items():
        for key in grid:
            for R in E.RS:
                T = P.run(key, R, hold) if key in P.idx else pd.DataFrame(columns=["netR"])
                if len(T) < 10:
                    rows.append(dict(market=market, tf=tf, strategy=key[0], label=LABEL[key[0]], rule=DESC[key[0]], entry=key[1], regime=key[2],
                                     stop=st, target_R=R, all_n=len(T), PASS=False)); continue
                rw = E.row(key, T, cuts)
                rw.update(market=market, tf=tf, strategy=key[0], label=LABEL[key[0]], rule=DESC[key[0]], entry=key[1], regime=key[2], stop=st, target_R=R,
                          delay_bars=(E.K_BY_TF.get(tf, 3) if key[0] in ("S5", "S6") else 0))
                rows.append(rw)
    L = pd.DataFrame(rows)
    ok = L.t_day.notna() if "t_day" in L else pd.Series(False, index=L.index)
    L["p_day"] = np.nan; L["FDR10"] = False; L["HOLM5"] = False
    if ok.any():
        p = E.pvals(L.loc[ok, "t_day"].values); L.loc[ok, "p_day"] = p; L.loc[ok, "FDR10"] = E.bh(p); L.loc[ok, "HOLM5"] = E.holm(p)
    return L


# ───────────────────────── market loaders (same data preparation as research/rsidiv) ─────────────────────────
def mcx(tf):
    from research.program import mcx_disc as MD
    from research.mcxhw.search import bars
    out = []
    for g, name in enumerate(MD.NAMES):
        d5 = MD.LM.load(name, "FIVE_MINUTE"); b = bars(d5, {"1h": 60, "3h": 180, "1d": 1440}[tf])
        cf = MD.real_cost(name, float(d5.close.iloc[-1])) / float(d5.close.iloc[-1])
        out.append(dict(b=b, live=np.ones(len(b), bool), costf=np.full(len(b), cf), expid=np.zeros(len(b), np.int64),
                        grp=g * 10000 + np.cumsum(b["sw"].fillna(False).astype(bool).values), name=name))
    return out


def stockfut(tf):
    import pickle
    from research.rsidiv import stockfut as SF
    A = pickle.loads(SF.CM_PKL.read_bytes()); F = SF.fut_daily(SF.fut_rows("STK"))
    sk = pd.concat([pd.DataFrame(dict(date=a["time"], symbol=a["symbol"].astype(str), key=k)) for k, a in A.items()], ignore_index=True)
    F = F.merge(sk, on=["date", "symbol"], how="inner"); out = []
    for g, (key, f) in enumerate(F.groupby("key")):
        a = A[key].copy(); a["time"] = pd.to_datetime(a["time"]); a = a[a["time"] >= "2016-01-01"].reset_index(drop=True)
        j = a.set_index("time"); f = f.set_index("date")
        to60 = j["value"].rolling(60, min_periods=40).median().shift(1)
        live = j.index.isin(f.index) & (to60 >= 25e7).values & (j["close"] >= 50).values
        b = a[["time", "open", "high", "low", "close", "volume"]].copy(); b["live"] = live; b["exp"] = f["expiry"].reindex(j.index).values
        if tf == "1w":
            gg = b.set_index("time").resample("W-FRI")
            b = pd.DataFrame(dict(open=gg["open"].first(), high=gg["high"].max(), low=gg["low"].min(), close=gg["close"].last(), volume=gg["volume"].sum(),
                                  live=gg["live"].last(), exp=gg["exp"].last())).dropna(subset=["close"]).reset_index()
        if len(b) < 300 or not b["live"].astype(bool).any():
            continue
        e = pd.Series(b["exp"]).astype("datetime64[ns]")
        expid = np.where(e.notna(), e.values.astype("datetime64[D]").astype(np.int64), -1)
        out.append(dict(b=b, live=b["live"].astype(bool).values, costf=SF.fut_cost(b["time"].values), expid=expid, grp=g, name=str(a["symbol"].iloc[-1])))
    return out


def index(tf):
    from research.rsidiv import index as IX, stockfut as SF
    X = IX.idx_rows(); out = []
    for g, name in enumerate(IX.NAMES):
        d, x = IX.daily(X, name)
        if tf == "1d":
            b = d.reset_index(drop=True); expid = b["expiry"].values.astype("datetime64[D]").astype(np.int64)
            live = (b["time"] >= "2018-03-01").values; grp = np.full(len(b), g)
        else:
            hh = IX.hourly(name, x)
            if hh is None or len(hh) < 500:
                continue
            b = hh.reset_index(drop=True); expid = pd.to_datetime(b["contract"]).values.astype("datetime64[D]").astype(np.int64)
            live = np.ones(len(b), bool); grp = g * 100000 + (expid - expid.min())
        out.append(dict(b=b, live=live, costf=SF.fut_cost(b["time"].values, slip=0.0001, notional=1.5e6), expid=expid, grp=grp, name=name))
    return out


def cash(tf):
    from research.cashq import data as D
    W = D.daily_panel()
    if tf == "1w":
        W = D.weekly(W)
    idx = W["close"].index; out = []
    for g, k in enumerate(W["close"].columns):
        cl = W["close"][k]; ok = cl.notna().values
        if ok.sum() < (60 if tf == "1w" else 300) or not W["elig"][k].fillna(False).astype(bool).any():
            continue
        b = pd.DataFrame(dict(time=idx[ok], **{f: W[f][k].values[ok] for f in ("open", "high", "low", "close", "volume")}))
        for col in ("open", "high", "low"):
            b[col] = b[col].where(b[col] > 0).fillna(b["close"])
        out.append(dict(b=b, live=W["elig"][k].fillna(False).astype(bool).values[ok], costf=np.full(len(b), 0.00393),
                        expid=np.zeros(len(b), np.int64), grp=g, name=str(W["symbol"][k])))
    return out


MARKETS = {
    "mcx": (mcx, (("1h", 45), ("3h", 40), ("1d", 15)), {"*": [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]}, (1, -1), "MCX"),
    "stockfut": (stockfut, (("1d", 15), ("1w", 10)), {"*": [("DEV", "2018-01-01"), ("VAL", "2022-01-01"), ("OOS", "2024-01-01")]}, (1, -1), "NSE_STOCK_FUT"),
    "index": (index, (("1d", 15), ("1h", 21)), {"1d": [("DEV", "2018-01-01"), ("VAL", "2022-01-01"), ("OOS", "2024-01-01")],
                                                 "1h": [("DEV", "2022-07-01"), ("VAL", "2024-07-01"), ("OOS", "2025-07-01")]}, (1, -1), "NSE_INDEX_FUT"),
    "cash": (cash, (("1d", 15), ("1w", 10)), {"*": [("DEV", "2005-01-01"), ("VAL", "2015-01-01"), ("OOS", "2020-01-01")]}, (1,), "NSE_CASH"),
}


def main(which):
    t0 = time.time(); load, tfs, cuts, sides, mk = MARKETS[which]; Ls = []
    for tf, hold in tfs:
        frames = load(tf)
        pools = build(frames, E.K_BY_TF.get(tf, 3), sides)
        Ls.append(evaluate(pools, cuts.get(tf, cuts.get("*")), hold, tf, mk, sides))
        del pools, frames
        print(f"{which} {tf}: {len(Ls[-1])} cells · PASS {int(Ls[-1].PASS.sum())} · {time.time() - t0:.0f}s", flush=True)
    L = pd.concat(Ls, ignore_index=True)
    L.to_csv(OUT / f"{which}_grid.csv", index=False)
    if which == "cash":
        for k in ("S2", "S4", "S6", "S8", "S9"):
            print(f"{k} {LABEL[k]}: not tested in cash – a delivery position cannot be shorted")


if __name__ == "__main__":
    for w in (sys.argv[1:] or list(MARKETS)):
        main(w)

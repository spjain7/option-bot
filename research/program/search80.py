"""SEARCH-80 (28-Oct-2026) – owner's goal: a futures BUY setup with ≥ 80 % winning trades, for MCX, stocks and indices.
Research only. Pre-declared before running: 24 BUY setups × 7 exits × 2 regime settings = 336 variants per dataset.

Setups (all known at the signal bar's close; entry = next bar open, live 0.5-ATR entry-zone check):
  trend      T1 live 20-bar breakout · T2 EMA9×EMA21 · T3 MACD cross · T4 Supertrend flip · T5 Donchian-55 breakout ·
             T6 ADX>25 resumption over EMA20 · T7 Bollinger squeeze breakout · T8 inside-bar breakout · T9 NR7 breakout
  pullback   M1 RSI(2)<10 · M2 RSI(2)<5 · M3 3 lower closes · M4 close ≤ lower Bollinger · M5 Williams %R<−90 ·
  (uptrend:  M6 Stochastic cross <20 · M7 pull-back to EMA20 in ADX>25 trend · M8 2-day RSI(2) sum<35 · M9 10-day low ·
  close>EMA200) M10 gap-down reversal
  patterns   P1 bullish engulfing after a 3-day dip · P2 hammer at a 10-day low · P3 morning star · P4 piercing line
  volume/OI  V1 dip with falling OI (long unwinding) · V2 volume dry-up dip (3 lower closes on < 0.8× volume)
Exits: E1 target 0.5R / SL 2 ATR · E2 0.3R / 1.5 ATR · E3 0.5R / 3 ATR · E4 1R / 2 ATR · E5 exit when close > SMA5 ·
       E6 exit at the first profitable close · E7 exit when close > previous high   (E5–E7: SL 3 ATR, exit at the NEXT open;
       all: max 10 bars, stop checked before target inside a bar, gap through stop fills at the open, roll exit, live stop cap)
Regime: R0 none · R1 market up (stocks: NIFTY > EMA200 yesterday; index / MCX: own EMA50 > EMA200)
Gate (each of train / validation / test separately): win ≥ 80 %, net expectancy at 2× costs > 0, PF ≥ 1.2,
n ≥ 30 / 15 / 15; plus ≥ 60 % of instruments positive in the test period (multi-instrument datasets).
"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H  # noqa: E402
from research.search import strategy_search as SS, stock_oi_buy_run as RN, stock_search as SR  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
SPL = {"angel": ("2024-07-01", "2025-07-01"), "stocks": ("2024-07-01", "2025-07-01"), "nseidx": ("2019-01-01", "2022-01-01"),
       "proxy": ("2019-01-01", "2022-01-01")}
EXITS = {"E1 0.5R/2ATR": ("t", 0.5, 2.0), "E2 0.3R/1.5ATR": ("t", 0.3, 1.5), "E3 0.5R/3ATR": ("t", 0.5, 3.0), "E4 1R/2ATR": ("t", 1.0, 2.0),
         "E5 close>SMA5": ("sma5", None, 3.0), "E6 first profitable close": ("prof", None, 3.0), "E7 close>prev high": ("phigh", None, 3.0)}


# ─────────────── indicators ───────────────
def rsi_n(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def ind(df):
    f = df.copy().reset_index(drop=True)
    o, h, l, c, v = f["open"], f["high"], f["low"], f["close"], f["volume"].astype(float)
    f["atr"] = I.atr(f, 14)
    for n in (9, 20, 21, 50, 200):
        f[f"ema{n}"] = I.ema(c, n)
    f["sma5"] = c.rolling(5).mean()
    f["rsi2"] = rsi_n(c, 2); f["rsi14"] = rsi_n(c, 14)
    ll14, hh14 = l.rolling(14).min(), h.rolling(14).max()
    f["stk"] = 100 * (c - ll14) / (hh14 - ll14).replace(0, np.nan); f["std"] = f["stk"].rolling(3).mean()
    f["wr"] = -100 * (hh14 - c) / (hh14 - ll14).replace(0, np.nan)
    m = I.ema(c, 12) - I.ema(c, 26); f["macd"] = m; f["macds"] = I.ema(m, 9)
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    f["bbu"], f["bbl"] = mid + 2 * sd, mid - 2 * sd
    f["bw"] = (f["bbu"] - f["bbl"]) / mid
    f["bw_q"] = f["bw"].rolling(120, min_periods=60).quantile(0.2)
    up_m, dn_m = h.diff(), -l.diff()
    tr = I.true_range(f)
    pdm = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0); ndm = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr_w = tr.ewm(alpha=1 / 14, adjust=False).mean()
    f["pdi"] = 100 * pd.Series(pdm).ewm(alpha=1 / 14, adjust=False).mean() / atr_w
    f["ndi"] = 100 * pd.Series(ndm).ewm(alpha=1 / 14, adjust=False).mean() / atr_w
    f["adx"] = I.adx(f)
    # supertrend (10, 3)
    a10 = I.atr(f, 10); hl2 = (h + l) / 2
    ub, lb = (hl2 + 3 * a10).values, (hl2 - 3 * a10).values
    cc = c.values; dirn = np.ones(len(f)); fu, fl = ub.copy(), lb.copy()
    for i in range(1, len(f)):
        fu[i] = ub[i] if (np.isnan(fu[i - 1]) or ub[i] < fu[i - 1] or cc[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (np.isnan(fl[i - 1]) or lb[i] > fl[i - 1] or cc[i - 1] < fl[i - 1]) else fl[i - 1]
        dirn[i] = 1 if cc[i] > fu[i - 1] else -1 if cc[i] < fl[i - 1] else dirn[i - 1]
    f["st_dir"] = dirn
    f["hh20"], f["hh55"] = h.shift(1).rolling(20).max(), h.shift(1).rolling(55).max()
    f["ll10"] = l.rolling(10).min()
    f["va"] = v.rolling(20).mean().shift(1); f["volx"] = v / f["va"]
    f["rng"] = h - l
    return f


def setups(f, mkt_up):
    o, h, l, c = f["open"], f["high"], f["low"], f["close"]
    up200 = c > f["ema200"]
    po, pc, ph, pl = o.shift(1), c.shift(1), h.shift(1), l.shift(1)
    down3 = (c < pc) & (pc < c.shift(2)) & (c.shift(2) < c.shift(3))
    body = (c - o).abs(); rng = (h - l).replace(0, np.nan)
    hammer = (np.minimum(o, c) - l >= 2 * body) & (h - np.maximum(o, c) <= 0.3 * rng)
    b2 = c.shift(2) - o.shift(2)
    mstar = (b2 < 0) & (b2.abs() >= 0.6 * rng.shift(2)) & (body.shift(1) <= 0.3 * rng.shift(1)) & (c > o) & (c > (o.shift(2) + c.shift(2)) / 2)
    inside_prev = (ph <= h.shift(2)) & (pl >= l.shift(2))
    nr7 = f["rng"].shift(1) <= f["rng"].shift(1).rolling(7).min()
    doi = f["doi"] if "doi" in f else pd.Series(np.nan, index=f.index)
    S = {
        "T1 20-bar breakout (live)": (c > f["hh20"]) & (f["volx"] > 1.5) & up200,
        "T2 EMA9 x EMA21": (f["ema9"] > f["ema21"]) & (f["ema9"].shift(1) <= f["ema21"].shift(1)) & up200,
        "T3 MACD cross": (f["macd"] > f["macds"]) & (f["macd"].shift(1) <= f["macds"].shift(1)) & up200,
        "T4 Supertrend flip up": (f["st_dir"] == 1) & (f["st_dir"].shift(1) == -1),
        "T5 Donchian-55 breakout": (c > f["hh55"]) & up200,
        "T6 ADX trend resumption": (f["adx"] > 25) & (f["pdi"] > f["ndi"]) & (c > f["ema20"]) & (pc <= f["ema20"].shift(1)),
        "T7 Bollinger squeeze breakout": (f["bw"].shift(1) <= f["bw_q"].shift(1)) & (c > f["bbu"]),
        "T8 inside-bar breakout": inside_prev & (c > ph) & (c > f["ema50"]),
        "T9 NR7 breakout": nr7 & (c > ph) & (c > f["ema50"]),
        "M1 RSI2<10": (f["rsi2"] < 10) & up200,
        "M2 RSI2<5": (f["rsi2"] < 5) & up200,
        "M3 3 lower closes": down3 & up200,
        "M4 lower Bollinger": (c <= f["bbl"]) & up200,
        "M5 Williams %R<-90": (f["wr"] < -90) & up200,
        "M6 Stochastic cross <20": (f["stk"] > f["std"]) & (f["stk"].shift(1) <= f["std"].shift(1)) & (f["stk"].shift(1) < 20) & up200,
        "M7 pullback to EMA20 in trend": (f["adx"] > 25) & (c > f["ema50"]) & (f["ema50"] > f["ema200"]) & (l <= f["ema20"]) & (c > f["ema20"]),
        "M8 2-day RSI2 sum<35": ((f["rsi2"] + f["rsi2"].shift(1)) < 35) & up200,
        "M9 10-day low": (l <= f["ll10"]) & up200,
        "M10 gap-down reversal": (o < pl) & (c > o) & up200,
        "P1 bullish engulfing after dip": (c > o) & (pc < po) & (c >= po) & (o <= pc) & (pc < c.shift(4)) & up200,
        "P2 hammer at 10-day low": hammer & (l <= f["ll10"]) & up200,
        "P3 morning star": mstar & up200,
        "P4 piercing line": (pc < po) & (o < pl) & (c > (po + pc) / 2) & (c < po) & up200,
        "V1 dip with falling OI": (c < c.shift(2)) & (doi < 0) & up200,
        "V2 volume dry-up dip": down3 & (f["volx"] < 0.8) & (f["volx"].shift(1) < 0.8) & (c > f["ema50"]),
    }
    reg = {"R0 any": np.ones(len(f), bool), "R1 market up": np.asarray(mkt_up, bool)}
    return {k: np.asarray(v.fillna(False) if hasattr(v, "fillna") else v, bool) for k, v in S.items()}, reg


# ─────────────── simulation ───────────────
def sim(f, sig, ex, cost, cap, start=210):
    kind, tgt, k = ex
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    sma5 = f["sma5"].values; sw = f["switch"].values
    out, busy, n = [], -1, len(c)
    for i in np.flatnonzero(sig):
        if i < start or i <= busy or i >= n - 2 or sw[i] or sw[i + 1] or not a[i] > 0:
            continue
        mv = (o[i + 1] - c[i]) / a[i]
        if abs(mv) > 0.5:
            out.append((i, "inv", np.nan, np.nan, "")); continue
        e0 = o[i + 1]; R = k * a[i]; st = e0 - R
        if cap and R / e0 * 100 > cap:
            out.append((i, "inv", np.nan, np.nan, "")); continue
        tp = e0 + tgt * R if tgt else None
        px = why = None; j = i + 1
        while j < n:
            if j > i + 1 and sw[j]:
                px, why, j = c[j - 1], "roll", j - 1; break
            if j > i + 1 and o[j] <= st:
                px, why = o[j], "stop"; break
            if j > i + 1 and tp is not None and o[j] >= tp:  # gap through the target fills at the open (VERIFY-EXITS, 29-Oct)
                px, why = o[j], "target"; break
            if l[j] <= st:
                px, why = st, "stop"; break
            if tp is not None and h[j] >= tp:
                px, why = tp, "target"; break
            exit_now = (kind == "sma5" and c[j] > sma5[j]) or (kind == "prof" and c[j] - e0 > cost[i]) or \
                       (kind == "phigh" and c[j] > h[j - 1])
            if exit_now or j - (i + 1) >= 9:
                if j + 1 < n and not sw[j + 1]:
                    px, why, j = o[j + 1], "signal" if exit_now else "time", j + 1
                else:
                    px, why = c[j], "signal" if exit_now else "time"
                break
            j += 1
        if px is None:
            break
        out.append((i, "trade", (px - e0 - cost[i]) / R, (px - e0 - 2 * cost[i]) / R, why))
        busy = j
    return out


# ─────────────── data sets ───────────────
_NIFTY = {}


def nifty_up():
    if not _NIFTY:
        d = H.nseidx("NIFTY")
        up = (d["close"] > I.ema(d["close"], 200)).shift(1)
        _NIFTY["s"] = pd.Series(up.values, index=d["time"].dt.normalize())
    return _NIFTY["s"]


def frames(job):
    ds, name, extra = job
    if ds == "angel":
        fr = H.angel(name, extra)
        out = []
        for tf in ("1d", "3h"):
            df = fr.get(tf)
            if df is not None and len(df) > 300:
                out.append((f"{'MCX' if extra == 'MCX' else 'INDEX'} {tf}", df, H.cost_series(name, df, "angel"),
                            {"1d": 4.0, "3h": 2.5}[tf]))
        return out
    if ds == "nseidx":
        df = H.nseidx(name)
        df["doi"] = np.where(df["switch"], np.nan, df["oi"].pct_change().values)
        return [("INDEX 1d NSE 2011-26", df, H.cost_series(name, df, "nseidx"), 4.0)]
    if ds == "proxy":
        df = H.proxy(name)
        return [("MCX proxy 1d 2005-26", df, H.cost_series(name, df, "proxy"), 4.0)] if df is not None else []
    S = RN.load_stock(name, extra)                       # stocks: corrected prices, validated OI
    if S is None:
        return []
    f0 = S["f"]
    df = pd.DataFrame(dict(time=f0["time"], open=f0["open"], high=f0["high"], low=f0["low"], close=f0["close"],
                           volume=(f0["volx"] * f0["va"]).fillna(0), doi=f0["doi"]))
    sw = np.zeros(len(df), bool); sw[1:] = S["last"][:-1]
    df["switch"] = sw
    return [("STOCKS 1d", df, np.array([S["cost"](p) for p in df["close"].values]), 6.0)]


def one(job):
    ds, name, extra = job
    rows = []
    for seg, df, cost, cap in frames(job):
        f = ind(df)
        if "doi" in df:
            f["doi"] = df["doi"].values
        if ds == "stocks":
            mk = nifty_up().reindex(f["time"].dt.normalize()).ffill().fillna(False).values
        else:
            mk = (f["ema50"] > f["ema200"]).values
        S, R = setups(f, mk)
        for sn, sig in S.items():
            for rn, rm in R.items():
                for en, ex in EXITS.items():
                    for (i, stt, r1, r2, why) in sim(f, sig & rm, ex, cost, cap):
                        rows.append((ds, seg, name, sn, rn, en, f["time"].iat[i], stt, r1, r2, why))
    return rows


def jobs():
    J = [("angel", n, ex) for ex, n in SS.NAMES] + [("nseidx", n, None) for n in ("NIFTY", "BANKNIFTY")] + \
        [("proxy", n, None) for n in ("GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ALUMINIUM")]
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    return J + [("stocks", n, int(l)) for n, l in zip(man["name"], man["lot"])]


def main():
    nifty_up()
    with Pool(8) as p:
        rows = [r for x in p.imap_unordered(one, jobs(), chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["ds", "seg", "name", "setup", "regime", "exit", "time", "status", "r1", "r2", "why"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = "3-test"
    for ds, (a, b) in SPL.items():
        m = T["ds"] == ds
        T.loc[m & (T["time"] < pd.Timestamp(b)), "split"] = "2-valid"
        T.loc[m & (T["time"] < pd.Timestamp(a)), "split"] = "1-train"
    T.to_parquet(OUT / "search80_trades.parquet") if False else T.to_csv(OUT / "search80_trades.csv.gz", index=False)
    tr = T[T["status"] == "trade"]
    g = tr.groupby(["seg", "setup", "regime", "exit", "split"])
    st = g.agg(n=("r1", "size"), win=("r1", lambda x: (x > 0).mean() * 100), exp1=("r1", "mean"), exp2=("r2", "mean"),
               gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum())).reset_index()
    st["pf"] = st["gw"] / st["gl"].replace(0, np.nan)
    W = st.pivot_table(index=["seg", "setup", "regime", "exit"], columns="split", values=["n", "win", "exp1", "exp2", "pf"])
    W.columns = [f"{b[2:]}_{a}" for a, b in W.columns]
    W = W.reset_index()
    nmin = {"train": 30, "valid": 15, "test": 15}

    def gate(r, s, w):
        return (r.get(f"{s}_n", 0) or 0) >= nmin[s] and (r.get(f"{s}_win", 0) or 0) >= w and (r.get(f"{s}_exp2", -1) or -1) > 0 \
            and (r.get(f"{s}_pf", 0) or 0) >= 1.2
    for w in (80, 75, 70):
        W[f"pass{w}"] = [all(gate(r, s, w) for s in ("train", "valid", "test")) for r in W.to_dict("records")]
    # instrument robustness in the test period
    te = tr[tr["split"] == "3-test"].groupby(["seg", "setup", "regime", "exit", "name"])["r2"].mean().reset_index()
    rob = te.groupby(["seg", "setup", "regime", "exit"])["r2"].agg(inst_pos=lambda x: (x > 0).mean() * 100, inst_n="size").reset_index()
    W = W.merge(rob, how="left")
    W.to_csv(OUT / "search80_variants.csv", index=False)
    cols = ["seg", "setup", "regime", "exit", "train_n", "train_win", "train_exp2", "valid_n", "valid_win", "valid_exp2",
            "test_n", "test_win", "test_exp2", "test_pf", "inst_pos", "inst_n"]
    L = ["# SEARCH-80 – futures BUY setups with ≥ 80 % wins (generated)\n",
         f"variants: {len(W)} · pass ≥80 % gate in all 3 periods: {int(W.pass80.sum())} · ≥75 %: {int(W.pass75.sum())} · "
         f"≥70 %: {int(W.pass70.sum())}\n"]
    for w in (80, 75, 70):
        P = W[W[f"pass{w}"]].sort_values(["seg", "test_exp2"], ascending=[True, False])
        L.append(f"\n## Pass the {w} % gate in train, validation AND test\n" + (P[cols].round(3).to_markdown(index=False) if len(P) else "_none_"))
    for seg, G in W.groupby("seg"):
        top = G[G["train_n"] >= 30].sort_values("train_win", ascending=False).head(8)
        L.append(f"\n## {seg}: highest TRAIN win rates (for context – most fail later periods)\n" + top[cols].round(3).to_markdown(index=False))
    (OUT / "search80_tables.md").write_text("\n".join(L))
    print("\n".join(L[:6]))


if __name__ == "__main__":
    main()

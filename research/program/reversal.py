"""REV-001 (28-Oct-2026) – owner's request: RSI reversal futures calls (BUY when RSI < 25, SELL when RSI > 75) confirmed by
reversal candles, volume / relative volume, ADX, OI positioning, VWAP and EMA – on 1-hour and 15-minute candles, for MCX,
index and stock futures. Research only. Everything below is pre-declared before running.

Base signal (bar i, known at its close): RSI(14) crossed into the extreme within the last 3 bars (BUY: min RSI of bars
i-2..i < T_low; SELL: max > T_high), T = 75/25 (owner) and 80/20 (stricter).
Confirmations (each on/off → 2^6 = 64 combinations per side):
  K  reversal candle on bar i – BUY: hammer, bullish engulfing, morning star, piercing; SELL: hanging man / shooting star,
     bearish engulfing, evening star, dark-cloud cover
  V  volume: bar volume ≥ 1.5× its 20-bar average AND ≥ 1.5× the average of the same time-of-day slot (relative volume)
  A  ADX(14) < 25 (no strong trend against the reversal)
  O  OI positioning that fuels the reversal (previous completed day for 1-hour data, last hour for 15-minute data):
     BUY after Short buildup (price ↓ OI ↑: trapped shorts) · SELL after Long buildup (price ↑ OI ↑: trapped longs)
     (MCX has no OI history → combinations with O are not available for MCX)
  W  VWAP: price stretched ≥ 1 ATR beyond the session VWAP (BUY below / SELL above)
  E  EMA: reversal in the direction of the bigger trend (BUY: close > EMA200, SELL: close < EMA200)
Exits: X1 target 0.5R / SL 1.5 ATR · X2 target 0.5R / SL 2 ATR · X3 target 1R / SL 1.5 ATR · X4 back to VWAP or EMA20
       (whichever is nearer, at least 0.3R) / SL 1.5 ATR · max 10 bars · entry next bar open (0.5-ATR entry zone) ·
       stop before target inside a bar · gap fills at the open · exit before a contract switch · costs at 1× / 2×.
Gate per period (1-hour: train < Jul-24 ≤ valid < Jul-25 ≤ test; 15-minute: 2 months only → first / second half, exploratory):
win ≥ 80 % (also reported at 75 / 70 %), expectancy at 2× costs > 0, PF ≥ 1.2, enough trades.
"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H  # noqa: E402
from research.search import strategy_search as SS, stock_oi_buy_run as RN, stock_search as SR, stock_check as SC  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
CONF = ["K", "V", "A", "O", "W", "E"]
EXITS = {"X1 0.5R/1.5ATR": ("t", 0.5, 1.5), "X2 0.5R/2ATR": ("t", 0.5, 2.0), "X3 1R/1.5ATR": ("t", 1.0, 1.5),
         "X4 to VWAP/EMA20": ("mean", None, 1.5)}
THR = {"75/25": (75, 25), "80/20": (80, 20)}


def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def prep(df, oi_label=None):
    """df: time, open, high, low, close, volume, switch [, oi]. oi_label: Series (index = bar) with 'SB'/'LB'/'SC'/'LU' or NaN."""
    f = df.copy().reset_index(drop=True)
    o, h, l, c, v = f["open"], f["high"], f["low"], f["close"], f["volume"].astype(float)
    f["atr"] = I.atr(f, 14); f["rsi"] = rsi(c); f["adx"] = I.adx(f)
    f["ema20"] = I.ema(c, 20); f["ema200"] = I.ema(c, 200)
    day = f["time"].dt.normalize()
    tp = (h + l + c) / 3
    f["vwap"] = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum().replace(0, np.nan)
    f["volx"] = v / v.rolling(20).mean().shift(1)
    slot = f["time"].dt.strftime("%H:%M")
    f["slotx"] = v / v.groupby(slot).transform(lambda x: x.rolling(10, min_periods=5).mean().shift(1))
    body = (c - o).abs(); rng = (h - l).replace(0, np.nan)
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    po, pc, ph, pl = o.shift(1), c.shift(1), h.shift(1), l.shift(1)
    b2 = c.shift(2) - o.shift(2); small1 = body.shift(1) <= 0.3 * rng.shift(1)
    f["k_buy"] = (((lw >= 2 * body) & (uw <= 0.3 * rng)) |                               # hammer
                  ((c > o) & (pc < po) & (c >= po) & (o <= pc)) |                        # bullish engulfing
                  ((b2 < 0) & (b2.abs() >= 0.6 * rng.shift(2)) & small1 & (c > o) & (c > (o.shift(2) + c.shift(2)) / 2)) |
                  ((pc < po) & (o < pl) & (c > (po + pc) / 2) & (c < po)))               # piercing
    f["k_sell"] = ((((lw >= 2 * body) & (uw <= 0.3 * rng)) | ((uw >= 2 * body) & (lw <= 0.3 * rng))) |   # hanging man / shooting star
                   ((c < o) & (pc > po) & (c <= po) & (o >= pc)) |
                   ((b2 > 0) & (b2.abs() >= 0.6 * rng.shift(2)) & small1 & (c < o) & (c < (o.shift(2) + c.shift(2)) / 2)) |
                   ((pc > po) & (o > ph) & (c < (po + pc) / 2) & (c > po)))              # dark cloud
    f["oi_lab"] = oi_label.values if oi_label is not None else np.nan
    return f


def masks(f, side, thr):
    hi, lo = THR[thr]
    r = f["rsi"]
    base = (r.rolling(3).min() < lo) if side > 0 else (r.rolling(3).max() > hi)
    m = {"K": f["k_buy"] if side > 0 else f["k_sell"],
         "V": (f["volx"] >= 1.5) & (f["slotx"] >= 1.5),
         "A": f["adx"] < 25,
         "O": (f["oi_lab"] == ("SB" if side > 0 else "LB")),
         "W": ((f["vwap"] - f["close"]) if side > 0 else (f["close"] - f["vwap"])) >= f["atr"],
         "E": (f["close"] > f["ema200"]) if side > 0 else (f["close"] < f["ema200"])}
    return base.fillna(False).values, {k: np.asarray(v.fillna(False) if hasattr(v, "fillna") else v, bool) for k, v in m.items()}


def sim(f, sig, side, ex, cost, cap):
    kind, tgt, k = ex
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    vw, e20, sw = f["vwap"].values, f["ema20"].values, f["switch"].values
    out, busy, n = [], -1, len(c)
    for i in np.flatnonzero(sig):
        if i < 210 or i <= busy or i >= n - 2 or sw[i] or sw[i + 1] or not a[i] > 0:
            continue
        if abs(o[i + 1] - c[i]) / a[i] > 0.5:
            continue
        e0 = o[i + 1]; R = k * a[i]; st = e0 - side * R
        if cap and R / e0 * 100 > cap:
            continue
        if kind == "mean":
            lv = [x for x in (vw[i], e20[i]) if np.isfinite(x) and side * (x - e0) >= 0.3 * R]
            if not lv:
                continue
            tp = min(lv) if side > 0 else max(lv)
        else:
            tp = e0 + side * tgt * R
        px = None; j = i + 1
        while j < n:
            if j > i + 1 and sw[j]:
                px, j = c[j - 1], j - 1; break
            if j > i + 1 and side * (o[j] - st) <= 0:
                px = o[j]; break
            if j > i + 1 and side * (o[j] - tp) >= 0:  # gap through the target fills at the open (VERIFY-EXITS, 29-Oct)
                px = o[j]; break
            if (l[j] <= st) if side > 0 else (h[j] >= st):
                px = st; break
            if (h[j] >= tp) if side > 0 else (l[j] <= tp):
                px = tp; break
            if j - (i + 1) >= 9:
                px = c[j]; break
            j += 1
        if px is None:
            break
        out.append((i, (side * (px - e0) - cost[i]) / R, (side * (px - e0) - 2 * cost[i]) / R))
        busy = j
    return out


def oi_daily_label(times, daily_px, daily_oi):
    """Label of the PREVIOUS completed day (no look-ahead) mapped to each intraday bar."""
    d = pd.DataFrame(dict(px=daily_px, oi=daily_oi)).sort_index()
    dp, do = d["px"].pct_change(), d["oi"].pct_change()
    lab = pd.Series(np.select([(dp < 0) & (do > 0), (dp > 0) & (do > 0), (dp > 0) & (do < 0), (dp < 0) & (do < 0)],
                              ["SB", "LB", "SC", "LU"], default=None), index=d.index).shift(1)
    return pd.Series(lab.reindex(pd.to_datetime(times).dt.normalize()).values)


# ─────────────── data sets ───────────────
def mcx_index_1h(name, ex):
    h = SS.load(ex, name, "ONE_HOUR")
    if h is None:
        return None
    sw = SS.switch_days(name, ex, h)
    h = h.reset_index(drop=True)
    day = h["time"].dt.normalize()
    h["switch"] = day.isin(sw) & (day != day.shift(1))
    lab = None
    if ex == "NFO":
        d = H.nseidx(name).set_index("time")
        lab = oi_daily_label(h["time"], d["close"], d["oi"])
    cost = np.array([INS.cost_points(name, p, 1.0) for p in h["close"].values])
    return ("MCX 1h" if ex == "MCX" else "INDEX 1h", prep(h, lab), cost, 2.5)


def stock_1h(name, lot):
    S = RN.load_stock(name, lot)
    if S is None:
        return None
    h = pd.concat(S["hourly"].values()).sort_values("time").reset_index(drop=True)
    days = S["f"]["time"].dt.normalize()
    first_after = set(days[np.r_[False, S["last"][:-1]]])
    hd = h["time"].dt.normalize()
    h["switch"] = hd.isin(first_after) & (hd != hd.shift(1))
    f0 = S["f"]
    oi = pd.Series((1 + f0["doi"].fillna(0)).cumprod().values, index=days)   # validated daily OI change -> index level
    oi[f0["doi"].isna().values] = np.nan
    lab = oi_daily_label(h["time"], pd.Series(f0["close"].values, index=days), oi)
    cost = np.array([SC.cost_frac(p, lot) for p in h["close"].values])
    return ("STOCKS 1h", prep(h, lab), cost, 6.0)


def m15(path, name, kind):
    df = pd.read_csv(path, parse_dates=["time"]).sort_values("time").drop_duplicates("time").reset_index(drop=True)
    df["switch"] = False
    lab = None
    if "oi" in df:                                        # last hour: price and OI change over 4 bars (known at the close)
        dp, do = df["close"].pct_change(4), df["oi"].pct_change(4)
        lab = pd.Series(np.select([(dp < 0) & (do > 0), (dp > 0) & (do > 0), (dp > 0) & (do < 0), (dp < 0) & (do < 0)],
                                  ["SB", "LB", "SC", "LU"], default=None))
    if kind == "stock":
        lot = 500
        cost = np.array([SC.cost_frac(p, lot) for p in df["close"].values])
    else:
        nm = name if name in INS.REGISTRY else None
        cost = np.array([INS.cost_points(nm, p, 1.0) for p in df["close"].values]) if nm else df["close"].values * 0.0004
    seg = {"index": "INDEX 15m", "stock": "STOCKS 15m", "mcx": "MCX 15m"}[kind]
    return (seg, prep(df, lab), cost, None)


def one(job):
    kind, a, b = job
    try:
        d = mcx_index_1h(a, b) if kind == "mi" else stock_1h(a, b) if kind == "stk" else m15(a, b, kind)
    except Exception as e:
        print("skip", job, e); return []
    if d is None:
        return []
    seg, f, cost, cap = d
    rows = []
    has_oi = f["oi_lab"].notna().any()
    for thr in THR:
        for side in (1, -1):
            base, M = masks(f, side, thr)
            for r in range(0, 7):
                for combo in itertools.combinations(CONF, r):
                    if "O" in combo and not has_oi:
                        continue
                    sig = base.copy()
                    for cnd in combo:
                        sig &= M[cnd]
                    if not sig.any():
                        continue
                    for en, ex in EXITS.items():
                        for (i, r1, r2) in sim(f, sig, side, ex, cost, cap):
                            rows.append((seg, a if kind in ("mi", "stk") else Path(str(a)).stem[4:], thr,
                                         "BUY" if side > 0 else "SELL", "+".join(combo) or "none", en, f["time"].iat[i], r1, r2))
    return rows


def jobs():
    J = [("mi", n, ex) for ex, n in SS.NAMES]
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    J += [("stk", n, int(l)) for n, l in zip(man["name"], man["lot"])]
    for p in sorted((ROOT / "research/data/obuy").glob("fut_*.csv")):
        nm = p.stem[4:]
        J.append(("index" if nm in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY") else "stock", p, nm))
    for p in sorted((ROOT / "research/data/obuy_mcx").glob("fut_*.csv")):
        J.append(("mcx", p, p.stem[4:]))
    return J


def main():
    with Pool(8) as p:
        rows = [r for x in p.imap_unordered(one, jobs(), chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["seg", "name", "thr", "side", "conf", "exit", "time", "r1", "r2"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    is15 = T["seg"].str.endswith("15m")
    mid15 = T.loc[is15, "time"].quantile(0.5) if is15.any() else None
    T["split"] = np.where(T["time"] < pd.Timestamp("2024-07-01"), "1-train", np.where(T["time"] < pd.Timestamp("2025-07-01"), "2-valid", "3-test"))
    if mid15 is not None:
        T.loc[is15, "split"] = np.where(T.loc[is15, "time"] < mid15, "1-train", "3-test")
    T.to_csv(OUT / "rev_trades.csv.gz", index=False)
    g = T.groupby(["seg", "thr", "side", "conf", "exit", "split"])
    st = g.agg(n=("r1", "size"), win=("r1", lambda x: (x > 0).mean() * 100), exp2=("r2", "mean"),
               gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum())).reset_index()
    st["pf"] = st["gw"] / st["gl"].replace(0, np.nan)
    W = st.pivot_table(index=["seg", "thr", "side", "conf", "exit"], columns="split", values=["n", "win", "exp2", "pf"])
    W.columns = [f"{b[2:]}_{a}" for a, b in W.columns]
    W = W.reset_index()
    for c in ("valid_n", "valid_win", "valid_exp2", "valid_pf"):
        if c not in W:
            W[c] = np.nan
    is15 = W["seg"].str.endswith("15m")

    def gate(r, w):
        sp = ("train", "test") if r["seg"].endswith("15m") else ("train", "valid", "test")
        nmin = {"train": 30, "valid": 15, "test": 15} if not r["seg"].endswith("15m") else {"train": 20, "test": 20}
        return all((r.get(f"{s}_n") or 0) >= nmin[s] and (r.get(f"{s}_win") or 0) >= w and (r.get(f"{s}_exp2") or -1) > 0
                   and (r.get(f"{s}_pf") or 0) >= 1.2 for s in sp)
    for w in (80, 75, 70):
        W[f"pass{w}"] = [gate(r, w) for r in W.to_dict("records")]
    W.to_csv(OUT / "rev_variants.csv", index=False)
    cols = ["seg", "thr", "side", "conf", "exit", "train_n", "train_win", "train_exp2", "valid_n", "valid_win", "valid_exp2",
            "test_n", "test_win", "test_exp2", "test_pf"]
    L = ["# REV-001 – RSI reversal + candle / volume / ADX / OI / VWAP / EMA (generated)\n",
         f"variants: {len(W)} · pass 80 %: {int(W.pass80.sum())} · 75 %: {int(W.pass75.sum())} · 70 %: {int(W.pass70.sum())}\n"]
    for w in (80, 75, 70):
        P = W[W[f"pass{w}"]].sort_values(["seg", "test_exp2"], ascending=[True, False])
        L.append(f"\n## pass {w} % in every period\n" + (P[cols].round(3).to_markdown(index=False) if len(P) else "_none_"))
    for seg, G in W.groupby("seg"):
        G = G[(G["train_n"] >= 20) & (G["test_n"] >= 15)].copy()
        G["minwin"] = G[[c for c in ("train_win", "valid_win", "test_win") if G[c].notna().any()]].min(axis=1)
        L.append(f"\n## {seg}: best lowest-period win rate with exp2 > 0 in every period\n" +
                 G[(G["train_exp2"] > 0) & (G["test_exp2"] > 0) & (G["valid_exp2"].fillna(1) > 0)]
                 .sort_values("minwin", ascending=False).head(10)[cols].round(3).to_markdown(index=False))
    (OUT / "rev_tables.md").write_text("\n".join(L))
    print("\n".join(L[:2]))


if __name__ == "__main__":
    main()

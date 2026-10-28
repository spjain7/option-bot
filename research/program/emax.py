"""EMAX-002 (28-Oct-2026) – EMA crossover futures calls with volume and OI confirmation (owner's request).
Earlier EMA-X-001 (23-Oct, 1-hour only, quick same-day exits) found nothing. This run adds what it did not cover:
15-minute / 3-hour / daily candles, the 50/200 pair, trend-following exits, both sides, long daily histories.

Signal: fast EMA crosses the slow EMA on a closed candle. Pairs: 9/21, 20/50, 50/200 (+ 5/13 on 15m / 1h).
Confirmations (all 8 on/off combinations):
  V  cross candle volume ≥ 1.5× its 20-candle average
  O  OI in the trade direction – BUY: long buildup (price ↑ OI ↑), SELL: short buildup (price ↓ OI ↑).
     Daily candles: same day (known at the close). 1h / 3h: previous completed day. 15m: last hour. MCX: no OI history.
  T  price on the trade side of EMA200 (not used with the 50/200 pair)
Exits: Y1 hold until the opposite crossover (exit next open), safety stop 3 ATR · Y2 stop 2 ATR, target 2R ·
       Y3 trailing stop 3 ATR on closes. Entry next open; stop before target in a bar; gap fills at the open; exit before a
       contract switch; max 120 bars; costs at 1× / 2×.
Periods: Angel / stock data train < Jul-24 ≤ valid < Jul-25 ≤ test; NSE index / proxies train < 2019 ≤ valid < 2022 ≤ test;
15-minute: first / second half (2 months, exploratory). PASS = net expectancy at 2× costs > 0 and PF ≥ 1.2 in EVERY period.
"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, reversal as RV  # noqa: E402
from research.search import strategy_search as SS, stock_oi_buy_run as RN, stock_search as SR, stock_check as SC  # noqa: E402
from research import instruments as INS  # noqa: E402
from alerts import stats as ST  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = ("Y1 opposite cross", "Y2 2ATR stop / 2R", "Y3 trail 3ATR")


def lab_dir(lab):
    return pd.Series(lab).map({"LB": 1, "SB": -1}).fillna(0).values


def three(h):
    out = ST.three_hour_generic(h).reset_index(drop=True)
    out["switch"] = out["time"].dt.normalize().isin(set(h.loc[h["switch"], "time"].dt.normalize())) & \
        (out["time"].dt.normalize() != out["time"].dt.normalize().shift(1))
    return out


def frames(job):
    kind, a, b = job
    res = []
    if kind == "mi":                                          # MCX / index Angel: 1h, 3h, daily
        seg0 = "MCX" if b == "MCX" else "INDEX"
        x = RV.mcx_index_1h(a, b)
        if x is None:
            return []
        f1 = x[1][["time", "open", "high", "low", "close", "volume", "switch"]].copy()
        od = lab_dir(x[1]["oi_lab"]) if b != "MCX" else np.zeros(len(f1))
        c1 = x[2]
        res.append((f"{seg0} 1h", f1, od, c1))
        f3 = three(f1)
        lab3 = RV.oi_daily_label(f3["time"], *(lambda d: (d["close"], d["oi"]))(H.nseidx(a).set_index("time"))) if b != "MCX" else None
        res.append((f"{seg0} 3h", f3, lab_dir(lab3) if lab3 is not None else np.zeros(len(f3)),
                    np.array([INS.cost_points(a, p, 1.0) for p in f3["close"].values])))
        fr = H.angel(a, b)
        d = fr["1d"]
        res.append((f"{seg0} 1d", d, np.zeros(len(d)), H.cost_series(a, d, "angel")))
    elif kind == "nse":                                       # NSE index daily 2011-26 with same-day OI
        d = H.nseidx(a)
        dp, do = d["close"].pct_change(), d["oi"].pct_change()
        od = np.where(d["switch"], 0, np.where((dp > 0) & (do > 0), 1, np.where((dp < 0) & (do > 0), -1, 0)))
        res.append(("INDEX 1d NSE 2011-26", d, od, H.cost_series(a, d, "nseidx")))
    elif kind == "proxy":
        d = H.proxy(a)
        if d is not None:
            res.append(("MCX proxy 1d 2005-26", d, np.zeros(len(d)), H.cost_series(a, d, "proxy")))
    elif kind == "stk":
        S = RN.load_stock(a, b)
        if S is None:
            return []
        f0 = S["f"]
        d = pd.DataFrame(dict(time=f0["time"], open=f0["open"], high=f0["high"], low=f0["low"], close=f0["close"],
                              volume=(f0["volx"] * f0["va"]).fillna(0)))
        sw = np.zeros(len(d), bool); sw[1:] = S["last"][:-1]; d["switch"] = sw
        od = np.where(f0["doi"].isna(), 0, np.where((f0["dp"] > 0) & (f0["doi"] > 0), 1, np.where((f0["dp"] < 0) & (f0["doi"] > 0), -1, 0)))
        cd = np.array([SC.cost_frac(p, b) for p in d["close"].values])
        res.append(("STOCKS 1d", d, od, cd))
        x = RV.stock_1h(a, b)
        if x is not None:
            f1 = x[1][["time", "open", "high", "low", "close", "volume", "switch"]].copy()
            res.append(("STOCKS 1h", f1, lab_dir(x[1]["oi_lab"]), x[2]))
            f3 = three(f1)
            days = f0["time"].dt.normalize()
            oi = pd.Series((1 + f0["doi"].fillna(0)).cumprod().values, index=days); oi[f0["doi"].isna().values] = np.nan
            lab3 = RV.oi_daily_label(f3["time"], pd.Series(f0["close"].values, index=days), oi)
            res.append(("STOCKS 3h", f3, lab_dir(lab3), np.array([SC.cost_frac(p, b) for p in f3["close"].values])))
    else:                                                     # 15-minute files (2 months)
        x = RV.m15(a, b, kind)
        f = x[1][["time", "open", "high", "low", "close", "volume", "switch"]].copy()
        res.append((x[0], f, lab_dir(x[1]["oi_lab"]), x[2]))
    return res


def sim(f, sig, side, exit_, cost, crossdn):
    o, h, l, c, a, sw = (f[x].values for x in ("open", "high", "low", "close", "atr", "switch"))
    out, busy, n = [], -1, len(c)
    for i in np.flatnonzero(sig):
        if i < 210 or i <= busy or i >= n - 2 or sw[i] or sw[i + 1] or not a[i] > 0:
            continue
        e0 = o[i + 1]
        k = 3.0 if exit_ != "Y2 2ATR stop / 2R" else 2.0
        R = k * a[i]; st = e0 - side * R
        tp = e0 + side * 2 * R if exit_ == "Y2 2ATR stop / 2R" else None
        best = e0; px = None; j = i + 1
        while j < n:
            if j > i + 1 and sw[j]:
                px, j = c[j - 1], j - 1; break
            if j > i + 1 and side * (o[j] - st) <= 0:
                px = o[j]; break
            if tp is not None and j > i + 1 and side * (o[j] - tp) >= 0:  # gap through the target fills at the open (VERIFY-EXITS, 29-Oct)
                px = o[j]; break
            if (l[j] <= st) if side > 0 else (h[j] >= st):
                px = st; break
            if tp is not None and ((h[j] >= tp) if side > 0 else (l[j] <= tp)):
                px = tp; break
            if exit_ == "Y1 opposite cross" and crossdn[j]:
                if j + 1 < n and not sw[j + 1]:
                    px, j = o[j + 1], j + 1
                else:
                    px = c[j]
                break
            if exit_ == "Y3 trail 3ATR":
                best = max(best, c[j]) if side > 0 else min(best, c[j])
                ns = best - side * 3 * a[j]
                if side * (ns - st) > 0:
                    st = ns
            if j - (i + 1) >= 120:
                px = c[j]; break
            j += 1
        if px is None:
            break
        out.append((i, (side * (px - e0) - cost[i]) / R, (side * (px - e0) - 2 * cost[i]) / R, j - i))
        busy = j
    return out


def one(job):
    rows = []
    try:
        fr = frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    name = job[1] if job[0] in ("mi", "nse", "proxy", "stk") else job[2]
    for seg, f, odir, cost in fr:
        f = f.reset_index(drop=True)
        if len(f) < 260:
            continue
        f["atr"] = I.atr(f, 14)
        v = f["volume"].astype(float); volx = (v / v.rolling(20).mean().shift(1)).values
        e200 = I.ema(f["close"], 200).values
        pairs = [(9, 21), (20, 50), (50, 200)] + ([(5, 13)] if seg.endswith(("15m", "1h")) else [])
        has_oi = np.any(odir != 0)
        for fa, sl in pairs:
            ef, es = I.ema(f["close"], fa).values, I.ema(f["close"], sl).values
            up = (ef > es) & (np.r_[np.nan, ef[:-1]] <= np.r_[np.nan, es[:-1]])
            dn = (ef < es) & (np.r_[np.nan, ef[:-1]] >= np.r_[np.nan, es[:-1]])
            for side, base, opp in ((1, up, dn), (-1, dn, up)):
                M = {"V": volx >= 1.5, "O": odir == side, "T": (f["close"].values > e200) if side > 0 else (f["close"].values < e200)}
                keys = ["V"] + (["O"] if has_oi else []) + (["T"] if sl != 200 else [])
                for r in range(len(keys) + 1):
                    for combo in itertools.combinations(keys, r):
                        sig = base.copy()
                        for kk in combo:
                            sig &= M[kk]
                        if not sig.any():
                            continue
                        for ex in EXITS:
                            for (i, r1, r2, bars) in sim(f, sig, side, ex, cost, opp):
                                rows.append((seg, name, f"{fa}/{sl}", "BUY" if side > 0 else "SELL", "+".join(combo) or "none", ex,
                                             f["time"].iat[i], r1, r2, bars))
    return rows


def jobs():
    J = [("mi", n, ex) for ex, n in SS.NAMES] + [("nse", n, None) for n in ("NIFTY", "BANKNIFTY")] + \
        [("proxy", n, None) for n in ("GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ALUMINIUM")]
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
    T = pd.DataFrame(rows, columns=["seg", "name", "pair", "side", "conf", "exit", "time", "r1", "r2", "bars"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    long_hist = T["seg"].str.contains("NSE|proxy")
    a = np.where(long_hist, np.datetime64("2019-01-01"), np.datetime64("2024-07-01"))
    b = np.where(long_hist, np.datetime64("2022-01-01"), np.datetime64("2025-07-01"))
    T["split"] = np.where(T["time"].values < a, "1-train", np.where(T["time"].values < b, "2-valid", "3-test"))
    is15 = T["seg"].str.endswith("15m")
    if is15.any():
        mid = T.loc[is15, "time"].quantile(0.5)
        T.loc[is15, "split"] = np.where(T.loc[is15, "time"] < mid, "1-train", "3-test")
    T.to_csv(OUT / "emax_trades.csv.gz", index=False)
    g = T.groupby(["seg", "pair", "side", "conf", "exit", "split"])
    st = g.agg(n=("r1", "size"), win=("r1", lambda x: (x > 0).mean() * 100), exp2=("r2", "mean"),
               gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum())).reset_index()
    st["pf"] = st["gw"] / st["gl"].replace(0, np.nan)
    W = st.pivot_table(index=["seg", "pair", "side", "conf", "exit"], columns="split", values=["n", "win", "exp2", "pf"])
    W.columns = [f"{bb[2:]}_{aa}" for aa, bb in W.columns]
    W = W.reset_index()
    for c in ("valid_n", "valid_win", "valid_exp2", "valid_pf"):
        if c not in W:
            W[c] = np.nan

    def ok(r):
        sp = ("train", "test") if r["seg"].endswith("15m") else ("train", "valid", "test")
        nmin = dict(train=30, valid=15, test=15) if not r["seg"].endswith("15m") else dict(train=15, test=15)
        return all((r.get(f"{s}_n") or 0) >= nmin[s] and (r.get(f"{s}_exp2") or -1) > 0 and (r.get(f"{s}_pf") or 0) >= 1.2 for s in sp)
    W["pass"] = [ok(r) for r in W.to_dict("records")]
    W.to_csv(OUT / "emax_variants.csv", index=False)
    cols = ["seg", "pair", "side", "conf", "exit", "train_n", "train_win", "train_exp2", "valid_n", "valid_win", "valid_exp2",
            "test_n", "test_win", "test_exp2", "test_pf"]
    L = [f"# EMAX-002 – EMA crossover + volume + OI (generated)\n\nvariants {len(W)} · PASS (profitable at 2× costs, PF ≥ 1.2 in "
         f"every period): {int(W['pass'].sum())}\n"]
    P = W[W["pass"]].sort_values(["seg", "test_exp2"], ascending=[True, False])
    L.append(P[cols].round(3).to_markdown(index=False) if len(P) else "_none_")
    base = W[W["conf"] == "none"]
    L.append("\n## Plain crossover (no confirmation) – all periods pooled\n")
    pooled = T[T["conf"] == "none"].groupby(["seg", "pair", "side", "exit"]).agg(
        n=("r1", "size"), win=("r1", lambda x: round((x > 0).mean() * 100, 1)), exp2=("r2", "mean")).round(3).reset_index()
    L.append(pooled.to_markdown(index=False))
    (OUT / "emax_tables.md").write_text("\n".join(L))
    print(L[0])


if __name__ == "__main__":
    main()

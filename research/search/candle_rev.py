"""CANDLE-001 – see REGISTRY_CANDLE.md.  python -m research.search.candle_rev"""
import itertools, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import strategy_search as SS, stock_search as SR, stock_check as SC  # noqa
from alerts.stocks import in_rollover_window  # noqa

SPLIT = pd.Timestamp("2024-07-01")
OUT = ROOT / "research/search/results_candle"
BULL, BEAR = ("hammer", "bull_engulf", "morning_star"), ("hanging_man", "bear_engulf", "evening_star")


def pats(df):
    o, h, l, c = (df[x] for x in ("open", "high", "low", "close"))
    rng = (h - l).replace(0, np.nan); body = (c - o).abs()
    up, lo = h - np.maximum(o, c), np.minimum(o, c) - l
    po, pc = o.shift(1), c.shift(1)
    hamm = (lo >= 2 * body) & (up <= 0.3 * rng)
    small1 = body.shift(1) <= 0.3 * rng.shift(1)
    b2 = c.shift(2) - o.shift(2)
    return {"hammer": hamm, "hanging_man": hamm,
            "bull_engulf": (c > o) & (pc < po) & (c >= po) & (o <= pc),
            "bear_engulf": (c < o) & (pc > po) & (c <= po) & (o >= pc),
            "morning_star": (b2 < 0) & (b2.abs() >= 0.6 * rng.shift(2)) & small1 & (c > o) & (c > (o.shift(2) + c.shift(2)) / 2),
            "evening_star": (b2 > 0) & (b2.abs() >= 0.6 * rng.shift(2)) & small1 & (c < o) & (c < (o.shift(2) + c.shift(2)) / 2)}


def sim(df, sig, conf, stop_kind, tg, cost, swd, maxh=10):
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    a = df["_atr"].values
    n, out, busy = len(df), [], -1
    for i in np.flatnonzero(sig):
        if i < 30 or i <= busy or i >= n - 2:
            continue
        s = int(sig[i])
        if swd[i] or not a[i] > 0:
            continue
        k = i
        if conf:                                              # next candle must close beyond the pattern high / low
            if not ((c[i + 1] > h[i]) if s > 0 else (c[i + 1] < l[i])):
                continue
            k = i + 1
        if k + 1 >= n:
            break
        e0 = o[k + 1]
        lo_, hi_ = l[max(0, i - 2):k + 1].min(), h[max(0, i - 2):k + 1].max()
        st = (lo_ - 0.1 * a[i]) if s > 0 else (hi_ + 0.1 * a[i]) if stop_kind == "PT" else e0 - s * 1.5 * a[i]
        if stop_kind != "PT":
            st = e0 - s * 1.5 * a[i]
        risk = s * (e0 - st)
        if not (0 < risk <= 4 * a[i]):
            continue
        tp = e0 + s * tg * risk
        px, j = None, k + 1
        while j < n:
            if (o[j] <= st) if s > 0 else (o[j] >= st): px = o[j]; break
            if (l[j] <= st) if s > 0 else (h[j] >= st): px = st; break
            if (h[j] >= tp) if s > 0 else (l[j] <= tp): px = tp; break
            if swd[j] or j - k >= maxh: px = c[j]; break
            j += 1
        if px is None: px, j = c[-1], n - 1
        out.append((df["time"].iat[i], s * (px - e0), cost[i]))
        busy = j
    return out


def instruments():
    for n in ("NIFTY", "BANKNIFTY"):
        h = SS.load("NFO", n, "ONE_HOUR"); sw = SS.switch_days(n, "NFO", h)
        yield "INDEX", n, h, sw, (lambda p, nn=n: INS.cost_points(nn, p, 1.0)), INS.REGISTRY[n]["mult"], None
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    for r in man.itertuples():
        f1, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if not f1.exists():
            continue
        h = pd.read_csv(f1, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        sw = {x for x in pd.unique(h["time"].dt.normalize()) if in_rollover_window(pd.Timestamp(x))}
        yield "STOCKS", r.name, h, sw, (lambda p, L=r.lot: SC.cost_frac(p, L)), r.lot, (pd.read_csv(fo) if fo.exists() else None)


def main():
    rows = []
    for uni, name, h, sw, costf, mult, oi in instruments():
        for tf, df in (("1d", SS.daily_from(h)), ("1h", h)):
            df = df.reset_index(drop=True)
            df["_atr"] = I.atr(df, 14).values
            day = df["time"].dt.normalize()
            swd = np.array([pd.Timestamp(x) in sw for x in day])
            cost = np.array([costf(p) for p in df["close"]])
            c = df["close"]; e20 = I.ema(c, 20); r5 = c.pct_change(5)
            dn_ctx = (c < e20) & (r5 < 0); up_ctx = (c > e20) & (r5 > 0)
            v = df["volume"].astype(float); vol = (v > 1.5 * v.rolling(20).mean().shift(1)).values
            a = I.atr(df, 14)
            near_lo = (df["low"] <= df["low"].shift(1).rolling(20).min() + 0.5 * a).values
            near_hi = (df["high"] >= df["high"].shift(1).rolling(20).max() - 0.5 * a).values
            oid = None
            if oi is not None:
                o_ = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last()
                oid = o_.reindex(day).pct_change().values if tf == "1d" else o_.pct_change().shift(1).reindex(day).values
            P = pats(df)
            for pn, pv in P.items():
                bull = pn in BULL
                base = np.where((pv & (dn_ctx if bull else up_ctx)).fillna(False).values, 1 if bull else -1, 0)
                srm = near_lo if bull else near_hi
                F = {"none": base, "vol": np.where(vol, base, 0), "sr": np.where(srm, base, 0), "vol+sr": np.where(vol & srm, base, 0)}
                if oid is not None:
                    om = np.nan_to_num(oid, nan=0) <= -0.01
                    F["oi"] = np.where(om, base, 0); F["oi+vol"] = np.where(om & vol, base, 0); F["oi+sr"] = np.where(om & srm, base, 0)
                for fn, sg in F.items():
                    for conf, sk, tg in itertools.product((False, True), ("PT", "A1.5"), (0.5, 1.0, 2.0)):
                        for t0, g, cp in sim(df, sg, conf, sk, tg, cost, swd):
                            rows.append((uni, tf, name, pn, fn + ("+conf" if conf else ""), sk, tg, t0, (g - cp) * mult, (g - 2 * cp) * mult))
        print(uni, name, flush=True)
    T = pd.DataFrame(rows, columns=["u", "tf", "name", "pat", "filt", "sl", "tg", "time", "rs", "rs2"])
    T["per"] = np.where(T.time < SPLIT, "design", "holdout")
    res = []
    for k, g in T.groupby(["u", "tf", "pat", "filt", "sl", "tg"]):
        D, H = g[g.per == "design"], g[g.per == "holdout"]
        share = (H.groupby("name").rs.mean() > 0).mean() * 100 if len(H) else 0
        mn = 40
        ok = len(D) >= mn and len(H) >= mn and D.rs2.mean() > 0 and H.rs2.mean() > 0 and (share >= 55 or k[0] == "INDEX")
        res.append(dict(zip(["u", "tf", "pat", "filt", "sl", "tg"], k), n_d=len(D), win_d=round((D.rs > 0).mean() * 100, 1) if len(D) else None,
                        rs2_d=round(D.rs2.mean()) if len(D) else None, n_h=len(H), win_h=round((H.rs > 0).mean() * 100, 1) if len(H) else None,
                        rs2_h=round(H.rs2.mean()) if len(H) else None, pos_h=round(share), PASS=ok))
    R = pd.DataFrame(res); OUT.mkdir(parents=True, exist_ok=True); R.to_csv(OUT / "summary.csv", index=False)
    print("tested", len(R), "PASS", int(R.PASS.sum()))
    print(R[R.PASS].sort_values("win_h", ascending=False).head(20).to_string(index=False))
    base = R[(R.filt == "none") & (R.sl == "PT") & (R.tg == 1.0)]
    print("\nplain patterns (no filter, SL beyond pattern, target 1R):\n", base.to_string(index=False))


if __name__ == "__main__":
    main()

"""LIQTL-004 (3-Nov-2026, owner: "get all old data, do back research and find a winning strategy with this [Liquidity Trendline
With Signals], avoid / filter choppy markets").
Data: Angel front-month stitched MCX futures, 5-minute and 3-minute candles (~2022 → Nov-2026), 7 commodities.
Timeframes: 3 (native), 5 (native), 10 / 15 / 30 min (built from 5-min, anchored at 09:00).
Signals: research/program/liqtl.py port (period 5, padding 2). Entry next candle open. Costs 2x the MCX model (INS.cost_points).
Exits:   REV   hold until the opposite signal (the owner's way), flat at 23:20      REV3  same + 3 ATR stop
         TRL   3 ATR trailing stop (chandelier), flat 23:20                        2R    fixed 1 ATR stop / 2R
Choppy-market filters (all known at the signal candle):
         CHOP  Choppiness Index(14) of the signal TF < 50          ADX1H  previous 1-hour ADX(14) ≥ 22
         ER    Kaufman efficiency ratio(20) ≥ 0.30                 DT     daily trend agrees (prev day EMA20 vs EMA50)
         VOL   signal candle volume ≥ 1.5x its 20-candle average   SES    skip signals 09:00-09:15 and after 22:30
         combos DT+ADX1H, DT+VOL, CHOP+VOL, DT+ADX1H+VOL
Periods: 2022-07 → 2024-06 · 2024-07 → 2025-06 · 2025-07 → (the same splits as every study). Robust = positive in all three.
python research/program/liqtl_mcx5.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import liqtl as LT  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

DATA = ROOT / "research/data/angel"
OUT = ROOT / "research/program/results"
NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
EOD = 2320
FILTERS = ["none", "CHOP", "ADX1H", "ER", "DT", "VOL", "SES", "DT+ADX1H", "DT+VOL", "CHOP+VOL", "DT+ADX1H+VOL"]


def load(name, iv):
    man = pd.read_csv(DATA / "manifest.csv")
    m = man[(man["exch"] == "MCX") & (man["name"] == name) & (man["interval"] == iv) & (man["front_stitched"].astype(str) == "True")]
    if m.empty:
        return None
    p = DATA / "MCX" / f"{m['symbol'].iat[0]}_{iv}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
    d = d.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    d["volume"] = d["volume"].clip(lower=0)
    from research.search import strategy_search as SS          # same contract-change days as every MCX study
    sw = SS.switch_days(name, "MCX", d)
    day = d["time"].dt.normalize()
    d["switch"] = day.isin(sw) & (day != day.shift(1))
    return d


def resample(d, m):
    day = d["time"].dt.normalize()
    k = ((d["time"] - day).dt.total_seconds() // 60 - 540) // m
    g = d.groupby([day, k], sort=True)
    return g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                 volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)


def context(f, base):
    """Filter columns aligned to f (all from completed data)."""
    c, h, l = f["close"], f["high"], f["low"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    chop = 100 * np.log10(tr.rolling(14).sum() / (h.rolling(14).max() - l.rolling(14).min())) / np.log10(14)
    er = (c - c.shift(20)).abs() / c.diff().abs().rolling(20).sum()
    volx = f["volume"] / f["volume"].rolling(20).mean().shift(1)
    # previous completed 1-hour ADX
    h1 = base.set_index("time").resample("60min", offset="0min").agg(dict(open="first", high="max", low="min", close="last")).dropna()
    h1["adx"] = I.adx(h1.reset_index(drop=True)).values
    h1 = h1.reset_index(drop=True).assign(time=h1.index + pd.Timedelta(minutes=60))[["time", "adx"]].sort_values("time")
    adx = pd.merge_asof(f[["time"]], h1, on="time", direction="backward")["adx"]
    dd = base.assign(day=base["time"].dt.normalize()).groupby("day")["close"].last()
    e20, e50 = I.ema(dd, 20), I.ema(dd, 50)
    up = ((e20 > e50) & (dd > e50)).shift(1); dn = ((e20 < e50) & (dd < e50)).shift(1)
    fd = f["time"].dt.normalize()
    hm = f["time"].dt.hour * 100 + f["time"].dt.minute
    return dict(chop=chop.values, er=er.values, volx=volx.values, adx=adx.values,
                dup=fd.map(up).fillna(False).astype(bool).values, ddn=fd.map(dn).fillna(False).astype(bool).values,
                ses=((hm >= 915) & (hm <= 2230)).values)


def ok(ctx, i, side, flt):
    if flt == "none":
        return True
    for p in flt.split("+"):
        if p == "CHOP" and not ctx["chop"][i] < 50:
            return False
        if p == "ADX1H" and not ctx["adx"][i] >= 22:
            return False
        if p == "ER" and not ctx["er"][i] >= 0.30:
            return False
        if p == "DT" and not (ctx["dup"][i] if side > 0 else ctx["ddn"][i]):
            return False
        if p == "VOL" and not ctx["volx"][i] >= 1.5:
            return False
        if p == "SES" and not ctx["ses"][i]:
            return False
    return True


def run_exit(f, sig, take, exit_, cost):
    """sig: +1/-1/0 raw signals (for reversal exits); take: bool mask of signals allowed to OPEN a trade."""
    o, h, l, c = (f[x].values for x in ("open", "high", "low", "close"))
    tm = f["time"]; day = tm.dt.normalize().values; hm = (tm.dt.hour * 100 + tm.dt.minute).values
    sw = f["switch"].values.astype(bool); atr = I.atr(f, 14).values
    out, i, n = [], 0, len(c)
    while i < n - 1:
        if not take[i] or not atr[i] > 0 or day[i + 1] != day[i] or hm[i] >= EOD - 30 or sw[i + 1]:
            i += 1; continue
        s = sig[i]; e0 = o[i + 1]; R = atr[i]
        st = e0 - s * (3 * R if exit_ in ("REV3", "TRL") else R) if exit_ != "REV" else None
        tp = e0 + s * 2 * R if exit_ == "2R" else None
        ext = e0; j = i + 1; px = None
        while j < n:
            if sw[j] or day[j] != day[i] or hm[j] >= EOD:
                px = o[j] if not sw[j] else c[j - 1]; break
            if st is not None and ((l[j] <= st) if s > 0 else (h[j] >= st)):
                px = o[j] if s * (o[j] - st) <= 0 else st; break
            if tp is not None and ((h[j] >= tp) if s > 0 else (l[j] <= tp)):
                px = o[j] if s * (o[j] - tp) >= 0 else tp; break
            if exit_ in ("REV", "REV3") and sig[j] == -s:
                px = o[j + 1] if j + 1 < n else c[j]; break
            if exit_ == "TRL":
                ext = max(ext, h[j]) if s > 0 else min(ext, l[j]); st = ext - s * 3 * atr[j] if s > 0 else ext + 3 * atr[j]
                st = max(st, e0 - 3 * R) if s > 0 else min(st, e0 + 3 * R)
            j += 1
        if px is None:
            px, j = c[-1], n - 1
        g = s * (px - e0); k = 2 * cost[min(i, len(cost) - 1)]
        out.append((tm.iat[i], "BUY" if s > 0 else "SELL", g - k, (g - k) / R, g / R, j - i))
        i = j if j > i else i + 1                   # a signal on the exit candle may open the next (reverse) trade
    return out


def one(name):
    rows = []
    d5, d3 = load(name, "FIVE_MINUTE"), load(name, "THREE_MINUTE")
    for m, d in ((3, d3), (5, d5), (10, d5), (15, d5), (30, d5)):
        if d is None or len(d) < 2000:
            continue
        f = d if m in (3, 5) else resample(d, m)
        f = f.reset_index(drop=True)
        b, s = LT.signals(f)
        sig = np.where(b, 1, np.where(s, -1, 0))
        ctx = context(f, d)
        cost = np.array([INS.cost_points(name, p, 1.0) for p in f["close"].values])
        for flt in FILTERS:
            take = np.array([sig[i] != 0 and ok(ctx, i, sig[i], flt) for i in range(len(f))])
            for ex in ("REV", "REV3", "TRL", "2R"):
                for t in run_exit(f, sig, take, ex, cost):
                    rows.append((name, f"{m} min", flt, ex) + t)
    return rows


def main():
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, NAMES) for r in x]
    T = pd.DataFrame(rows, columns=["name", "tf", "filter", "exit", "time", "side", "pts", "r", "gross_r", "bars"])
    T["time"] = pd.to_datetime(T["time"])
    T["split"] = np.where(T.time < T1, "p1", np.where(T.time < T2, "p2", "p3"))
    T.to_csv(OUT / "liqtl_mcx5_trades.csv.gz", index=False)
    K = ["tf", "filter", "exit", "side"]
    S = T.groupby(K).agg(n=("r", "size"), win=("r", lambda s: (s > 0).mean() * 100), R=("r", "mean"), gross=("gross_r", "mean")) \
        .join(T.pivot_table(index=K, columns="split", values="r", aggfunc="mean")[["p1", "p2", "p3"]])
    S["all3"] = (S[["p1", "p2", "p3"]] > 0).all(axis=1)
    S = S.reset_index(); S.to_csv(OUT / "liqtl_mcx5_summary.csv", index=False)
    # per commodity for the robust rows
    P = T.groupby(K + ["name"]).agg(n=("r", "size"), R=("r", "mean")).reset_index()
    P.to_csv(OUT / "liqtl_mcx5_by_name.csv", index=False)
    pd.set_option("display.width", 230); pd.set_option("display.max_rows", 400)
    print(f"trades {len(T):,} · {T.time.min():%Y-%m-%d} → {T.time.max():%Y-%m-%d}")
    print("\nROBUST (positive in all 3 periods, n ≥ 100), best first:")
    print(S[S.all3 & (S.n >= 100)].sort_values("R", ascending=False).head(40).round(3).to_string(index=False))
    print("\nNo filter, by timeframe / exit:")
    print(S[S["filter"] == "none"].round(3).to_string(index=False))


if __name__ == "__main__":
    main()

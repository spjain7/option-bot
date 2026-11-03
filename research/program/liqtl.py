"""LIQTL-001 (3-Nov-2026, owner: "check accuracy of this [StratifyTrade 'Liquidity Trendline With Signals'] on 3/5/10/15/30 min,
with what risk-reward and how many points").
Faithful Python port of the Pine v5 script (period 5, padding 2, ATR 200, one shared 'broken' flag):
  * pivot highs / lows with 5 bars each side (confirmed 5 bars later – no look-ahead)
  * DOWN trendline (resistance) from two falling pivot highs; valid when the flag 'broken' is set, else the 4-pivot rule
    (the last two pivots below the two before); dropped if any bar since the first pivot already closed its LOW above it
  * UP trendline (support) mirror from rising pivot lows; the zone is the line + padding (2 × min(0.1·ATR200, 0.1 % of price))
  * BUY ('Breaking Up')   : a bar's LOW above the down trendline            -> entry at the NEXT bar's open
    SELL ('Breaking Down'): a bar's HIGH below the up line + padding        -> entry at the next bar's open
Data: NSE stock futures, 5-minute candles 27-Jul → 29-Oct-2026 (≈ 3 months, ~216 stocks); 10 / 15 / 30 min built from them
(day-anchored at 09:15). 3-minute needs 1-minute history, which we do not have (only ~2 days of the live stream) – not tested.
Exits tested: stop = signal bar's low (BUY) / high (SELL) ± 0.1 ATR14  or  1 ATR14; targets 1R / 1.5R / 2R / 3R;
intraday – flat at 15:20; one trade at a time; signals after 15:00 skipped. Costs 0.04 % of price round trip (1x), shown at 2x.
python research/program/liqtl.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402

M5 = ROOT / "research/data/m5"
OUT = ROOT / "research/program/results"
TFS = (5, 10, 15, 30)
LEN, SPACE = 5, 2.0
COST = 0.0004
STOPS = ("bar", "1ATR")
TGTS = (1.0, 1.5, 2.0, 3.0)


def resample(df, m):
    if m == 5:
        return df.reset_index(drop=True)
    day = df["time"].dt.normalize()
    k = ((df["time"] - day).dt.total_seconds() // 60 - 555) // m
    g = df.groupby([day, k], sort=True)
    return g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                 volume=("volume", "sum")).reset_index(drop=True)


def signals(f):
    """Port of the Pine logic. Returns arrays buy, sell (bool, on the signal bar)."""
    h, l, c = f["high"].values, f["low"].values, f["close"].values
    n = len(c)
    atr200 = I.atr(f, 200).values
    hs = pd.Series(h); ls = pd.Series(l)
    win = 2 * LEN + 1
    ph = (hs.rolling(win).max() == hs.shift(LEN)).values          # pivot high confirmed at t (located at t-LEN)
    pl = (ls.rolling(win).min() == ls.shift(LEN)).values
    buy, sell = np.zeros(n, bool), np.zeros(n, bool)
    upbin, dnbin = [], []
    up = dn = None          # (x1, y1, slope, pad)
    broken = False
    valid_u = valid_d = False
    for t in range(win, n):
        pad = min(atr200[t] * 0.1, c[t] * 0.001) * SPACE if np.isfinite(atr200[t]) else 0.0
        if ph[t]:
            upbin.insert(0, (h[t - LEN], t - LEN))
            if len(upbin) > 1:
                cur, bef = upbin[0], upbin[1]
                if cur[0] < bef[0]:
                    if broken:
                        valid_u = True
                    elif len(upbin) > 3:
                        po, pc_, now, late = upbin[3][0], upbin[2][0], upbin[1][0], upbin[0][0]
                        valid_u = now < pc_ and now < po and late < pc_ and late < po
                    else:
                        valid_u = False
                    if valid_u:
                        sl = (cur[0] - bef[0]) / (cur[1] - bef[1])
                        line = lambda x, b=bef, s=sl: b[0] + s * (x - b[1])  # noqa: E731
                        if any(l[i] > line(i) for i in range(bef[1], t + 1)):
                            up = None; upbin.clear(); broken = True
                        else:
                            up = (bef[1], bef[0], sl, pad); upbin.clear(); broken = False
        if up is not None:
            y = up[1] + up[2] * (t - 1 - up[0])                      # Pine compares with the line value carried from the last bar
            if l[t] > y:
                up = None; broken = True; upbin.clear(); buy[t] = True
        if pl[t]:
            dnbin.insert(0, (l[t - LEN], t - LEN))
            if len(dnbin) > 1:
                cur, bef = dnbin[0], dnbin[1]
                if cur[0] > bef[0]:
                    if broken:
                        valid_d = True
                    elif len(dnbin) > 3:
                        po, pc_, now, late = dnbin[3][0], dnbin[2][0], dnbin[1][0], dnbin[0][0]
                        valid_d = now > pc_ and now > po and late > pc_ and late > po
                    else:
                        valid_d = False
                    if valid_d:
                        sl = (cur[0] - bef[0]) / (cur[1] - bef[1])
                        line = lambda x, b=bef, s=sl: b[0] + s * (x - b[1])  # noqa: E731
                        if any(h[i] < line(i) for i in range(bef[1], t + 1)):
                            dn = None; dnbin.clear(); broken = True
                        else:
                            dn = (bef[1], bef[0], sl, pad); dnbin.clear(); broken = False
        if dn is not None:
            y = dn[1] + dn[2] * (t - 1 - dn[0]) + dn[3]               # 'btm' = the padded line (above the pivot line)
            if h[t] < y:
                dn = None; broken = True; dnbin.clear(); sell[t] = True
    return buy, sell


def trades(f, buy, sell, stop_kind, tgt):
    o, h, l, c = (f[x].values for x in ("open", "high", "low", "close"))
    tm = f["time"]; day = tm.dt.normalize().values; hm = (tm.dt.hour * 100 + tm.dt.minute).values
    atr = I.atr(f, 14).values
    out, busy = [], -1
    for i in np.flatnonzero(buy | sell):
        if i <= busy or i + 1 >= len(c) or day[i + 1] != day[i] or hm[i] >= 1500 or not atr[i] > 0:
            continue
        s = 1 if buy[i] else -1
        e0 = o[i + 1]
        st = (l[i] - 0.1 * atr[i]) if s > 0 else (h[i] + 0.1 * atr[i])
        if stop_kind == "1ATR":
            st = e0 - s * atr[i]
        R = s * (e0 - st)
        if not R > 0:
            continue
        tp = e0 + s * tgt * R
        px = why = None; j = i + 1
        while j < len(c):
            if day[j] != day[i] or hm[j] >= 1520:
                px, why = (o[j], "eod") if day[j] != day[i] else (o[j], "eod"); j -= 0; break
            if (l[j] <= st) if s > 0 else (h[j] >= st):
                px, why = (o[j] if (s * (o[j] - st) <= 0 and j > i + 1) else st), "stop"; break
            if (h[j] >= tp) if s > 0 else (l[j] <= tp):
                px, why = (o[j] if (s * (o[j] - tp) >= 0 and j > i + 1) else tp), "target"; break
            j += 1
        if px is None:
            px, why = c[-1], "end"
        g = s * (px - e0)
        out.append(dict(side="BUY" if s > 0 else "SELL", time=tm.iat[i], entry=e0, risk_pts=R, risk_pct=R / e0 * 100,
                        pts=g - 2 * COST * e0, pct=(g - 2 * COST * e0) / e0 * 100, r2=(g - 2 * COST * e0) / R, why=why,
                        gross_r=g / R))
        busy = j
    return out


def one(p):
    try:
        df = pd.read_csv(p, parse_dates=["time"]).sort_values("time").drop_duplicates("time")
    except Exception:
        return []
    df = df[(df["time"].dt.hour * 100 + df["time"].dt.minute >= 915) & (df["time"].dt.hour * 100 + df["time"].dt.minute < 1530)]
    name = p.stem[4:]
    rows = []
    for m in TFS:
        f = resample(df, m)
        if len(f) < 300:
            continue
        b, s = signals(f)
        for sk in STOPS:
            for tg in TGTS:
                for x in trades(f, b, s, sk, tg):
                    x.update(name=name, tf=f"{m} min", stop=sk, target=f"{tg:g}R"); rows.append(x)
    return rows


def main():
    fs = sorted(M5.glob("fut_*.csv"))
    with Pool(3) as pool:
        rows = [r for x in pool.imap_unordered(one, fs, chunksize=4) for r in x]
    T = pd.DataFrame(rows)
    T.to_csv(OUT / "liqtl_trades.csv.gz", index=False)
    half = T["time"].min() + (T["time"].max() - T["time"].min()) / 2
    K = ["tf", "stop", "target", "side"]
    S = T.groupby(K).agg(trades=("r2", "size"), win=("r2", lambda s: (s > 0).mean() * 100), avg_R=("r2", "mean"),
                         avg_pts=("pts", "mean"), avg_pct=("pct", "mean"), win_pct=("pct", lambda s: s[s > 0].mean()),
                         loss_pct=("pct", lambda s: s[s <= 0].mean()), risk_pct=("risk_pct", "mean"))
    S["R_1st_half"] = T[T.time < half].groupby(K)["r2"].mean()
    S["R_2nd_half"] = T[T.time >= half].groupby(K)["r2"].mean()
    S = S.reset_index(); S.to_csv(OUT / "liqtl_summary.csv", index=False)
    pd.set_option("display.width", 230); pd.set_option("display.max_rows", 300)
    print(f"trades {len(T):,} · stocks {T.name.nunique()} · {T.time.min():%d-%b} → {T.time.max():%d-%b-%Y}")
    print(S.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

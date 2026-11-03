"""LIQTL-003 (3-Nov-2026, owner: "why different from my chart – I traded 5-min live and got 4000+ points").
The owner holds until the move ends, not a fixed 1:2. Exit variants on the same signals (entry next bar open, costs 0.08 % stocks /
2x MCX model):  REV  hold until the opposite signal (stop-and-reverse), flat at day end (intraday)
                REV+1.5ATR  same with a 1.5 ATR protective stop ·  REV+3ATR  3 ATR stop
Stocks 5/10/15/30-min (27-Jul → 29-Oct-2026), MCX 7 commodities 1-hour (2022-26, also overnight hold)."""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import liqtl as LT, emax as EX  # noqa: E402
from crude import indicators as I  # noqa: E402


def rev(f, buy, sell, k, cost_pts, eod, intraday=True):
    o, h, l, c = (f[x].values for x in ("open", "high", "low", "close"))
    tm = f["time"]; day = tm.dt.normalize().values; hm = (tm.dt.hour * 100 + tm.dt.minute).values
    sw = f["switch"].values if "switch" in f else np.zeros(len(c), bool)
    atr = I.atr(f, 14).values
    sig = np.where(buy, 1, np.where(sell, -1, 0))
    out, i, n = [], 0, len(c)
    while i < n - 1:
        if sig[i] == 0 or not atr[i] > 0 or (intraday and (day[i + 1] != day[i] or hm[i] >= eod - 30)) or sw[i + 1]:
            i += 1; continue
        s = sig[i]; e0 = o[i + 1]; R = atr[i]; st = e0 - s * k * R if k else None
        j = i + 1; px = None; nxt = None
        while j < n:
            if sw[j]:
                px = c[j - 1]; break
            if intraday and (day[j] != day[i] or hm[j] >= eod):
                px = o[j]; break
            if st is not None and ((l[j] <= st) if s > 0 else (h[j] >= st)):
                px = o[j] if s * (o[j] - st) <= 0 else st; break
            if sig[j] == -s:                      # opposite signal on bar j -> exit at the next open (and reverse)
                px = o[j + 1] if j + 1 < n else c[j]; nxt = j; break
            j += 1
        if px is None:
            px, j = c[-1], n - 1
        g = s * (px - e0); cs = cost_pts[min(i, len(cost_pts) - 1)]
        out.append(dict(side="BUY" if s > 0 else "SELL", time=tm.iat[i], pts=g - cs, pct=(g - cs) / e0 * 100, r=(g - cs) / R,
                        gross_r=g / R, bars=j - i))
        i = nxt if nxt is not None else j + 1
    return out


def stock(p):
    df = pd.read_csv(p, parse_dates=["time"]).sort_values("time").drop_duplicates("time")
    hm = df["time"].dt.hour * 100 + df["time"].dt.minute
    df = df[(hm >= 915) & (hm < 1530)]
    rows = []
    for m in (5, 10, 15, 30):
        f = LT.resample(df, m)
        if len(f) < 300:
            continue
        b, s = LT.signals(f)
        cost = (f["close"] * 2 * LT.COST).values
        for k in (None, 1.5, 3.0):
            for x in rev(f, b, s, k, cost, 1520):
                x.update(mkt="STOCKS", tf=f"{m} min", stop=f"{k}ATR" if k else "none"); rows.append(x)
    return rows


def mcx(nm):
    fr = EX.frames(("mi", nm, "MCX"))
    f1, c1 = [(f, c) for s_, f, o, c in fr if s_ == "MCX 1h"][0]
    f1 = f1.reset_index(drop=True).copy(); f1["volume"] = f1["volume"].clip(lower=0)
    b, s = LT.signals(f1)
    rows = []
    for intra in (True, False):
        for k in (None, 1.5, 3.0):
            for x in rev(f1, b, s, k, 2 * c1, 2320, intraday=intra):
                x.update(mkt="MCX " + nm, tf="1h " + ("intraday" if intra else "overnight"), stop=f"{k}ATR" if k else "none"); rows.append(x)
    return rows


def main():
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(stock, sorted(LT.M5.glob("fut_*.csv")), chunksize=4) for r in x]
        rows += [r for x in p.imap_unordered(mcx, ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]) for r in x]
    T = pd.DataFrame(rows)
    T["grp"] = np.where(T.mkt.str.startswith("MCX SILVER"), "MCX SILVER", np.where(T.mkt.str.startswith("MCX"), "MCX all 7", "STOCKS"))
    a = T.groupby(["grp", "tf", "stop", "side"]).agg(n=("r", "size"), win=("r", lambda s: (s > 0).mean() * 100), gross_R=("gross_r", "mean"),
                                                   net_R=("r", "mean"), avg_pts=("pts", "mean"), best_pts=("pts", "max"), bars=("bars", "median"))
    b = T[T.grp != "MCX SILVER"].groupby(["grp", "tf", "stop", "side"]).size()
    S = a[(a.index.get_level_values(0) != "MCX all 7") | True]
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print(S.round(3).to_string())
    S.reset_index().to_csv(LT.OUT / "liqtl_rev_summary.csv", index=False)


if __name__ == "__main__":
    main()

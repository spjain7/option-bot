"""RSIPAT-001 (4-Nov-2026) – owner: "after RSI 75 / 25 on the hourly, wait for a REVERSAL PATTERN, enter on it, SL as per that setup".

Setup zone: RSI(14) 1h >= 75 (SELL side) or <= 25 (BUY side) on any candle in the last 6 candles before the pattern completes.
Patterns (SELL shown; BUY is the mirror):
  ENGULF : bearish engulfing                       trigger = low of the engulfing candle     SL = high of the 2 candles
  PIN    : shooting star (upper wick >= 2 x body,  trigger = its low                          SL = its high
           close in the lower 40 %)
  ESTAR  : evening star (big up, small body, big   trigger = low of the 3rd candle            SL = high of the 3 candles
           down closing below the 1st candle's mid)
  INSIDE : inside bar after the extreme candle     trigger = low of the mother candle         SL = high of the mother candle
  MTOP   : double top / lower high: extreme high H, pull-back low L, a later high that fails below H + 0.25 ATR,
           trigger = L (break of structure)                                                  SL = that lower high
  DIV    : RSI divergence: new price high with RSI lower than at the previous RSI-75 high, trigger = low of the
           divergence candle                                                                 SL = its high
Entry = SELL-STOP at the trigger (fills at the trigger, or at the open if it gaps through), valid for 3 candles; cancelled if
SL is hit first. A fill candle that also touches SL counts as a full loss. SL buffer 0.05 ATR. Risk must be 0.25-3 ATR.
Targets 1R / 1.5R / 2R; costs 0.1R; max 40 candles; contract switch -> closed at previous close; one trade at a time per pattern.
Fixed rules, nothing chosen on the data. Reported 2022-24 and 2025-26 separately.

  python -m research.search.rsi_pattern_mcx   -> research/search/results_rsipat/*
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_rsipat"
SPLIT = pd.Timestamp("2025-01-01")
TGTS = (1.0, 1.5, 2.0)
COST, MAXH, VALID, ZONE = 0.1, 40, 3, 6


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).values


def atr(df):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False).mean().values


def setups(df, hi_lvl, lo_lvl):
    """List of (bar_i, side, pattern, trigger, sl). side -1 SELL / +1 BUY. Everything known at the close of bar i."""
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    r, a = rsi(df["close"]), atr(df)
    n = len(c); out = []
    for s in (-1, 1):
        # work in "SELL space": for BUY mirror prices
        O, Hh, L, C = (o, h, l, c) if s < 0 else (-o, -l, -h, -c)
        R = r if s < 0 else 100 - r
        lvl = hi_lvl if s < 0 else 100 - lo_lvl
        zone = pd.Series(R >= lvl).rolling(ZONE, min_periods=1).max().values.astype(bool)
        last_ext = None                                     # index of the last RSI-extreme swing high (for MTOP / DIV)
        for i in range(30, n):
            if R[i] >= lvl and (last_ext is None or Hh[i] > Hh[last_ext] or i - last_ext > 20):
                last_ext = i
            if not zone[i] or np.isnan(a[i]):
                continue
            body = abs(C[i] - O[i]); rg = Hh[i] - L[i]
            if rg <= 0:
                continue
            pos = (C[i] - L[i]) / rg
            cand = []
            if C[i] < O[i] and C[i - 1] > O[i - 1] and C[i] <= O[i - 1] and O[i] >= C[i - 1]:
                cand.append(("ENGULF", L[i], max(Hh[i], Hh[i - 1])))
            if (Hh[i] - max(O[i], C[i])) >= 2 * body and pos <= 0.4:
                cand.append(("PIN", L[i], Hh[i]))
            b1, b2, b3 = C[i - 2] - O[i - 2], abs(C[i - 1] - O[i - 1]), O[i] - C[i]
            if b1 > 0 and b3 > 0 and b2 < 0.5 * b1 and C[i] < (O[i - 2] + C[i - 2]) / 2:
                cand.append(("ESTAR", L[i], max(Hh[i - 2:i + 1])))
            if Hh[i] <= Hh[i - 1] and L[i] >= L[i - 1] and R[i - 1] >= lvl - 5:
                cand.append(("INSIDE", L[i - 1], Hh[i - 1]))
            if last_ext is not None and 3 <= i - last_ext <= 20:
                seg_lo = L[last_ext:i].min(); lh = Hh[last_ext + 1:i + 1].max()
                if lh < Hh[last_ext] + 0.25 * a[i] and Hh[i] == lh and C[i] < O[i] and lh > seg_lo + 0.5 * a[i]:
                    cand.append(("MTOP", seg_lo, lh))
            if last_ext is not None and 2 <= i - last_ext <= 20 and Hh[i] > Hh[last_ext] and R[i] < R[last_ext] - 3 and C[i] < O[i]:
                cand.append(("DIV", L[i], Hh[i]))
            for p, trig, sl in cand:
                sl = sl + 0.05 * a[i]
                risk = sl - trig
                if not (0.25 * a[i] <= risk <= 3 * a[i]):
                    continue
                if s > 0:
                    trig, sl = -trig, -sl
                out.append((i, s, p, trig, sl))
    return out


def simulate(df, i, s, trig, sl):
    """Stop-entry at trig (valid VALID candles), SL fixed, targets in R. Returns dict tgt -> R, or None (no fill)."""
    o, h, l, c, sw = (df[k].values for k in ("open", "high", "low", "close", "switch"))
    n = len(c)
    for j in range(i + 1, min(i + 1 + VALID, n)):
        if sw[j]:
            return None
        if (s < 0 and h[j] >= sl) or (s > 0 and l[j] <= sl):
            if not ((s < 0 and l[j] <= trig) or (s > 0 and h[j] >= trig)):
                return None                                   # SL first -> setup cancelled
        hit = (s < 0 and l[j] <= trig) or (s > 0 and h[j] >= trig)
        if not hit:
            continue
        e = (min(o[j], trig) if s < 0 else max(o[j], trig))
        R = abs(sl - e)
        if R <= 0:
            return None
        out = {}
        for tg in TGTS:
            tp = e + s * tg * R
            if (s < 0 and h[j] >= sl) or (s > 0 and l[j] <= sl):
                out[tg] = -1 - COST; continue                 # fill candle also reaches SL
            res = None
            for k in range(j + 1, min(j + 1 + MAXH, n)):
                if sw[k]:
                    res = s * (c[k - 1] - e) / R - COST; break
                if (s < 0 and h[k] >= sl) or (s > 0 and l[k] <= sl):
                    px = o[k] if ((s < 0 and o[k] > sl) or (s > 0 and o[k] < sl)) else sl
                    res = s * (px - e) / R - COST; break
                if (s < 0 and l[k] <= tp) or (s > 0 and h[k] >= tp):
                    res = tg - COST; break
            if res is None:
                k = min(j + MAXH, n - 1); res = s * (c[k] - e) / R - COST
            out[tg] = res
        return dict(out, fill=j)
    return None


def pf(x):
    g, ls = x[x > 0].sum(), -x[x < 0].sum()
    return round(g / ls, 2) if ls else np.nan


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for seg, tf, name, df in H.datasets():
        if seg == "STK":
            break
        if seg != "MCX" or tf != "1h":
            continue
        df = df.reset_index(drop=True)
        for lv in ((75, 25), (70, 30)):
            busy = {}
            for i, s, p, trig, sl in sorted(setups(df, *lv)):
                if busy.get((s, p), -1) >= i:
                    continue
                r = simulate(df, i, s, trig, sl)
                if r is None:
                    continue
                busy[(s, p)] = r["fill"] + MAXH // 4
                rows.append((name, f"{lv[0]}/{lv[1]}", "BUY" if s > 0 else "SELL", p, df["time"].iloc[i], r[1.0], r[1.5], r[2.0]))
        print(name, "done", flush=True)
    t = pd.DataFrame(rows, columns=["name", "lvl", "side", "pattern", "time", "R1", "R15", "R2"])
    t["period"] = np.where(t.time < SPLIT, "2022-24", "2025-26")
    t.to_csv(OUT / "trades.csv.gz", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 500)

    def summ(g):
        d = {}
        for col in ("R1", "R15", "R2"):
            d[f"{col}_win"] = round((g[col] > 0).mean(), 2); d[f"{col}_avg"] = round(g[col].mean(), 2); d[f"{col}_pf"] = pf(g[col])
        d["n"] = len(g)
        return pd.Series(d)
    m = t[t.lvl == "75/25"]
    by_pat = m.groupby(["pattern", "side", "period"]).apply(summ)
    by_name = m.groupby(["name", "side", "period"]).apply(summ)
    by_name_pat = m.groupby(["name", "pattern", "side", "period"]).apply(summ)
    alt = t[t.lvl == "70/30"].groupby(["pattern", "side", "period"]).apply(summ)
    by_pat.to_csv(OUT / "by_pattern.csv"); by_name.to_csv(OUT / "by_commodity.csv"); by_name_pat.to_csv(OUT / "by_commodity_pattern.csv")
    alt.to_csv(OUT / "by_pattern_70_30.csv")
    print("=== 75/25 by pattern ===\n", by_pat.to_string())
    print("=== 75/25 by commodity (all patterns) ===\n", by_name.to_string())
    print("=== 70/30 by pattern ===\n", alt.to_string())


if __name__ == "__main__":
    main()

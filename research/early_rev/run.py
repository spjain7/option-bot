"""EARLY-REV – early-stage reversals with LOW risk and HIGH reward (owner 12-Nov-2026). Research only.
Each trigger fires at the first sign of a turn; the stop sits just beyond the reversal extreme (tight), the target is
large. Judged by net R per trade after costs (expectancy), not by win rate. BUY shown, SELL mirrored.
  T1 SPRING          low below the prior 20-bar low, close back above it in the bar's upper half (stop-run reclaimed)
  T2 SWEEP_MSS       low below the prior 20-bar low, then within 3 bars a close above the sweep bar's high
  T3 FAILED_BREAK    close below the prior 20-bar low, then within 2 bars a close back above that level
  T4 DIV_BREAK       regular bullish RSI or MACD divergence (known 3 bars after the swing), then within 5 bars a close
                     above the high of the confirmation bar
  T5 CLIMAX          volume >= 2.5x average, range >= 1.5 ATR, after a fall of >= 2 ATR in 5 bars, close in the top half
  T6 KEY_REVERSAL    new 10-bar low and a close above the previous bar's high (outside reversal)
  T7 RSI_RECLAIM     RSI(14) <= 30 within the last 5 bars and a close above the highest high of the last 3 bars
  T8 DOUBLE_BOTTOM   a second swing low within 0.25 ATR of the previous one (5–40 bars apart), then a close above the
                     second low's bar high
Stop: the setup's own extreme (lowest low of the last 3 bars, or the sweep / pattern low) - 0.1 ATR, kept 0.3–2 ATR.
Exits (each tested): fixed 3R · 5R · 8R; TRAIL = stop to breakeven at +1R, then the 5-bar low as a trailing stop.
Context: all · counter-trend (BUY below EMA200 = true reversal) · with-trend (BUY above EMA200 = pullback reversal).
Markets: MCX 1h / 3h / 1d, NSE stock futures 1d, NSE index futures 1h, NSE cash 1d (BUY only). Real costs; next-bar
open entries; stop first inside a bar; gaps at the open; intraday index flat by the session end.
Gate: profit and PF >= 1.2 in DEV, VALID and OOS, >= 30 trades each; BH-FDR 10 % over every test.
python -m research.early_rev.run  ->  results/early_rev.csv"""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.rsirev import run as RR  # noqa: E402
from research.cycle2 import common as C, cont_buy as CB  # noqa: E402
from research.families import run as FA  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)


def triggers(b):
    o, h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("open", "high", "low", "close", "volume"))
    n = len(c); pc = c.shift(1)
    atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    rng = (h - l).replace(0, np.nan); pos = (c - l) / rng
    S, LV = {}, {}
    I = E.indicators(h, l, c, v); r = I["rsi"]
    D = E.divergences(h, l, {"rsi": I["rsi"], "macd": I["macd"]}, 3)
    e200 = c.ewm(span=200, adjust=False).mean()
    for sd in (1, -1):
        if sd > 0:
            ref = l.shift(1).rolling(20).min(); ext = l; far = lambda x: x.rolling(3).min()
        else:
            ref = h.shift(1).rolling(20).max(); ext = h; far = lambda x: x.rolling(3).max()
        beyond = (l < ref) if sd > 0 else (h > ref)
        back = (c > ref) if sd > 0 else (c < ref)
        upper = (pos >= 0.5) if sd > 0 else (pos <= 0.5)
        S["T1_SPRING", sd] = (beyond & back & upper).fillna(False).values; LV["T1_SPRING", sd] = ext.values
        z = np.zeros(n, bool); lv = np.full(n, np.nan); bz = beyond.fillna(False).values
        for i in np.where(bz)[0]:
            for j in range(i + 1, min(i + 4, n)):
                if (sd > 0 and c.iloc[j] > h.iloc[i]) or (sd < 0 and c.iloc[j] < l.iloc[i]):
                    z[j] = True; lv[j] = (l.iloc[i: j + 1].min() if sd > 0 else h.iloc[i: j + 1].max()); break
        S["T2_SWEEP_MSS", sd] = z; LV["T2_SWEEP_MSS", sd] = lv
        brk = ((c < ref) if sd > 0 else (c > ref)).fillna(False).values; z = np.zeros(n, bool); lv = np.full(n, np.nan)
        for i in np.where(brk)[0]:
            for j in (i + 1, i + 2):
                if j < n and ((sd > 0 and c.iloc[j] > ref.iloc[i]) or (sd < 0 and c.iloc[j] < ref.iloc[i])):
                    z[j] = True; lv[j] = (l.iloc[i: j + 1].min() if sd > 0 else h.iloc[i: j + 1].max()); break
        S["T3_FAILED_BREAK", sd] = z; LV["T3_FAILED_BREAK", sd] = lv
        dv = D["rsi", "regular", sd] | D["macd", "regular", sd]; z = np.zeros(n, bool); lv = np.full(n, np.nan)
        for i in np.where(dv)[0]:
            for j in range(i + 1, min(i + 6, n)):
                if (sd > 0 and c.iloc[j] > h.iloc[i]) or (sd < 0 and c.iloc[j] < l.iloc[i]):
                    z[j] = True; lv[j] = (l.iloc[max(0, i - 4): j + 1].min() if sd > 0 else h.iloc[max(0, i - 4): j + 1].max()); break
        S["T4_DIV_BREAK", sd] = z; LV["T4_DIV_BREAK", sd] = lv
        rv = v / v.rolling(20).mean().shift(1)
        fall = ((c.shift(1) - c.shift(6)) <= -2 * atr) if sd > 0 else ((c.shift(1) - c.shift(6)) >= 2 * atr)
        S["T5_CLIMAX", sd] = ((rv >= 2.5) & ((h - l) >= 1.5 * atr) & fall & upper).fillna(False).values; LV["T5_CLIMAX", sd] = ext.values
        new10 = (l <= l.rolling(10).min()) if sd > 0 else (h >= h.rolling(10).max())
        kr = (c > h.shift(1)) if sd > 0 else (c < l.shift(1))
        S["T6_KEY_REVERSAL", sd] = (new10 & kr).fillna(False).values; LV["T6_KEY_REVERSAL", sd] = far(ext).values
        was = ((r <= 30) if sd > 0 else (r >= 70)).rolling(5).max() > 0
        rec = (c > h.shift(1).rolling(3).max()) if sd > 0 else (c < l.shift(1).rolling(3).min())
        S["T7_RSI_RECLAIM", sd] = (was & rec).fillna(False).values; LV["T7_RSI_RECLAIM", sd] = (l.rolling(5).min() if sd > 0 else h.rolling(5).max()).values
        K = 3; w = 2 * K + 1
        piv = np.where(((l == l.rolling(w, center=True).min()) if sd > 0 else (h == h.rolling(w, center=True).max())).values)[0]
        z = np.zeros(n, bool); lv = np.full(n, np.nan); px = (l if sd > 0 else h).values
        for a_, b_ in zip(piv[:-1], piv[1:]):
            if 5 <= b_ - a_ <= 40 and abs(px[b_] - px[a_]) <= 0.25 * atr.iloc[b_] and b_ + K < n:
                trig = h.iloc[b_] if sd > 0 else l.iloc[b_]
                for j in range(b_ + K, min(b_ + K + 6, n)):
                    if (sd > 0 and c.iloc[j] > trig) or (sd < 0 and c.iloc[j] < trig):
                        z[j] = True; lv[j] = min(px[a_], px[b_]) if sd > 0 else max(px[a_], px[b_]); break
        S["T8_DOUBLE_BOTTOM", sd] = z; LV["T8_DOUBLE_BOTTOM", sd] = lv
    risk = {}
    for k, lv in LV.items():
        sd = k[1]; lv = pd.Series(lv)
        d = (c - lv + 0.1 * atr) if sd > 0 else (lv - c + 0.1 * atr)
        risk[k] = d.clip(lower=0.3 * atr, upper=2.0 * atr).values
    ctx = {"all": np.ones(n, bool), "counter": None, "with": None}
    return S, risk, (c > e200).values


@njit(cache=True)
def sim_trail(o, h, l, c, sig, side, risk, grp, hold, costf):
    """stop at entry - risk; at +1R the stop moves to breakeven, then trails at the 5-bar low (BUY) / high (SELL)."""
    n = len(c); ei = np.empty(n, np.int64); nr = np.empty(n); m = 0; t = 0
    while t < n - 2:
        if not sig[t] or not np.isfinite(risk[t]) or risk[t] <= 0 or grp[t + 1] != grp[t]:
            t += 1; continue
        e = t + 1; px = o[e]; rk = risk[t]; st = px - side * rk; armed = False; j = e; x = np.nan
        while j < n:
            if grp[j] != grp[e]:
                j -= 1; x = c[j]; break
            if j > e and ((side > 0 and o[j] <= st) or (side < 0 and o[j] >= st)):
                x = o[j]; break
            if (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
                x = st; break
            if not armed and ((side > 0 and h[j] >= px + rk) or (side < 0 and l[j] <= px - rk)):
                armed = True
            if armed:
                lo = l[max(e, j - 4): j + 1].min() if side > 0 else h[max(e, j - 4): j + 1].max()
                nst = max(px, lo) if side > 0 else min(px, lo)
                st = max(st, nst) if side > 0 else min(st, nst)
            if j - e + 1 >= hold or j == n - 1 or grp[j + 1] != grp[j]:
                x = c[j]; break
            j += 1
        if np.isnan(x):
            break
        ei[m] = e; nr[m] = (side * (x - px) - costf[e] * px) / rk; m += 1
        t = j + 1
    return ei[:m], nr[:m]


SETS = {"mcx1h": ("MCX", "1h", lambda: RR.mcx("1h"), 90, (1, -1), [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")], False),
        "mcx3h": ("MCX", "3h", lambda: RR.mcx("3h"), 80, (1, -1), [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")], False),
        "mcx1d": ("MCX", "1d", lambda: RR.mcx("1d"), 40, (1, -1), [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")], False),
        "stockfut": ("NSE_STOCK_FUT", "1d", lambda: RR.stockfut("1d"), 40, (1, -1), [("DEV", "2018-01-01"), ("VAL", "2022-01-01"), ("OOS", "2024-01-01")], False),
        "index": ("NSE_INDEX_FUT", "1h", lambda: RR.index("1h"), 30, (1, -1), [("DEV", "2022-07-01"), ("VAL", "2024-07-01"), ("OOS", "2025-07-01")], True),
        "cash": ("NSE_CASH", "1d", None, 40, (1,), [("DEV", "2005-01-01"), ("VAL", "2015-01-01"), ("OOS", "2020-01-01")], False)}


def run_set(key):
    mk, tf, load, hold, sides, cuts, intraday = SETS[key]
    frames = CB.cash_frames("1d", C.cash_context()) if key == "cash" else load()
    P = FA.MultiPool(); trend = []
    for f in frames:
        b = f["b"].reset_index(drop=True)
        S, risk, up = triggers(b)
        live = np.asarray(f["live"], bool)
        S2, R2 = {}, {}
        for (tg, sd), x in S.items():
            if sd not in sides:
                continue
            for cx, m in (("all", np.ones(len(b), bool)), ("counter", ~up if sd > 0 else up), ("with", up if sd > 0 else ~up)):
                S2[(f"{tg}|{cx}", sd)] = x & live & m; R2[(f"{tg}|{cx}", sd)] = risk[(tg, sd)]
        grp = np.asarray(f["grp"])
        if intraday:
            grp = grp * 10 ** 6 + pd.to_datetime(b["time"]).dt.normalize().values.astype("datetime64[D]").astype(np.int64) % 10 ** 6
        P.add2(b, S2, R2, grp, f["costf"], f["expid"], f["name"])
    P.done(); rows = []
    for k in sorted(P.rk2):
        tgcx, sd = k; tg, cx = tgcx.split("|")
        key_ = (tgcx, "x", "x", sd)
        for ex in ("3R", "5R", "8R", "TRAIL"):
            if key_ not in P.idx:
                rows.append(dict(market=mk, tf=tf, trigger=tg, context=cx, side="BUY" if sd > 0 else "SELL", exit=ex, all_n=0, PASS=False)); continue
            if ex == "TRAIL":
                sig = np.zeros(P.n, np.bool_); sig[P.idx[key_]] = True
                ei, nr = sim_trail(P.o, P.h, P.l, P.c, sig, sd, P.rk2[k], P.grp, hold, P.costf)
                T = pd.DataFrame(dict(name=P.name[ei], entry=P.t[ei], netR=nr, ret=0.0, costR=0.0))
            else:
                T = P.run2(k, float(ex[:-1]), hold)
            if len(T) < 10:
                rows.append(dict(market=mk, tf=tf, trigger=tg, context=cx, side="BUY" if sd > 0 else "SELL", exit=ex, all_n=len(T), PASS=False)); continue
            rw = E.row((tg, cx, ex, sd), T, cuts)
            rw.update(market=mk, tf=tf, trigger=tg, context=cx, side="BUY" if sd > 0 else "SELL", exit=ex,
                      avg_win_R=round(float(T.netR[T.netR > 0].mean()), 2) if (T.netR > 0).any() else np.nan,
                      risk_atr_median=round(float(np.nanmedian(P.rk2[k][P.idx[key_]] / np.maximum(1e-9, np.nanmedian(P.rk2[k])))), 2))
            rows.append(rw)
    return rows


def main(keys):
    rows, t0 = [], time.time()
    for k in keys:
        rows += run_set(k); print(k, f"{time.time() - t0:.0f}s", flush=True)
        pd.DataFrame(rows).to_csv(OUT / "early_rev.csv", index=False)
    L = pd.DataFrame(rows)
    ok = L.t_day.notna(); p = E.pvals(L.t_day.fillna(0).values)
    L["p"] = np.where(ok, p, np.nan); L["FDR10"] = C.bh(L.p.values); L["HOLM5"] = False
    L.loc[ok, "HOLM5"] = E.holm(L.loc[ok, "p"].values)
    L.to_csv(OUT / "early_rev.csv", index=False)
    print("tests", len(L), "PASS", int(L.PASS.sum()), "PASS+FDR", int((L.PASS & L.FDR10).sum()))


if __name__ == "__main__":
    main(sys.argv[1:] or list(SETS))

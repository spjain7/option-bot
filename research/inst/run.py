"""INST – "institutional" MCX setups (owner 12-Nov-2026). Research only. 7 commodities, 5-minute data 2023 -> 3-Nov-2026,
15-minute decision bars (volume profile from 5-minute bars), real MCX fees + 1.5 ticks slippage, next-bar-open entries,
stop first inside a bar, every trade flat by the session's last bar. BUY and SELL apart; win rate AND net R reported.
  I1 ORDER_BLOCK   displacement (>= 2 ATR move in <= 3 bars that closes beyond the prior 20-bar high / low); the last
                   opposite-colour candle before it is the block; entry when price later returns into the block (within
                   30 bars); stop beyond the block - 0.1 ATR; targets 2R / 3R
  I2 FVG           3-candle imbalance after displacement (low[t] > high[t-2] for BUY); entry on the first retrace into
                   the gap (within 30 bars); stop below the gap - 0.1 ATR; targets 2R / 3R
  I3 PDH_PDL_SWEEP price trades beyond the previous day's high / low and the bar closes back inside -> fade; stop beyond
                   the sweep extreme; targets 2R / 3R and "VWAP" (exit at the session VWAP)
  I4 VWAP_2SD      close beyond session VWAP +/- 2 standard deviations (volume-weighted) then a close back inside ->
                   fade toward VWAP; stop beyond the extreme; exit at VWAP or 2R
  I5 VALUE_80      previous day's value area (70 % of volume around the POC, 5-min volume profile); the day opens
                   outside it and two consecutive 15-min closes come back inside -> target the opposite edge of the value
                   area (the "80 % rule"); stop beyond the day's extreme so far
  I6 US_OPEN_ORB   US-session opening range on MCX (first 30 minutes from 18:30 IST, when COMEX / NYMEX are most active):
                   first 15-min close beyond it before 21:30 -> BUY / SELL; stop the other side; 2R / 3R
  I7 PDH_RETEST    close above the previous day's high, then within 8 bars a retest (low <= PDH + 0.1 ATR) closing
                   above it -> BUY (mirror SELL); stop below the retest low; 2R / 3R
Benchmark: every 10th bar with a 1-ATR stop, same targets. Gate: profit and PF >= 1.2 in DEV (2023–24), VALID (2025),
OOS (2026); >= 30 trades each; BH-FDR 10 % over all tests.   python -m research.inst.run  ->  results/inst.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from research.mcxhw.search import bars  # noqa: E402
from research.rsidiv import engine as E  # noqa: E402
from research.cycle2 import common as C  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)
CUTS = [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]


@njit(cache=True)
def sim_lv(o, h, l, c, sig, side, stop, tgt, grp, last, costf):
    """price-level exits: stop level and target level fixed at the signal bar; flat at the session's last bar."""
    n = len(c); ei = np.empty(n, np.int64); nr = np.empty(n); m = 0; t = 0
    while t < n - 2:
        if not sig[t] or not np.isfinite(stop[t]) or not np.isfinite(tgt[t]) or grp[t + 1] != grp[t] or last[t]:
            t += 1; continue
        e = t + 1; px = o[e]; st = stop[t]; tp = tgt[t]; rk = side * (px - st)
        if rk <= 0 or side * (tp - px) <= 0:
            t += 1; continue
        j = e; x = np.nan
        while j < n:
            if j > e and ((side > 0 and o[j] <= st) or (side < 0 and o[j] >= st)):
                x = o[j]; break
            if j > e and ((side > 0 and o[j] >= tp) or (side < 0 and o[j] <= tp)):
                x = o[j]; break
            if (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
                x = st; break
            if (side > 0 and h[j] >= tp) or (side < 0 and l[j] <= tp):
                x = tp; break
            if last[j] or j == n - 1 or grp[j + 1] != grp[j]:
                x = c[j]; break
            j += 1
        if np.isnan(x):
            break
        ei[m] = e; nr[m] = (side * (x - px) - costf[e] * px) / rk; m += 1
        t = j + 1
    return ei[:m], nr[:m]


def value_area(d5):
    """previous-day POC / VAH / VAL from 5-minute bars (volume at the bar's typical price, 0.1-ATR-free price bins)."""
    out = {}
    for day, g in d5.groupby(d5.time.dt.normalize()):
        tp = ((g.high + g.low + g.close) / 3).values; v = g.volume.values.astype(float)
        if v.sum() <= 0 or len(g) < 20:
            continue
        step = max((g.high.max() - g.low.min()) / 50, 1e-9)
        bins = np.clip(np.floor((tp - g.low.min()) / step), 0, 50).astype(int); v = np.where(np.isfinite(v) & (v > 0), v, 0.0); vol = np.bincount(bins, weights=v, minlength=51)
        poc = int(vol.argmax()); lo = hi = poc; tot = vol.sum(); acc = vol[poc]
        while acc < 0.7 * tot and (lo > 0 or hi < len(vol) - 1):
            a = vol[lo - 1] if lo > 0 else -1; b = vol[hi + 1] if hi < len(vol) - 1 else -1
            if a >= b:
                lo -= 1; acc += a
            else:
                hi += 1; acc += b
        base = g.low.min()
        out[day] = (base + (poc + 0.5) * step, base + (hi + 1) * step, base + lo * step)
    return out


def setups(b, d5):
    o, h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("open", "high", "low", "close", "volume"))
    n = len(c); pc = c.shift(1); t = pd.to_datetime(b["time"])
    atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    day = t.dt.normalize().values; hm = (t.dt.hour * 60 + t.dt.minute).values
    tp = (h + l + c) / 3
    cv = v.groupby(day).cumsum().replace(0, np.nan)
    vw = (tp * v).groupby(day).cumsum() / cv
    var = ((tp ** 2) * v).groupby(day).cumsum() / cv - vw ** 2
    sd = np.sqrt(var.clip(lower=0))
    ud = pd.Series(day).drop_duplicates().values
    dh = pd.Series(h.groupby(day).max().values, index=ud); dl = pd.Series(l.groupby(day).min().values, index=ud)
    pdh = pd.Series(day).map(dh.shift(1)).values; pdl = pd.Series(day).map(dl.shift(1)).values
    S = {}                                              # (name, side, exit) -> (signal, stop level, target level)
    ok_t = (hm >= 9 * 60 + 15) & (hm <= 23 * 60)

    def add(name, sd_, sig, stop, R_list=(2.0, 3.0), extra=None):
        sig = np.nan_to_num(sig).astype(bool) & ok_t
        rk = sd_ * (c.values - stop)
        for R in R_list:
            S[(name, sd_, f"{R:g}R")] = (sig, stop, c.values + sd_ * R * np.where(rk > 0, rk, np.nan))
        if extra is not None:
            for k_, tg in extra.items():
                S[(name, sd_, k_)] = (sig, stop, tg)
    # I1 order block + I2 FVG
    for sd_ in (1, -1):
        disp = ((c - c.shift(3)) * sd_ >= 2 * atr) & ((c > h.shift(1).rolling(20).max()) if sd_ > 0 else (c < l.shift(1).rolling(20).min()))
        ob_sig = np.zeros(n, bool); ob_stop = np.full(n, np.nan); fv_sig = np.zeros(n, bool); fv_stop = np.full(n, np.nan)
        for i in np.where(disp.fillna(False).values)[0]:
            k = None
            for j in range(i - 1, max(i - 6, 0), -1):
                if (sd_ > 0 and c.iloc[j] < o.iloc[j]) or (sd_ < 0 and c.iloc[j] > o.iloc[j]):
                    k = j; break
            if k is not None:
                top, bot = h.iloc[k], l.iloc[k]
                for j in range(i + 1, min(i + 31, n)):
                    if day[j] != day[i]:
                        break
                    if (sd_ > 0 and l.iloc[j] <= top and c.iloc[j] > bot) or (sd_ < 0 and h.iloc[j] >= bot and c.iloc[j] < top):
                        ob_sig[j] = True; ob_stop[j] = (bot - 0.1 * atr.iloc[j]) if sd_ > 0 else (top + 0.1 * atr.iloc[j]); break
            for g_ in range(max(i - 2, 2), i + 1):
                gap = (l.iloc[g_] > h.iloc[g_ - 2]) if sd_ > 0 else (h.iloc[g_] < l.iloc[g_ - 2])
                if gap:
                    top, bot = (l.iloc[g_], h.iloc[g_ - 2]) if sd_ > 0 else (l.iloc[g_ - 2], h.iloc[g_])
                    for j in range(i + 1, min(i + 31, n)):
                        if day[j] != day[i]:
                            break
                        if (sd_ > 0 and l.iloc[j] <= top and c.iloc[j] > bot) or (sd_ < 0 and h.iloc[j] >= bot and c.iloc[j] < top):
                            fv_sig[j] = True; fv_stop[j] = (bot - 0.1 * atr.iloc[j]) if sd_ > 0 else (top + 0.1 * atr.iloc[j]); break
                    break
        add("I1_ORDER_BLOCK", sd_, ob_sig, ob_stop); add("I2_FVG", sd_, fv_sig, fv_stop)
    # I3 previous-day sweep and reclaim (fade)
    sw_b = (l.values < pdl) & (c.values > pdl); sw_s = (h.values > pdh) & (c.values < pdh)
    add("I3_PDH_PDL_SWEEP", 1, sw_b, l.values - 0.1 * atr.values, extra={"VWAP": np.where(vw.values > c.values, vw.values, np.nan)})
    add("I3_PDH_PDL_SWEEP", -1, sw_s, h.values + 0.1 * atr.values, extra={"VWAP": np.where(vw.values < c.values, vw.values, np.nan)})
    # I4 VWAP 2-sigma reversion
    lo2, hi2 = (vw - 2 * sd).values, (vw + 2 * sd).values
    b4 = (pd.Series(c.values < lo2).shift(1).fillna(False).astype(bool).values) & (c.values > lo2)
    s4 = (pd.Series(c.values > hi2).shift(1).fillna(False).astype(bool).values) & (c.values < hi2)
    add("I4_VWAP_2SD", 1, b4, l.rolling(3).min().values - 0.1 * atr.values, R_list=(2.0,), extra={"VWAP": vw.values})
    add("I4_VWAP_2SD", -1, s4, h.rolling(3).max().values + 0.1 * atr.values, R_list=(2.0,), extra={"VWAP": vw.values})
    # I5 80 % rule
    VA = value_area(d5)
    vah = pd.Series(day).map({d: VA.get(p) for d, p in zip(ud[1:], ud[:-1])})
    poc_, VAH, VAL = (np.array([x[i] if isinstance(x, tuple) else np.nan for x in vah]) for i in range(3))
    first_open = pd.Series(o.values).groupby(day).transform("first").values
    inside = (c.values < VAH) & (c.values > VAL)
    two_in = inside & pd.Series(inside).shift(1).fillna(False).astype(bool).values & (pd.Series(day).shift(1).values == day)
    day_lo = pd.Series(l.values).groupby(day).cummin().values; day_hi = pd.Series(h.values).groupby(day).cummax().values
    first_b = two_in & (first_open < VAL); first_s = two_in & (first_open > VAH)
    once = lambda s: np.asarray(s, bool) & (pd.Series(np.asarray(s, bool).astype(int)).groupby(day).cumsum().values == 1)
    S[("I5_VALUE_80", 1, "VA edge")] = (once(first_b) & ok_t, day_lo - 0.1 * atr.values, VAH)
    S[("I5_VALUE_80", -1, "VA edge")] = (once(first_s) & ok_t, day_hi + 0.1 * atr.values, VAL)
    # I6 US-open ORB (18:30-19:00 IST)
    us = (hm >= 18 * 60 + 30) & (hm < 19 * 60)
    orh = pd.Series(np.where(us, h.values, np.nan)).groupby(day).transform("max").values
    orl = pd.Series(np.where(us, l.values, np.nan)).groupby(day).transform("min").values
    win6 = (hm >= 19 * 60) & (hm <= 21 * 60 + 30)
    up6 = once(win6 & (c.values > orh)); dn6 = once(win6 & (c.values < orl))
    add("I6_US_OPEN_ORB", 1, up6, orl); add("I6_US_OPEN_ORB", -1, dn6, orh)
    # I7 previous-day high / low break and retest
    for sd_ in (1, -1):
        lev = pdh if sd_ > 0 else pdl
        brk = (c.values > lev) if sd_ > 0 else (c.values < lev)
        brk = once(brk); z = np.zeros(n, bool); st = np.full(n, np.nan)
        for i in np.where(brk)[0]:
            for j in range(i + 1, min(i + 9, n)):
                if day[j] != day[i]:
                    break
                if (sd_ > 0 and l.iloc[j] <= lev[i] + 0.1 * atr.iloc[j] and c.iloc[j] > lev[i]) or \
                        (sd_ < 0 and h.iloc[j] >= lev[i] - 0.1 * atr.iloc[j] and c.iloc[j] < lev[i]):
                    z[j] = True; st[j] = (l.iloc[j] - 0.1 * atr.iloc[j]) if sd_ > 0 else (h.iloc[j] + 0.1 * atr.iloc[j]); break
        add("I7_PDH_RETEST", sd_, z, st)
    every = np.zeros(n, bool); every[::10] = True
    for sd_ in (1, -1):
        add("BENCH_every10", sd_, every, c.values - sd_ * atr.values)
    return S


def main(tf=15, positional=False):
    rows = []
    parts = []
    for g, name in enumerate(MD.NAMES):
        d5 = MD.LM.load(name, "FIVE_MINUTE")
        b = bars(d5, tf); hm = b.time.dt.hour * 60 + b.time.dt.minute
        b = b[(hm >= 9 * 60) & (hm < 23 * 60 + 30)].reset_index(drop=True)
        d5s = d5[(d5.time.dt.hour * 60 + d5.time.dt.minute >= 540) & (d5.time.dt.hour * 60 + d5.time.dt.minute < 1410)]
        S = setups(b, d5s)
        day = b.time.dt.normalize().values
        last = np.r_[day[1:] != day[:-1], True]
        if positional:                                    # positional: carried overnight, flat only at the data end
            last = np.zeros(len(b), bool); last[-1] = True
        grp = g * 10 ** 7 + np.cumsum(b["sw"].fillna(False).astype(bool).values) * 10 ** 4 + pd.factorize(day)[0] % 10 ** 4
        cf = MD.real_cost(name, float(d5.close.iloc[-1])) / float(d5.close.iloc[-1])
        parts.append((name, b, S, last, grp.astype(np.int64), np.full(len(b), cf)))
        print(name, "setups built", flush=True)
    keys = sorted({k for _, _, S, _, _, _ in parts for k in S})
    cat = lambda f: np.concatenate([f(p) for p in parts])
    o, h, l, c = (cat(lambda p, x=x: p[1][x].astype(float).values) for x in ("open", "high", "low", "close"))
    last, grp, cf = cat(lambda p: p[3]), cat(lambda p: p[4]), cat(lambda p: p[5])
    tt, nm = cat(lambda p: p[1]["time"].values), cat(lambda p: np.full(len(p[1]), p[0]))
    for k in keys:
        sig = cat(lambda p: p[2][k][0]); st = cat(lambda p: p[2][k][1].astype(float)); tg = cat(lambda p: np.asarray(p[2][k][2], float))
        ei, nr = sim_lv(o, h, l, c, sig, k[1], st, tg, grp, last, cf)
        T = pd.DataFrame(dict(name=nm[ei], entry=tt[ei], netR=nr))
        rw = dict(setup=k[0], side="BUY" if k[1] > 0 else "SELL", exit=k[2], n=len(T))
        lab = E.periods(T.entry.values, CUTS) if len(T) else np.array([])
        for p, _ in CUTS:
            r = T.netR.values[lab == p] if len(T) else np.array([]); w = r > 0
            rw[f"{p}_n"] = len(r); rw[f"{p}_win"] = round(100 * float(w.mean()), 1) if len(r) else np.nan
            rw[f"{p}_R"] = round(float(r.mean()), 3) if len(r) else np.nan
            rw[f"{p}_PF"] = round(float(r[w].sum() / -r[~w].sum()), 2) if len(r) and (~w).any() else np.nan
        if len(T) > 2:
            dm = T.groupby(pd.to_datetime(T.entry).dt.normalize()).netR.mean()
            rw["t_day"] = round(float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))), 2) if dm.std(ddof=1) > 0 else np.nan
            rw["all_win"] = round(100 * float((T.netR > 0).mean()), 1); rw["all_R"] = round(float(T.netR.mean()), 3)
            rw["metals_R"] = round(float(T.netR[T.name.isin(C.METALS)].mean()), 3); rw["energy_R"] = round(float(T.netR[~T.name.isin(C.METALS)].mean()), 3)
            rw["per_commodity"] = "; ".join(f"{a}:{g_.netR.mean():+.2f}/{100 * (g_.netR > 0).mean():.0f}%({len(g_)})" for a, g_ in T.groupby("name"))
        rw["PASS"] = bool(rw["n"] >= 100 and all(rw[f"{p}_n"] >= 30 and rw[f"{p}_R"] > 0 and (rw[f"{p}_PF"] or 0) >= 1.2 for p, _ in CUTS))
        rows.append(rw)
    L = pd.DataFrame(rows)
    p = E.pvals(L.t_day.fillna(0).values); L["p"] = np.where(L.t_day.notna(), p, np.nan); L["FDR10"] = C.bh(L.p.values)
    L.to_csv(OUT / ("inst.csv" if tf == 15 else f"inst_{tf}m{'_pos' if positional else ''}.csv"), index=False)
    pd.set_option("display.width", 260)
    print(L[["setup", "side", "exit", "n", "all_win", "all_R", "DEV_win", "DEV_R", "VAL_win", "VAL_R", "OOS_win", "OOS_R", "OOS_PF", "t_day", "metals_R", "energy_R", "PASS", "FDR10"]].to_string(index=False))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 15, len(a) > 1 and a[1] == "pos")

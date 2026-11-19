"""MCX-HW – high-win-rate search for MCX (owner 10-Nov: "find a winning 80-90 % accuracy strategy ... all chart patterns,
all candlestick patterns, all trendlines, unlimited trial and error; focus on the last 6-9 months, intraday and positional").

What is searched (both sides, 7 commodities, front-month 5-minute data to 3-Nov-2026):
  timeframes  INTRADAY 15-minute bars (square-off 23:00) · POSITIONAL 60-minute bars (held up to 3 / 8 sessions)
  entries     candlesticks: hammer / shooting star, engulfing, morning / evening star, three soldiers / crows, marubozu,
              inside-bar break, doji at a 20-bar extreme · chart patterns: double bottom / top, inverse / head-and-shoulders,
              1-2-3 higher-low break, flag, range break 20 / 40, squeeze (NR7) break, false-break (spring / upthrust)
              · trendlines: break of the line through the last two pivot highs / lows, bounce off the line
              · indicators: RSI 30/70 cross, VWAP reclaim (intraday), EMA20 pull-back in trend
  filters     60-minute trend: with / against / any
  exits       target 0.25 / 0.5 / 0.75 / 1.0 ATR × stop 1 / 1.5 / 2 / 3 ATR (ATR of the entry timeframe) – small targets with
              wide stops are what produces high win rates; stop checked first in every bar; entry at the next bar's open
  costs       real MCX costs per commodity (fees + 1.5 ticks slippage per side)
Periods: FOCUS = 1-Feb-2026 … 3-Nov-2026 (the owner's last 9 months) · CHECK = everything before (2023 … Jan-2026), never
used to choose anything. A strategy is called a WINNER only if, per commodity or pooled, win rate >= 80 %, net result > 0
after costs and >= 40 trades in FOCUS, and it ALSO has win >= 75 % and net > 0 in CHECK.
python -m research.mcxhw.search"""
import json
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
FOCUS0 = pd.Timestamp("2026-02-01")
TG, SL = (0.25, 0.5, 0.75, 1.0), (1.0, 1.5, 2.0, 3.0)


def bars(d5, minutes):
    t = d5["time"]
    k = (t.dt.hour * 60 + t.dt.minute) // minutes
    g = d5.groupby([t.dt.normalize(), k])
    o = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum"), sw=("switch", "max")).reset_index(drop=True)
    return o


def wilder(x, n):
    return pd.Series(x).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().values


@njit(cache=True)
def structure(h, l, c, atr, k):
    """pivot-based signals (known k bars after the pivot): returns bool arrays
    dbl_b, dbl_t, ihs, hs, hl123, lh123, tl_break_up, tl_break_dn, tl_bounce_up, tl_bounce_dn"""
    n = len(c)
    out = np.zeros((10, n), np.bool_)
    ph = np.zeros(4, np.int64); pl = np.zeros(4, np.int64); nh = 0; nl = 0
    for t in range(2 * k, n):
        p = t - k
        ish = True; isl = True
        for j in range(p - k, p + k + 1):
            if h[j] > h[p]:
                ish = False
            if l[j] < l[p]:
                isl = False
        if ish:
            for q in range(3, 0, -1):
                ph[q] = ph[q - 1]
            ph[0] = p; nh = min(nh + 1, 4)
        if isl:
            for q in range(3, 0, -1):
                pl[q] = pl[q - 1]
            pl[0] = p; nl = min(nl + 1, 4)
        a = atr[t]
        if np.isnan(a) or a <= 0:
            continue
        if nl >= 2 and t - pl[1] <= 80:
            neck = 0.0
            for j in range(pl[1], pl[0] + 1):
                if h[j] > neck:
                    neck = h[j]
            if abs(l[pl[0]] - l[pl[1]]) <= 0.5 * a and c[t] > neck and c[t - 1] <= neck:
                out[0, t] = True                                         # double bottom
            if l[pl[0]] > l[pl[1]] and c[t] > neck and c[t - 1] <= neck:
                out[4, t] = True                                         # 1-2-3 higher low + break
        if nh >= 2 and t - ph[1] <= 80:
            neck = 1e18
            for j in range(ph[1], ph[0] + 1):
                if l[j] < neck:
                    neck = l[j]
            if abs(h[ph[0]] - h[ph[1]]) <= 0.5 * a and c[t] < neck and c[t - 1] >= neck:
                out[1, t] = True
            if h[ph[0]] < h[ph[1]] and c[t] < neck and c[t - 1] >= neck:
                out[5, t] = True
        if nl >= 3 and t - pl[2] <= 120:
            if l[pl[1]] < l[pl[2]] - 0.3 * a and l[pl[1]] < l[pl[0]] - 0.3 * a and abs(l[pl[0]] - l[pl[2]]) <= 1.0 * a:
                neck = 0.0
                for j in range(pl[2], pl[0] + 1):
                    if h[j] > neck:
                        neck = h[j]
                if c[t] > neck and c[t - 1] <= neck:
                    out[2, t] = True                                     # inverse head and shoulders
        if nh >= 3 and t - ph[2] <= 120:
            if h[ph[1]] > h[ph[2]] + 0.3 * a and h[ph[1]] > h[ph[0]] + 0.3 * a and abs(h[ph[0]] - h[ph[2]]) <= 1.0 * a:
                neck = 1e18
                for j in range(ph[2], ph[0] + 1):
                    if l[j] < neck:
                        neck = l[j]
                if c[t] < neck and c[t - 1] >= neck:
                    out[3, t] = True
        if nh >= 2 and ph[0] > ph[1] and t - ph[1] <= 120:               # trendline through the last two pivot highs
            s = (h[ph[0]] - h[ph[1]]) / (ph[0] - ph[1])
            if s < 0:
                v = h[ph[0]] + s * (t - ph[0]); v1 = h[ph[0]] + s * (t - 1 - ph[0])
                if c[t] > v and c[t - 1] <= v1:
                    out[6, t] = True                                     # break of a falling trendline -> buy
                if h[t] >= v - 0.1 * a and c[t] < v and c[t] < (h[t] + l[t]) / 2:
                    out[9, t] = True                                     # rejection at a falling trendline -> sell
        if nl >= 2 and pl[0] > pl[1] and t - pl[1] <= 120:
            s = (l[pl[0]] - l[pl[1]]) / (pl[0] - pl[1])
            if s > 0:
                v = l[pl[0]] + s * (t - pl[0]); v1 = l[pl[0]] + s * (t - 1 - pl[0])
                if c[t] < v and c[t - 1] >= v1:
                    out[7, t] = True                                     # break of a rising trendline -> sell
                if l[t] <= v + 0.1 * a and c[t] > v and c[t] > (h[t] + l[t]) / 2:
                    out[8, t] = True                                     # bounce off a rising trendline -> buy
    return out


def signals(b, intraday):
    o, h, l, c, v = (b[x].values.astype(float) for x in ("open", "high", "low", "close", "volume"))
    O, H, L, C = (pd.Series(x) for x in (o, h, l, c))
    pc = C.shift(1)
    atr = wilder(np.maximum(H - L, np.maximum((H - pc).abs(), (L - pc).abs())).values, 14)
    A = pd.Series(atr)
    body = (C - O).abs(); rng = (H - L).replace(0, np.nan)
    lw = np.minimum(O, C) - L; uw = H - np.maximum(O, C)
    up, dn = C > O, C < O
    ll20, hh20 = L.shift(1).rolling(20).min(), H.shift(1).rolling(20).max()
    hh40, ll40 = H.shift(1).rolling(40).max(), L.shift(1).rolling(40).min()
    d = C.diff()
    rsi = 100 - 100 / (1 + pd.Series(wilder(d.clip(lower=0).values, 14)) / pd.Series(wilder((-d).clip(lower=0).values, 14)).replace(0, np.nan))
    e20, e50 = C.ewm(span=20, adjust=False).mean(), C.ewm(span=50, adjust=False).mean()
    S = {}
    S["hammer", 1] = (lw >= 2 * body) & ((C - L) / rng >= 0.6) & (L <= ll20 + 0.5 * A)
    S["shooting_star", -1] = (uw >= 2 * body) & ((C - L) / rng <= 0.4) & (H >= hh20 - 0.5 * A)
    S["engulfing", 1] = up & dn.shift(1) & (C >= O.shift(1)) & (O <= C.shift(1))
    S["engulfing", -1] = dn & up.shift(1) & (C <= O.shift(1)) & (O >= C.shift(1))
    small1 = body.shift(1) <= 0.3 * rng.shift(1)
    S["morning_star", 1] = dn.shift(2) & (body.shift(2) >= 0.6 * rng.shift(2)) & small1 & up & (C > (O.shift(2) + C.shift(2)) / 2)
    S["evening_star", -1] = up.shift(2) & (body.shift(2) >= 0.6 * rng.shift(2)) & small1 & dn & (C < (O.shift(2) + C.shift(2)) / 2)
    S["three_soldiers", 1] = up & up.shift(1) & up.shift(2) & (C > C.shift(1)) & (C.shift(1) > C.shift(2)) & (body >= 0.5 * rng)
    S["three_crows", -1] = dn & dn.shift(1) & dn.shift(2) & (C < C.shift(1)) & (C.shift(1) < C.shift(2)) & (body >= 0.5 * rng)
    S["marubozu", 1] = up & (body >= 0.85 * rng) & (rng >= 1.2 * A)
    S["marubozu", -1] = dn & (body >= 0.85 * rng) & (rng >= 1.2 * A)
    inside1 = (H.shift(1) <= H.shift(2)) & (L.shift(1) >= L.shift(2))
    S["inside_break", 1] = inside1 & (C > H.shift(1)); S["inside_break", -1] = inside1 & (C < L.shift(1))
    doji = body <= 0.1 * rng
    S["doji_extreme", 1] = doji.shift(1) & (L.shift(1) <= ll20.shift(1)) & (C > H.shift(1))
    S["doji_extreme", -1] = doji.shift(1) & (H.shift(1) >= hh20.shift(1)) & (C < L.shift(1))
    S["range_break20", 1] = (C > hh20) & (C.shift(1) <= hh20.shift(1)); S["range_break20", -1] = (C < ll20) & (C.shift(1) >= ll20.shift(1))
    S["range_break40", 1] = (C > hh40) & (C.shift(1) <= hh40.shift(1)); S["range_break40", -1] = (C < ll40) & (C.shift(1) >= ll40.shift(1))
    nr7 = (rng.shift(1) <= rng.shift(1).rolling(7).min())
    S["nr7_break", 1] = nr7 & (C > H.shift(1)); S["nr7_break", -1] = nr7 & (C < L.shift(1))
    S["spring", 1] = (L < ll20) & (C > ll20) & ((C - L) / rng >= 0.6)
    S["upthrust", -1] = (H > hh20) & (C < hh20) & ((C - L) / rng <= 0.4)
    imp_up = (C.shift(5) - C.shift(10)) >= 2.5 * A.shift(5); imp_dn = (C.shift(10) - C.shift(5)) >= 2.5 * A.shift(5)
    tight = (H.shift(1).rolling(5).max() - L.shift(1).rolling(5).min()) <= 1.5 * A.shift(1)
    S["flag", 1] = imp_up & tight & (C > H.shift(1).rolling(5).max()); S["flag", -1] = imp_dn & tight & (C < L.shift(1).rolling(5).min())
    S["rsi_cross", 1] = (rsi > 30) & (rsi.shift(1) <= 30); S["rsi_cross", -1] = (rsi < 70) & (rsi.shift(1) >= 70)
    S["ema20_pullback", 1] = (e20 > e50) & (L <= e20) & (C > e20) & up
    S["ema20_pullback", -1] = (e20 < e50) & (H >= e20) & (C < e20) & dn
    if intraday:
        day = b["time"].dt.normalize()
        tp = (H + L + C) / 3
        vw = (tp * v).groupby(day.values).cumsum() / pd.Series(v).groupby(day.values).cumsum().replace(0, np.nan)
        below = (C.shift(1) < vw.shift(1)).rolling(4).min().fillna(0).astype(bool)
        above = (C.shift(1) > vw.shift(1)).rolling(4).min().fillna(0).astype(bool)
        S["vwap_reclaim", 1] = below & (C > vw); S["vwap_reclaim", -1] = above & (C < vw)
    st = structure(h, l, c, atr, 3)
    for i, (nm, sd) in enumerate((("double_bottom", 1), ("double_top", -1), ("inv_head_shoulders", 1), ("head_shoulders", -1), ("hl_123", 1),
                                  ("lh_123", -1), ("trendline_break", 1), ("trendline_break", -1), ("trendline_bounce", 1), ("trendline_reject", -1))):
        S[nm, sd] = pd.Series(st[i])
    tr = np.where((e20 > e50) & (C > e50), 1, np.where((e20 < e50) & (C < e50), -1, 0))
    return {k: np.nan_to_num(np.asarray(x, dtype=float)).astype(np.bool_) for k, x in S.items()}, atr, tr


@njit(cache=True)
def sim(o, h, l, c, sig, side, atr, tg, sl, grp, hold, cost):
    """grp: session id (intraday: day; positional: 0) – a trade never crosses grp; hold: max bars. Returns entry idx, net (price units), win flag, in ATR."""
    n = len(c)
    ei = np.empty(n, np.int64); net = np.empty(n); R = np.empty(n)
    m = 0; t = 0
    while t < n - 2:
        if not sig[t] or np.isnan(atr[t]) or atr[t] <= 0 or grp[t + 1] != grp[t]:
            t += 1; continue
        e = t + 1; px = o[e]; a = atr[t]
        st = px - side * sl * a; tp = px + side * tg * a
        j = e; x = np.nan
        while j < n:
            if grp[j] != grp[e]:
                x = c[j - 1]; j -= 1; break
            if j > e and ((side > 0 and o[j] <= st) or (side < 0 and o[j] >= st)):
                x = o[j]; break
            if (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
                x = st; break
            if (side > 0 and h[j] >= tp) or (side < 0 and l[j] <= tp):
                x = tp; break
            if j - e + 1 >= hold or j == n - 1 or grp[j + 1] != grp[j]:
                x = c[j]; break
            j += 1
        if np.isnan(x):
            break
        ei[m] = e; net[m] = side * (x - px) - cost; R[m] = net[m] / a
        m += 1
        t = j + 1
    return ei[:m], net[:m], R[:m]


def stats(tm, net, R, mult, mask):
    x, r = net[mask], R[mask]
    if len(x) == 0:
        return dict(n=0)
    w = x > 0
    gp, gl = x[w].sum(), -x[~w].sum()
    mx = cur = 0
    for z in w:
        cur = 0 if z else cur + 1; mx = max(mx, cur)
    return dict(n=int(len(x)), win=round(100 * w.mean(), 1), net_atr=round(float(r.mean()), 3), rs_lot=round(float(x.mean() * mult)),
                total_rs=round(float(x.sum() * mult)), PF=round(float(gp / gl), 2) if gl > 0 else 99.0, max_loss_streak=int(mx),
                worst_rs=round(float(x.min() * mult)))


def main():
    t0 = time.time()
    rows = []
    for name in MD.NAMES:
        d5 = MD.LM.load(name, "FIVE_MINUTE")
        mult = MD.REG[name]["mult"]
        cost = MD.real_cost(name, float(d5.close.iloc[-1]))
        for mode, minutes in (("INTRADAY", 15), ("POSITIONAL", 60)):
            b = bars(d5, minutes)
            S, atr, tr = signals(b, mode == "INTRADAY")
            o, h, l, c = (b[x].values.astype(float) for x in ("open", "high", "low", "close"))
            day = b["time"].dt.normalize().values.astype("datetime64[D]").astype(np.int64)
            hm = (b["time"].dt.hour * 60 + b["time"].dt.minute).values
            sw = b["sw"].fillna(False).astype(bool).values
            tm = b["time"].values
            if mode == "INTRADAY":
                grp = day.copy(); ok = (hm >= 9 * 60 + 30) & (hm <= 22 * 60)           # entries 09:30-22:00, out by the session end
                holds = (400,)
            else:
                grp = np.cumsum(sw).astype(np.int64); ok = np.ones(len(b), bool)        # never held across a contract switch
                holds = (3 * 15, 8 * 15)
            for (nm, sd), sig in S.items():
                for flt in ("any", "with", "against"):
                    s2 = sig & ok & (True if flt == "any" else (tr == sd) if flt == "with" else (tr == -sd))
                    if s2.sum() < 30:
                        continue
                    for hold in holds:
                        for tg in TG:
                            for sl in SL:
                                ei, net, R = sim(o, h, l, c, s2, sd, atr, tg, sl, grp, hold, cost)
                                if len(ei) < 30:
                                    continue
                                te = tm[ei]
                                f = te >= np.datetime64(FOCUS0)
                                row = dict(commodity=name, mode=mode, pattern=nm, side="BUY" if sd > 0 else "SELL", trend=flt,
                                           target_atr=tg, stop_atr=sl, hold_bars=hold if mode == "POSITIONAL" else 0)
                                row.update({f"F_{k}": v for k, v in stats(te, net, R, mult, f).items()})
                                row.update({f"C_{k}": v for k, v in stats(te, net, R, mult, ~f).items()})
                                rows.append(row)
        print(f"{name}: {len(rows):,} variants so far ({time.time() - t0:.0f}s)", flush=True)
    L = pd.DataFrame(rows)
    L["focus_ok"] = (L.F_n >= 40) & (L.F_win >= 80) & (L.F_net_atr > 0)
    L["winner"] = L.focus_ok & (L.C_n >= 60) & (L.C_win >= 75) & (L.C_net_atr > 0)
    L.to_csv(OUT / "mcxhw_all.csv.gz", index=False)
    L[L.focus_ok].sort_values(["winner", "F_total_rs"], ascending=False).to_csv(OUT / "mcxhw_focus_candidates.csv", index=False)
    summ = dict(variants=int(len(L)), focus_80_any_profit=int(((L.F_n >= 40) & (L.F_win >= 80)).sum()), focus_80_profitable=int(L.focus_ok.sum()),
                winners_also_in_check=int(L.winner.sum()), seconds=round(time.time() - t0),
                by_mode={m: dict(variants=int(len(g)), focus_ok=int(g.focus_ok.sum()), winners=int(g.winner.sum())) for m, g in L.groupby("mode")})
    json.dump(summ, open(OUT / "mcxhw_summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()

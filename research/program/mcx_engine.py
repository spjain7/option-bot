"""MCXE v2 (MCXE-002, 6-Nov-2026) – corrections vs v1 (results/mcxe_v1_PROVISIONAL_*): stable seeds + dataset fingerprints,
no independent random family (matched controls live in mcx_controls.py), ONE position at a time per strategy stream,
conservative stop-entry (trigger and invalidation in the same 5-min bar = no trade), SWEEP split into BOS / CHOCH,
CHANNEL breaks, combination filters (structure-aligned, volume, both), quarter-level output for walk-forward selection.

MCXE – MCX intraday STRATEGY ENGINE (research). One framework, many families (owner directive 6-Nov: "build the engine,
not isolated experiments"). Every family is a DETECTOR that turns candles into objective SETUPS
    (fam, sub, side, tf, signal_end_time, trigger_level, invalidation_level, context...)
and one shared SIMULATOR executes them on 5-minute candles with identical entry / stop / exit options and costs.

Detectors (swings are pivots of +-3 candles, usable only 3 candles later = no look-ahead):
  SWEEP   liquidity sweep: candle trades beyond a level (prev-day H/L, last confirmed swing, equal highs/lows within 0.1 ATR)
          and CLOSES back inside -> REV (reverse) · BOS (reverse only after a close through the latest opposite swing within
          8 candles = sweep + break of structure)
  SR      support / resistance zones = >= 2 confirmed swing pivots within 0.25 ATR in the last 100 candles:
          BRK (close through the zone) · RET (after a break, back to the zone within 10 candles and closes beyond = role
          reversal) · REJ (touch + rejection candle: wick >= 50 % and close in the far third)
  TL      trendline through the last two confirmed swing highs (falling) / lows (rising): BRK (close through the line) ·
          RET (after a break, touches the line and closes beyond) · REJ (touch and rejection candle back with the line)
  MS      market structure from confirmed swings: BOS (trend continuation: close beyond the last swing in the trend
          direction while HH+HL / LH+LL) · CHOCH (close through the last swing AGAINST the prevailing structure)
  CDL     candle at a level (prev-day H/L, VWAP, SR zone within 0.3 ATR): bullish / bearish ENGULF, PIN bar
  CMP     compression: FLAG (impulse >= 2.5 ATR in <= 5 candles, 3-8 candle pause <= 1.2 ATR, break of the pause in the
          impulse direction) · TRI (last two swing highs falling and lows rising, close beyond)
  DTC     day-trend continuation (reference, already in shadow)
Execution options: entry {NXT next 5m open after the signal candle, STP stop order at the trigger within 3 signal candles,
cancelled if the invalidation trades first} x stop {STR invalidation -/+ 0.1 ATR (0.3-3 ATR), ATR 1.5 x ATR(tf)} x exit
{2R, 3R, EOD square-off 23:00, TRL 2 x ATR(tf) trailing}. No entries after 22:00. Costs: realistic (fees + 1.5 ticks/side)
and 2 x stress. Filters (applied after, on the signal candle): trend60 {any, with, against}, volume >= 1.5x.
Periods: DEV 2025-11-06…2026-06-30 (choose) · VALID 2026-07-01…11-03 · HIST 2023…2025-11-05 (never used to choose).
python research/program/mcx_engine.py"""
import sys
import hashlib
import json
import time
import zlib
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
TFS = {"15m": 15, "30m": 30, "60m": 60}
K = 3                                                     # pivot half-width
SR_LB, SR_TOL, SR_MIN = 100, 0.25, 2                      # S/R zone: lookback candles, pivot tolerance (ATR), min pivots
SEED = 20261106
FILTS = ("any", "vol", "trend", "ms", "ms+vol")
EXECS = list(product((0, 1), (0, 1), (2.0, 3.0, 0.0, -1.0)))
TAG = "mcxe2"


def fingerprint(d5):
    h = hashlib.sha256()
    h.update(f"{len(d5)}|{d5.time.iat[0]}|{d5.time.iat[-1]}|{float(d5.close.sum()):.4f}|{float(d5.volume.sum()):.1f}".encode())
    return h.hexdigest()[:16]


# ── detectors ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def pivots(h, l, k=K):
    n = len(h); ph = np.zeros(n, bool); pl = np.zeros(n, bool)
    for j in range(k, n - k):
        if h[j] == h[j - k:j + k + 1].max():
            ph[j] = True
        if l[j] == l[j - k:j + k + 1].min():
            pl[j] = True
    return ph, pl


def detect(f, tf, dd, sw_days):
    """f: candles of timeframe tf with columns time/open/high/low/close/volume/day/m/atr (+ vwap for 15m)."""
    o, h, l, c, v = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "volume"))
    a = f.atr.values; t = f.time.values; day = f.day.values; mins = f.m.values; n = len(f)
    end = t + np.timedelta64(TFS[tf], "m")
    rng = np.where(h - l > 0, h - l, np.nan); pos = (c - l) / rng
    uw, lw, body = h - np.maximum(o, c), np.minimum(o, c) - l, np.abs(c - o)
    volx = v / pd.Series(v).rolling(20, min_periods=10).mean().shift(1).values
    vw = f["vwap"].values if "vwap" in f else np.full(n, np.nan)
    ph, pl = pivots(h, l)
    PDH = pd.Series(day).map(dd.ph).values; PDL = pd.Series(day).map(dd.pl).values
    out = []
    sh, sl = [], []                                        # confirmed swings (index, price)
    zone_hits = []
    tl_state = {1: None, -1: None}                         # broken trendline awaiting retest: (level fn params, bar)
    sr_broken = []                                         # (zone level, side, bar)
    sweep_wait = []                                        # (side, bar, extreme) awaiting BOS
    flag = None

    ms_state = 0

    def add(fam, sub, side, i, trig, inv):
        if day[i] in sw_days or mins[i] + TFS[tf] > 22 * 60 or not a[i] > 0 or mins[i] < 9 * 60:
            return
        out.append((fam, sub, side, end[i], trig, inv, a[i], volx[i], i, ms_state))

    for i in range(20, n):
        if not a[i] > 0:
            continue
        j = i - K                                          # pivot at j is confirmed now
        if ph[j]:
            sh.append((j, h[j]))
        if pl[j]:
            sl.append((j, l[j]))
        sh = sh[-12:]; sl = sl[-12:]
        A = a[i]
        if len(sh) >= 2 and len(sl) >= 2:
            ms_state = 1 if (sh[-1][1] > sh[-2][1] and sl[-1][1] > sl[-2][1]) else (-1 if (sh[-1][1] < sh[-2][1] and sl[-1][1] < sl[-2][1]) else 0)
        # ---------- SWEEP ----------
        levels = []
        if PDH[i] == PDH[i]:
            levels += [(PDH[i], -1, "PD"), (PDL[i], 1, "PD")]
        if sh:
            levels.append((sh[-1][1], -1, "SW"))
        if sl:
            levels.append((sl[-1][1], 1, "SW"))
        if len(sh) >= 2 and abs(sh[-1][1] - sh[-2][1]) <= 0.1 * A:
            levels.append((max(sh[-1][1], sh[-2][1]), -1, "EQ"))
        if len(sl) >= 2 and abs(sl[-1][1] - sl[-2][1]) <= 0.1 * A:
            levels.append((min(sl[-1][1], sl[-2][1]), 1, "EQ"))
        for lvl, s, kind in levels:
            if s < 0 and h[i] > lvl and c[i] < lvl:
                add("SWEEP", f"REV_{kind}", -1, i, l[i], h[i]); sweep_wait.append((-1, i, h[i], ms_state))
            if s > 0 and l[i] < lvl and c[i] > lvl:
                add("SWEEP", f"REV_{kind}", 1, i, h[i], l[i]); sweep_wait.append((1, i, l[i], ms_state))
        keep = []
        for s, b, ext, ms0 in sweep_wait:
            if i - b > 8:
                continue
            tag = "CHOCH" if ms0 == -s else "BOS"          # reversal against the prevailing structure = change of character
            if s < 0 and sl and c[i] < sl[-1][1] and i > b:
                add("SWEEP", tag, -1, i, l[i], ext); continue
            if s > 0 and sh and c[i] > sh[-1][1] and i > b:
                add("SWEEP", tag, 1, i, h[i], ext); continue
            keep.append((s, b, ext, ms0))
        sweep_wait = keep[-6:]
        # ---------- SR zones ----------
        piv = [p for p in sh if i - p[0] <= SR_LB] + [p for p in sl if i - p[0] <= SR_LB]
        zones = []
        for x in range(len(piv)):
            cl = [p for p in piv if abs(p[1] - piv[x][1]) <= SR_TOL * A]
            if len(cl) >= SR_MIN:
                zones.append(np.mean([p[1] for p in cl]))
        zones = sorted(set(round(z / (SR_TOL * A)) * SR_TOL * A for z in zones)) if zones else []
        for z in zones:
            if c[i - 1] <= z < c[i]:
                add("SR", "BRK", 1, i, h[i], z - 0.25 * A); sr_broken.append((z, 1, i))
            if c[i - 1] >= z > c[i]:
                add("SR", "BRK", -1, i, l[i], z + 0.25 * A); sr_broken.append((z, -1, i))
            if l[i] > z and h[i] >= z - 0.1 * A and uw[i] >= 0.5 * rng[i] and pos[i] <= 0.34 and c[i] < z:
                pass
            if h[i] >= z - 0.1 * A and h[i] <= z + 0.5 * A and c[i] < z and uw[i] >= 0.5 * (rng[i] or 1) and pos[i] <= 0.34:
                add("SR", "REJ", -1, i, l[i], h[i])
            if l[i] <= z + 0.1 * A and l[i] >= z - 0.5 * A and c[i] > z and lw[i] >= 0.5 * (rng[i] or 1) and pos[i] >= 0.66:
                add("SR", "REJ", 1, i, h[i], l[i])
        nb = []
        for z, s, b in sr_broken:
            if i - b > 10:
                continue
            if i > b + 1 and ((s > 0 and l[i] <= z + 0.1 * A and c[i] > z) or (s < 0 and h[i] >= z - 0.1 * A and c[i] < z)):
                add("SR", "RET", s, i, h[i] if s > 0 else l[i], l[i] if s > 0 else h[i]); continue
            nb.append((z, s, b))
        sr_broken = nb[-8:]
        # ---------- trendlines ----------
        for s, pts in ((1, sh), (-1, sl)):                 # s=+1: falling line through swing highs, break UP
            if len(pts) < 2:
                continue
            (j1, p1), (j2, p2) = pts[-2], pts[-1]
            if j2 == j1 or (s > 0 and p2 >= p1) or (s < 0 and p2 <= p1):
                continue
            slope = (p2 - p1) / (j2 - j1); line = p2 + slope * (i - j2); line_prev = p2 + slope * (i - 1 - j2)
            if (s > 0 and c[i - 1] <= line_prev and c[i] > line) or (s < 0 and c[i - 1] >= line_prev and c[i] < line):
                add("TL", "BRK", s, i, h[i] if s > 0 else l[i], l[i] if s > 0 else h[i]); tl_state[s] = (j2, p2, slope, i)
            elif (s > 0 and h[i] >= line - 0.1 * A and c[i] < line and uw[i] >= 0.5 * (rng[i] or 1)):
                add("TL", "REJ", -1, i, l[i], h[i])
            elif (s < 0 and l[i] <= line + 0.1 * A and c[i] > line and lw[i] >= 0.5 * (rng[i] or 1)):
                add("TL", "REJ", 1, i, h[i], l[i])
            stt = tl_state[s]
            if stt and i - stt[3] <= 10 and i > stt[3] + 1:
                ln = stt[1] + stt[2] * (i - stt[0])
                if (s > 0 and l[i] <= ln + 0.1 * A and c[i] > ln) or (s < 0 and h[i] >= ln - 0.1 * A and c[i] < ln):
                    add("TL", "RET", s, i, h[i] if s > 0 else l[i], l[i] if s > 0 else h[i]); tl_state[s] = None
        # ---------- channels: line through the last two swing highs (lows) + parallel through the extreme in between ----------
        for base, pts, opp in ((1, sh, l), (-1, sl, h)):
            if len(pts) < 2:
                continue
            (j1, p1), (j2, p2) = pts[-2], pts[-1]
            if j2 <= j1:
                continue
            slope = (p2 - p1) / (j2 - j1)
            if base > 0:                                   # upper line through highs, lower parallel through the lowest low since j1
                off = min(opp[jj] - (p1 + slope * (jj - j1)) for jj in range(j1, i))
                up_l, lo_l = p1 + slope * (i - j1), p1 + slope * (i - j1) + off
                up_p, lo_p = up_l - slope, lo_l - slope
            else:                                          # lower line through lows, upper parallel through the highest high since j1
                off = max(opp[jj] - (p1 + slope * (jj - j1)) for jj in range(j1, i))
                lo_l, up_l = p1 + slope * (i - j1), p1 + slope * (i - j1) + off
                up_p, lo_p = up_l - slope, lo_l - slope
            width = up_l - lo_l
            if not (1.0 * A <= width <= 6.0 * A):
                continue
            if c[i - 1] <= up_p and c[i] > up_l:
                add("CH", "BRKUP" if slope > 0 else "BRKUP_F", 1, i, h[i], lo_l if width <= 3 * A else l[i])
            if c[i - 1] >= lo_p and c[i] < lo_l:
                add("CH", "BRKDN" if slope < 0 else "BRKDN_R", -1, i, l[i], up_l if width <= 3 * A else h[i])
        # ---------- market structure ----------
        if len(sh) >= 2 and len(sl) >= 2:
            up = sh[-1][1] > sh[-2][1] and sl[-1][1] > sl[-2][1]
            dn = sh[-1][1] < sh[-2][1] and sl[-1][1] < sl[-2][1]
            if c[i - 1] <= sh[-1][1] < c[i]:
                add("MS", "BOS" if up else ("CHOCH" if dn else "BRK"), 1, i, h[i], sl[-1][1])
            if c[i - 1] >= sl[-1][1] > c[i]:
                add("MS", "BOS" if dn else ("CHOCH" if up else "BRK"), -1, i, l[i], sh[-1][1])
        # ---------- candles at levels ----------
        lv = [x for x in (PDH[i], PDL[i], vw[i]) if x == x] + zones
        near = any(abs(c[i] - x) <= 0.3 * A or (l[i] <= x <= h[i]) for x in lv)
        if near and rng[i] == rng[i]:
            if c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body[i] > body[i - 1]:
                add("CDL", "ENGULF", 1, i, h[i], l[i])
            if c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1] and body[i] > body[i - 1]:
                add("CDL", "ENGULF", -1, i, l[i], h[i])
            if lw[i] >= 2 * body[i] and lw[i] >= 0.6 * rng[i] and pos[i] >= 0.6:
                add("CDL", "PIN", 1, i, h[i], l[i])
            if uw[i] >= 2 * body[i] and uw[i] >= 0.6 * rng[i] and pos[i] <= 0.4:
                add("CDL", "PIN", -1, i, l[i], h[i])
        # ---------- compression ----------
        for L_ in range(3, 9):
            b0 = i - L_
            if b0 - 5 < 0:
                break
            imp_hi, imp_lo = h[b0 - 5:b0].max(), l[b0 - 5:b0].min()
            pause_hi, pause_lo = h[b0:i].max(), l[b0:i].min()
            if imp_hi - imp_lo >= 2.5 * A and pause_hi - pause_lo <= 1.2 * A:
                upimp = c[b0 - 1] > o[b0 - 5]
                if upimp and c[i] > pause_hi and pause_lo > imp_lo + 0.5 * (imp_hi - imp_lo):
                    add("CMP", "FLAG", 1, i, h[i], pause_lo); break
                if not upimp and c[i] < pause_lo and pause_hi < imp_hi - 0.5 * (imp_hi - imp_lo):
                    add("CMP", "FLAG", -1, i, l[i], pause_hi); break
        if len(sh) >= 2 and len(sl) >= 2 and sh[-1][1] < sh[-2][1] and sl[-1][1] > sl[-2][1]:
            if c[i - 1] <= sh[-1][1] < c[i]:
                add("CMP", "TRI", 1, i, h[i], sl[-1][1])
            if c[i - 1] >= sl[-1][1] > c[i]:
                add("CMP", "TRI", -1, i, l[i], sh[-1][1])
    return out


# ── simulator (5-minute execution) ────────────────────────────────────────────────────────────────────────────────────
@njit(cache=True)
def sim(o, h, l, c, act, side, trig, inv, atr, eod, last_entry, entry, stop, exitc, cost):
    """setups must be sorted by act. ONE position at a time: a setup activating before the previous trade's exit bar is
    skipped. Returns (K, 4): gross R, cost R, entry bar, exit bar (NaN = no trade)."""
    K_ = len(act); res = np.full((K_, 4), np.nan)
    busy = -1
    for k in range(K_):
        i0, s, L, V, a, ie = act[k], side[k], trig[k], inv[k], atr[k], eod[k]
        if i0 <= busy:
            continue
        j = -1; e = 0.0
        if entry == 0:
            j = i0; e = o[i0]
        else:
            for t in range(i0, last_entry[k] + 1):
                hitV = (s > 0 and l[t] < V) or (s < 0 and h[t] > V)
                hitL = (s > 0 and h[t] > L) or (s < 0 and l[t] < L)
                if hitV:                                   # invalidation first, or both in one bar (order unknown) -> no trade
                    break
                if hitL:
                    j = t; e = max(L, o[t]) if s > 0 else min(L, o[t]); break
        if j < 0 or j >= ie:
            continue
        if s * (e - L) > 0.5 * a and entry == 1:
            continue
        st = (V - s * 0.1 * a) if stop == 0 else (e - s * 1.5 * a)
        R = s * (e - st)
        if not (R > 0.3 * a and R < 3.0 * a):
            continue
        tgt = e + s * exitc * R if exitc > 0 else 0.0
        best = e; px = c[ie]; tx = ie
        for t in range(j, ie + 1):
            if t > j and ((s > 0 and o[t] <= st) or (s < 0 and o[t] >= st)):
                px = o[t]; tx = t; break
            if (s > 0 and l[t] <= st) or (s < 0 and h[t] >= st):
                px = st; tx = t; break
            if exitc > 0 and t > j and ((s > 0 and h[t] >= tgt) or (s < 0 and l[t] <= tgt)):
                px = tgt; tx = t; break
            if exitc == -1:
                best = max(best, h[t]) if s > 0 else min(best, l[t])
                ns = best - s * 2.0 * a
                if (s > 0 and ns > st) or (s < 0 and ns < st):
                    st = ns
        res[k, 0] = s * (px - e) / R; res[k, 1] = cost[j] / R; res[k, 2] = j; res[k, 3] = tx
        busy = tx
    return res


def setups_for(name, P):
    """all setups of one commodity, all timeframes, activation mapped to 5-min bars (sorted). Also used by mcx_controls."""
    d5, f15, f30, f60, dd, sw = P
    t5 = d5.time.values
    eod_day = d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1])
    tr60_15 = dict(zip(f15.time + pd.Timedelta(minutes=15), f15.tr60))
    out = []
    for tf, f in {"15m": f15, "30m": f30, "60m": f60}.items():
        S = detect(f.reset_index(drop=True), tf, dd, sw)
        if not S:
            continue
        D = pd.DataFrame(S, columns=["fam", "sub", "side", "end", "trig", "inv", "atr", "volx", "i", "ms"])
        D["tf"] = tf
        D["act"] = np.searchsorted(t5, D.end.values)
        D = D[D.act < len(d5)]
        D["day"] = d5.day.values[D.act.values]
        D = D[D.day.isin(eod_day.index) & (pd.to_datetime(D.end).dt.normalize() == D.day)]
        D["eod"] = D.day.map(eod_day).astype(int)
        D = D[D.act < D.eod]
        D["last_entry"] = np.minimum(D.act + 3 * TFS[tf] // 5 - 1, D.eod - 1)
        D["tr60"] = pd.to_datetime(D.end).map(lambda x: tr60_15.get(x, 0)).values if tf != "60m" else 0
        out.append(D)
    D = pd.concat(out, ignore_index=True).sort_values("act", kind="stable").reset_index(drop=True)
    D["risk_atr"] = (D.trig - D.inv).abs() / D.atr
    # MCXE-003 day-trend context at activation (last completed 5-min bar): beyond session VWAP and >= 0.3 x daily ATR beyond
    # the day's 09:00 open in the setup direction (the condition behind the only surviving strategy, MCXD-002)
    prev = np.maximum(D.act.values - 1, 0)
    cl, vw = d5.close.values[prev], d5.vwap.values[prev]
    dopen = d5.groupby("day").open.transform("first").values[prev]
    datr = D.day.map(dd.atr).values
    sgn = D.side.values
    D["dayctx"] = ((sgn * (cl - vw) > 0) & (sgn * (cl - dopen) >= 0.3 * datr)).astype(int)
    return D


def apply_filter(D, flt):
    if flt == "vol":
        return D[D.volx >= 1.5]
    if flt == "trend":
        return D[(D.tf != "60m") & (D.tr60 == D.side)]
    if flt == "ms":
        return D[D.ms == D.side]
    if flt == "ms+vol":
        return D[(D.ms == D.side) & (D.volx >= 1.5)]
    if flt == "day":
        return D[D.dayctx == 1]
    if flt == "day+ms":
        return D[(D.dayctx == 1) & (D.ms == D.side)]
    if flt == "noday":
        return D[D.dayctx == 0]
    return D


def simulate(D, d5arr, cost, en, sp, ex):
    o, h, l, c = d5arr
    a = [D.act.values.astype(np.int64), D.side.values.astype(np.int64), D.trig.values.astype(np.float64), D.inv.values.astype(np.float64),
         D.atr.values.astype(np.float64), D.eod.values.astype(np.int64), D.last_entry.values.astype(np.int64)]
    r = sim(o, h, l, c, *a, en, sp, ex, cost)
    m = ~np.isnan(r[:, 0])
    return D[m].assign(gross=r[m, 0], costR=r[m, 1], j=r[m, 2].astype(int), x=r[m, 3].astype(int))


def run_name(name):
    P = MD.prep(name)
    d5 = P[0]
    d5arr = tuple(d5[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
    cost = np.array([MD.real_cost(name, p) for p in d5arr[3]])
    D = setups_for(name, P)
    meta = dict(name=name, fingerprint=fingerprint(d5), bars=len(d5), first=str(d5.time.iat[0]), last=str(d5.time.iat[-1]),
                setups=int(len(D)), unique_signals=int(D.drop_duplicates(["tf", "fam", "sub", "side", "i"]).shape[0]))
    rows = []
    for (tf, fam, sub, sd), G in D.groupby(["tf", "fam", "sub", "side"]):
        for flt in FILTS:
            F = apply_filter(G, flt)
            if len(F) < 10:
                continue
            for en, sp, ex in EXECS:
                X = simulate(F, d5arr, cost, en, sp, ex)
                if X.empty:
                    continue
                X = X.assign(net=X.gross - X.costR, q=pd.PeriodIndex(X.day, freq="Q").astype(str))
                eq = X.net.cumsum().values
                dd_ = float((np.maximum.accumulate(eq) - eq).max())
                base = dict(name=name, tf=tf, fam=fam, sub=sub, side="BUY" if sd > 0 else "SELL", filt=flt, entry=("NXT", "STP")[en],
                            stop=("STR", "ATR")[sp], exit={2.0: "2R", 3.0: "3R", 0.0: "EOD", -1.0: "TRL"}[ex], signals=len(F), maxdd=dd_)
                for q, g in X.groupby("q"):
                    rows.append(dict(base, q=q, n=len(g), s=g.net.sum(), ss=(g.net ** 2).sum(), w=int((g.net > 0).sum()),
                                     gs=g.gross.sum(), cs=g.costR.sum()))
    return rows, meta


def main():
    t0 = time.time()
    rows, metas = [], []
    for n in MD.NAMES:
        r, m = run_name(n)
        rows += r; metas.append(m)
        print(f"[{(time.time() - t0) / 60:.1f} min] {n}: {len(r):,} quarter rows · {m['setups']:,} setups", flush=True)
    Q = pd.DataFrame(rows)
    Q.to_csv(OUT / f"{TAG}_quarters.csv.gz", index=False)
    run = dict(run=TAG.upper(), filters=list(FILTS), seed=SEED, created=pd.Timestamp.utcnow().isoformat(), commodities=metas,
               experiments=int(Q.drop_duplicates(["name", "tf", "fam", "sub", "side", "filt", "entry", "stop", "exit"]).shape[0]),
               quarter_rows=len(Q), minutes=round((time.time() - t0) / 60, 1))
    (OUT / f"{TAG}_run.json").write_text(json.dumps(run, indent=1, default=str))
    print(json.dumps({k: v for k, v in run.items() if k != "commodities"}, indent=1))


if __name__ == "__main__":
    main()

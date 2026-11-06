"""MCXI-001 – MCX intraday range breakout / breakdown + volume + OI buildup + false-breakout filter (owner priority 1-3).

DATA (verified 6-Nov-2026): Angel front-month 5-minute price + volume for CRUDEOIL, NATURALGAS, GOLD, SILVER, COPPER, ZINC,
ALUMINIUM to 2026-11-03 (from 2023 for older validation); contract-level DAILY OI from the official MCX bhavcopy
(2022-07 … 2026-11-05). Historical INTRADAY MCX OI is not available (Angel AB1012; live stream only since ~30-Oct-2026),
so OI enters as the PREVIOUS SESSION's buildup class – known before the day starts (no look-ahead). LEAD / NICKEL have no
intraday data -> not tested.

PERIODS: primary year 2025-11-06 … 2026-11-03 split chronologically: DEV 2025-11-06 … 2026-06-30, VALID 2026-07-01 … 11-03.
Older history 2023-2025-11-05 = additional out-of-sample check (never used for selection).

GRID (pre-registered; every combination is written to results/mcxi_ledger.csv):
  tf {5m, 15m, 30m} · range {OR60 = first 60 minutes, CONS = 2-hour range no wider than 3 ATR, PDHL = previous day high/low}
  side {BUY, SELL} · volume {any, breakout bar >= 1.5x its 20-bar average}  (stop entries: 'any' only – the trigger bar's
  volume is unknown at the fill) · OI {any, buildup (BUY: prev-day long buildup, SELL: short buildup), OI rising}
  entry {CBRK close beyond -> next open, STOP intrabar at the level, RET retest of the level within 6 bars after a close
  beyond} · stop {STR other side of the range (0.3-3 ATR), ATR 1.5 x ATR} · exit {2R, EOD}.
  No entries after 22:00, square-off at the 23:00 bar, first trigger per day per range per side, stop checked first,
  2 x MCX round-trip costs (instruments.cost_points incl. slippage). Random-entry baseline: same days / side / stop / exit.
python research/program/mcx_intra.py"""
import sys
import time
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import liqtl_mcx5 as LM  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
BHAV_SYM = {"ALUMINIUM": "ALUMINIUM", "COPPER": "COPPER", "CRUDEOIL": "CRUDEOIL", "GOLD": "GOLD", "NATURALGAS": "NATURALGAS",
            "SILVER": "SILVER", "ZINC": "ZINC"}
Y0, DEV_END, Y1 = pd.Timestamp("2025-11-06"), pd.Timestamp("2026-07-01"), pd.Timestamp("2026-11-04")
TFM = {"5m": 5, "15m": 15, "30m": 30}


# ── OI context from the MCX bhavcopy ───────────────────────────────────────────────────────────────────────────────────
def daily_oi():
    """-> {name: DataFrame(day, px_chg, oi_chg, cls)} – total futures OI of the commodity (all expiries, roll-neutral),
    price change of the most-traded contract; class of day d is applied to trading on the NEXT day."""
    fs = sorted((ROOT / "research/data/mcx_bhav/days").glob("*.csv"))
    rows = []
    for f in fs:
        d = pd.read_csv(f)
        d = d[(d.instrument == "FUTCOM") & d.symbol.isin(BHAV_SYM.values())]
        if d.empty:
            continue
        for s, g in d.groupby("symbol"):
            a = g.sort_values("volume_lots").iloc[-1]
            rows.append((pd.Timestamp(a.date), s, float(a.close), float(a.prev_close), float(g.oi_lots.sum()), str(a.expiry)))
    X = pd.DataFrame(rows, columns=["day", "sym", "close", "prev_close", "oi", "expiry"]).sort_values(["sym", "day"])
    out = {}
    for s, g in X.groupby("sym"):
        g = g.copy()
        g["px_chg"] = g.close / g.prev_close - 1                    # same contract (bhavcopy prev close) -> roll-free
        g["oi_chg"] = g.oi.pct_change()
        g["cls"] = np.select([(g.px_chg > 0) & (g.oi_chg > 0), (g.px_chg < 0) & (g.oi_chg > 0), (g.px_chg > 0) & (g.oi_chg < 0),
                              (g.px_chg < 0) & (g.oi_chg < 0)], ["LB", "SB", "SC", "LU"], "NA")
        g["next_day"] = g.day.shift(-1)
        out[s] = g
    return out


# ── simulator ─────────────────────────────────────────────────────────────────────────────────────────────────────────
@njit(cache=True)
def sim(o, h, l, c, atr, act, lvl, inv, eod, last_entry, side, entry, stop, exitc, cost):
    """per setup k: active from bar act[k] (range complete) to last_entry[k]; level lvl, invalidation inv; square-off eod[k].
    entry 1 CBRK (close beyond -> next open), 2 STOP (intrabar at level), 3 RET (after a close beyond, limit at level within
    6 bars). Returns (setup index, entry bar, R net, R gross, cbrk bar)."""
    K = len(act)
    oi_ = np.empty(K, np.int64); oj = np.empty(K, np.int64); orr = np.empty(K); og = np.empty(K); ocb = np.empty(K, np.int64)
    n = 0
    for k in range(K):
        i0, i1, ie, L, V = act[k], last_entry[k], eod[k], lvl[k], inv[k]
        j = -1; e = 0.0; cb = -1
        for t in range(i0, i1 + 1):
            if entry == 2:
                if (side > 0 and h[t] > L) or (side < 0 and l[t] < L):
                    j = t; e = max(L, o[t]) if side > 0 else min(L, o[t])
                    break
            if (side > 0 and c[t] > L) or (side < 0 and c[t] < L):
                cb = t; break
        if entry == 1 and cb >= 0 and cb + 1 <= ie:
            j = cb + 1; e = o[j]
        if entry == 3 and cb >= 0:
            for t in range(cb + 1, min(cb + 7, ie)):
                if (side > 0 and l[t] <= L) or (side < 0 and h[t] >= L):
                    j = t; e = min(L, o[t]) if side > 0 else max(L, o[t]); break
        if j < 0 or j >= ie:
            continue
        a = atr[i0]
        if not a > 0:
            continue
        if side * (e - L) > 0.5 * a:                           # never chase > 0.5 ATR beyond the level
            continue
        st = (V - side * 0.1 * a) if stop == 0 else (e - side * 1.5 * a)
        R = side * (e - st)
        if not (R > 0.3 * a and R < 3.0 * a):
            continue
        tgt = e + side * 2.0 * R
        px = c[ie]
        for t in range(j, ie + 1):
            if t > j and ((side > 0 and o[t] <= st) or (side < 0 and o[t] >= st)):
                px = o[t]; break
            if (side > 0 and l[t] <= st) or (side < 0 and h[t] >= st):
                px = st; break
            if exitc == 2 and (t > j or entry == 1) and ((side > 0 and h[t] >= tgt) or (side < 0 and l[t] <= tgt)):
                px = tgt; break
        g = side * (px - e) / R
        oi_[n] = k; oj[n] = j; og[n] = g; orr[n] = g - cost[j] / R; ocb[n] = cb; n += 1
    return oi_[:n], oj[:n], orr[:n], og[:n], ocb[:n]


def setups(f, tf, oi):
    """-> {range: dict(BUY/SELL -> arrays act, lvl, inv, eod, last_entry, day)} + bar relvol + oi class per bar day"""
    m = TFM[tf]
    t = f.time; day = t.dt.normalize().values; mins = (t.dt.hour * 60 + t.dt.minute).values
    h, l = f.high.values, f.low.values
    a = I.atr(f, 14).values
    days = pd.Series(np.arange(len(f))).groupby(day)
    out = {"OR60": {1: [], -1: []}, "CONS": {1: [], -1: []}, "PDHL": {1: [], -1: []}}
    prev_hi = prev_lo = None
    ncons = 120 // m
    for d, idx in days:
        idx = idx.values
        mm = mins[idx]
        ok = idx[(mm <= 23 * 60)]
        if len(ok) < 10:
            prev_hi, prev_lo = h[idx].max(), l[idx].min(); continue
        eod = ok[-1]
        le_ = ok[mm[: len(ok)] <= 22 * 60]
        last_entry = le_[-1] if len(le_) else eod
        orb = idx[mm < 600]                                      # 09:00-10:00
        if len(orb) >= max(1, 60 // m - 1) and orb[-1] + 1 < last_entry:
            for s in (1, -1):
                out["OR60"][s].append((orb[-1] + 1, h[orb].max() if s > 0 else l[orb].min(), l[orb].min() if s > 0 else h[orb].max(), eod, last_entry, d))
        if prev_hi is not None:
            first = idx[0]
            for s in (1, -1):
                out["PDHL"][s].append((first, prev_hi if s > 0 else prev_lo, (prev_lo if s > 0 else prev_hi), eod, last_entry, d))
        # consolidation: first time in the day a 2-hour window is no wider than 3 ATR (after 11:00)
        for p in range(ncons, len(ok)):
            w = ok[p - ncons:p]
            if mins[ok[p]] < 660 or ok[p] >= last_entry:
                continue
            hi, lo = h[w].max(), l[w].min()
            if a[ok[p]] > 0 and hi - lo <= 3 * a[ok[p]]:
                for s in (1, -1):
                    out["CONS"][s].append((ok[p], hi if s > 0 else lo, lo if s > 0 else hi, eod, last_entry, d))
                break
        prev_hi, prev_lo = h[idx].max(), l[idx].min()
    res = {}
    for r, dd in out.items():
        res[r] = {s: tuple(np.array(x) for x in zip(*v)) if v else None for s, v in dd.items()}
    v = f.volume.values.astype(float)
    relv = v / pd.Series(v).rolling(20, min_periods=10).mean().shift(1).values
    cls = pd.Series(day).map(oi.set_index("next_day")["cls"] if oi is not None else {}).fillna("NA").values
    oic = pd.Series(day).map(oi.set_index("next_day")["oi_chg"] if oi is not None else {}).fillna(0).values
    return res, a, relv, cls, oic


def run_name(name, OI):
    d5 = LM.load(name, "FIVE_MINUTE")
    if d5 is None:
        return [], []
    d5 = d5[d5.time >= pd.Timestamp("2023-01-01")].reset_index(drop=True)
    rows, trades = [], []
    oi = OI.get(BHAV_SYM[name])
    rng = np.random.default_rng(7)
    for tf in TFM:
        f = d5 if tf == "5m" else LM.resample(d5, TFM[tf])
        f = f.reset_index(drop=True)
        S, atr, relv, cls, oic = setups(f, tf, oi)
        o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
        atr = np.nan_to_num(atr).astype(np.float64)
        cost = np.array([2 * INS.cost_points(name, p, 1.0) for p in c])
        sw = f.switch.fillna(False).values.astype(bool)
        for rg, sides in S.items():
            for s, arr in sides.items():
                if arr is None:
                    continue
                act, lvl, inv, eod, le, day = arr
                okd = ~sw[act.astype(int)]                      # no trading on contract-switch days
                act, lvl, inv, eod, le, day = act[okd].astype(np.int64), lvl[okd].astype(np.float64), inv[okd].astype(np.float64), eod[okd].astype(np.int64), le[okd].astype(np.int64), day[okd]
                for en, sp, ex in product((1, 2, 3), (0, 1), (2, 0)):
                    ki, j, rr, gg, cb = sim(o, h, l, c, atr, act, lvl, inv, eod, le, s, en, sp, ex, cost)
                    if not len(ki):
                        continue
                    sig_bar = np.where(cb >= 0, cb, j)
                    for vf, of in product(("any", "vol"), ("any", "buildup", "oi_up")):
                        if vf == "vol" and en == 2:
                            continue
                        m = np.ones(len(ki), bool)
                        if vf == "vol":
                            m &= np.nan_to_num(relv[sig_bar]) >= 1.5
                        if of == "buildup":
                            m &= cls[sig_bar] == ("LB" if s > 0 else "SB")
                        elif of == "oi_up":
                            m &= oic[sig_bar] > 0
                        if m.sum() == 0:
                            continue
                        tt = f.time.values[j[m]]
                        per = np.where(tt < np.datetime64(Y0), 0, np.where(tt < np.datetime64(DEV_END), 1, np.where(tt < np.datetime64(Y1), 2, 3)))
                        for p_ in range(3):
                            x = rr[m][per == p_]; g_ = gg[m][per == p_]
                            if len(x):
                                rows.append((name, tf, rg, "BUY" if s > 0 else "SELL", vf, of, ("CBRK", "STOP", "RET")[en - 1],
                                             ("STR", "ATR")[sp], "2R" if ex == 2 else "EOD", p_, len(x), x.sum(), (x ** 2).sum(),
                                             (x > 0).sum(), x[x > 0].sum(), -x[x <= 0].sum(), g_.sum()))
                        if vf == "any" and of == "any":
                            trades += [(name, tf, rg, "BUY" if s > 0 else "SELL", ("CBRK", "STOP", "RET")[en - 1], ("STR", "ATR")[sp],
                                        "2R" if ex == 2 else "EOD", f.time.values[jj], r_, g2) for jj, r_, g2 in zip(j, rr, gg)]
        # random-entry baseline: one random bar per day between 10:00 and 22:00, random side, ATR stop, 2R / EOD
        dd = f.time.dt.normalize().values; mins = (f.time.dt.hour * 60 + f.time.dt.minute).values
        for ex in (2, 0):
            act_, lv_, iv_, eo_, le_, sd_ = [], [], [], [], [], []
            for d_, idx in pd.Series(np.arange(len(f))).groupby(dd):
                idx = idx.values; mm = mins[idx]
                cand = idx[(mm >= 600) & (mm <= 1320)]; ok = idx[mm <= 1380]
                if len(cand) < 3 or sw[idx[0]]:
                    continue
                i = rng.choice(cand); s = rng.choice([1, -1])
                act_.append(i); lv_.append(o[i + 1] if i + 1 < len(o) else c[i]); iv_.append(0.0); eo_.append(ok[-1]); le_.append(i + 1); sd_.append(s)
            act_, lv_, iv_, eo_, le_, sd_ = map(np.array, (act_, lv_, iv_, eo_, le_, sd_))
            for s in (1, -1):
                mk = sd_ == s
                lvl2 = np.where(s > 0, lv_[mk] - 1e9, lv_[mk] + 1e9)  # level always crossed -> CBRK next open = random entry
                ki, j, rr, gg, cb = sim(o, h, l, c, atr, act_[mk].astype(np.int64), lvl2.astype(np.float64), iv_[mk].astype(np.float64),
                                        eo_[mk].astype(np.int64), le_[mk].astype(np.int64), s, 1, 1, ex, cost)
                tt = f.time.values[j]
                per = np.where(tt < np.datetime64(Y0), 0, np.where(tt < np.datetime64(DEV_END), 1, np.where(tt < np.datetime64(Y1), 2, 3)))
                for p_ in range(3):
                    x = rr[per == p_]; g_ = gg[per == p_]
                    if len(x):
                        rows.append((name, tf, "RANDOM", "BUY" if s > 0 else "SELL", "any", "any", "RAND", "ATR", "2R" if ex == 2 else "EOD",
                                     p_, len(x), x.sum(), (x ** 2).sum(), (x > 0).sum(), x[x > 0].sum(), -x[x <= 0].sum(), g_.sum()))
    return rows, trades


COLS = ["name", "tf", "range", "side", "vol", "oi", "entry", "stop", "exit", "period", "n", "s", "ss", "w", "gw", "gl", "gs"]


def summarise(A, keys):
    g = A.groupby(keys + ["period"])[["n", "s", "ss", "w", "gw", "gl", "gs"]].sum()
    out = []
    for k, x in g.groupby(level=list(range(len(keys)))):
        x = x.droplevel(list(range(len(keys))))
        row = dict(zip(keys, k if isinstance(k, tuple) else (k,)))
        for p_, nm in ((1, "dev"), (2, "valid"), (0, "hist")):
            if p_ in x.index:
                r = x.loc[p_]
                row.update({f"{nm}_n": int(r.n), f"{nm}_R": r.s / r.n, f"{nm}_gross": r.gs / r.n, f"{nm}_win": 100 * r.w / r.n,
                            f"{nm}_PF": r.gw / r.gl if r.gl > 0 else np.nan})
                if nm == "dev":
                    sd = np.sqrt(max(r.ss / r.n - (r.s / r.n) ** 2, 1e-9))
                    row["dev_p"] = stats.t.sf((r.s / r.n) / (sd / np.sqrt(r.n)), max(r.n - 1, 1))
        out.append(row)
    S = pd.DataFrame(out)
    S["dev_p"] = S.get("dev_p", pd.Series(1.0, index=S.index)).fillna(1.0)
    S = S.sort_values("dev_p").reset_index(drop=True)
    m = len(S); S["dev_q"] = (S.dev_p * m / (np.arange(m) + 1))[::-1].cummin()[::-1].clip(upper=1)
    return S


def main():
    t0 = time.time()
    OI = daily_oi()
    rows, trades = [], []
    for nm in NAMES:
        r, t = run_name(nm, OI); rows += r; trades += t
        print(f"[{(time.time() - t0) / 60:.1f} min] {nm}: {len(r)} rows", flush=True)
    A = pd.DataFrame(rows, columns=COLS)
    A.to_csv(OUT / "mcxi_agg.csv.gz", index=False)
    pd.DataFrame(trades, columns=["name", "tf", "range", "side", "entry", "stop", "exit", "time", "R", "gross"]).to_csv(OUT / "mcxi_trades.csv.gz", index=False)
    K = ["tf", "range", "side", "vol", "oi", "entry", "stop", "exit"]
    P = summarise(A, K); P.to_csv(OUT / "mcxi_pooled.csv", index=False)
    N = summarise(A, ["name"] + K); N.to_csv(OUT / "mcxi_by_name.csv", index=False)
    A[["name"] + K].drop_duplicates().to_csv(OUT / "mcxi_ledger.csv", index=False)
    print(f"combinations: pooled {len(P)} · per commodity {len(N)} · {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()

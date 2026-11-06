"""CRSB-001 – validation of the FROZEN candidate "CRUDEOIL 30m S/R-zone breakout BUY" (owner 6-Nov-2026).

FROZEN SPEC (selected by MCXE-002 walk-forward at 2026-06-30; nothing below may be changed during validation):
  data      Angel front-month stitched CRUDEOIL 5-min (research/data/angel, liqtl_mcx5.load), contract-switch days skipped;
            30-min candles day-anchored at 09:00; ATR(14) on 30-min candles
  detector  pivots ±3 candles, usable 3 candles later; S/R zone = mean of >= 2 confirmed swing pivots within 0.25 x ATR inside
            the last 100 candles (rounded to a 0.25-ATR grid); SETUP when the previous 30-min close is <= zone < this close
  filter    60-min trend agrees: EMA20 > EMA50 and close > EMA50 on completed hourly candles ('trend')
  entry     buy-stop at the breakout candle's high, valid for the next 3 x 30-min (18 five-minute bars); cancelled if the
            invalidation (zone - 0.25 ATR) trades first or in the same 5-min bar; never > 0.5 ATR beyond the trigger
  stop      zone - 0.25 ATR - 0.1 ATR (structure), risk must be 0.3-3 ATR
  exit      square-off at the 23:00 bar close (no target), stop checked first in every 5-min bar
  costs     statutory MCX fees + 1.5 ticks slippage per side (mcx_disc.real_cost); one position at a time; no entries after 22:00
python research/program/crude_srbrk.py [audit|maxstat|robust|data|dtc|all]"""
import hashlib
import json
import sys
import zlib
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_engine as E, mcx_disc as MD  # noqa: E402

OUT = ROOT / "research/program/results"
SPEC = dict(name="CRUDEOIL", tf="30m", fam="SR", sub="BRK", side=1, filt="trend", entry=1, stop=0, exitc=0.0,
            sr=dict(lookback=100, tol_atr=0.25, min_pivots=2), pivot_k=3, cost="fees + 1.5 ticks/side", selected_at="2026-06-30",
            oos=("2026-07-01", "2026-11-03"))
OOS0, OOS1 = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-11-04")
CACHE = {}


def data(name="CRUDEOIL"):
    if name not in CACHE:
        P = MD.prep(name); d5 = P[0]
        CACHE[name] = dict(P=P, d5=d5, D=E.setups_for(name, P),
                           arr=tuple(d5[x].values.astype(np.float64) for x in ("open", "high", "low", "close")),
                           cost=np.array([MD.real_cost(name, p) for p in d5.close.values]))
    return CACHE[name]


def frozen_trades(C=None, cost_mult=1.0, delay=0, extra_stop_ticks=0.0, D=None):
    C = C or data()
    D = C["D"] if D is None else D
    S = D[(D.tf == SPEC["tf"]) & (D.fam == SPEC["fam"]) & (D["sub"] == SPEC["sub"]) & (D.side == SPEC["side"])]
    F = E.apply_filter(S, SPEC["filt"]).copy()
    if delay:
        F["act"] = F.act + delay; F["last_entry"] = F.last_entry + delay
        F = F[F.act < F.eod]
    X = E.simulate(F, C["arr"], C["cost"] * cost_mult, SPEC["entry"], SPEC["stop"], SPEC["exitc"])
    d5 = C["d5"]
    X = X.assign(entry_time=d5.time.values[X.j], exit_time=d5.time.values[X.x], entry_px=np.nan)
    tick = 1.0
    if extra_stop_ticks:                                       # conservative stop fills: every stop-out a further N ticks worse
        R_pts = X.risk_atr * X.atr  # approx risk in points of the structure stop (for R conversion)
        stopped = X.gross <= -0.999
        X.loc[stopped, "gross"] = X.loc[stopped, "gross"] - extra_stop_ticks * tick / (X.loc[stopped, "atr"] * X.loc[stopped, "risk_atr"]).clip(lower=1e-9)
    X["net"] = X.gross - X.costR
    return X


def stats(x):
    R = np.asarray(x, float)
    if not len(R):
        return {}
    eq = np.cumsum(R); dd = float((np.maximum.accumulate(eq) - eq).max())
    streak = cur = 0
    for v in R:
        cur = cur + 1 if v <= 0 else 0; streak = max(streak, cur)
    srt = np.sort(R)[::-1]
    top3 = srt[:3].sum() / R.sum() if R.sum() > 0 else np.nan
    return dict(n=len(R), win=round(100 * (R > 0).mean(), 1), mean=round(R.mean(), 3), median=round(float(np.median(R)), 3),
                PF=round(R[R > 0].sum() / -R[R <= 0].sum(), 2) if (R <= 0).any() else np.inf, total=round(R.sum(), 2),
                maxDD=round(dd, 2), max_losing_streak=streak, top3_share_of_net=round(top3, 2),
                mean_without_top3=round(np.sort(R)[:-3].mean(), 3) if len(R) > 5 else np.nan)


def boot(x, n=10000, seed=1):
    rng = np.random.default_rng(seed); x = np.asarray(x)
    m = rng.choice(x, (n, len(x))).mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def audit():
    C = data()
    fp = E.fingerprint(C["d5"])
    X = frozen_trades(C)
    o = X[(X.day >= OOS0) & (X.day < OOS1)]
    out = dict(spec=SPEC, data_fingerprint=fp, data_first=str(C["d5"].time.iat[0]), data_last=str(C["d5"].time.iat[-1]),
               code_sha=hashlib.sha256(Path(E.__file__).read_bytes()).hexdigest()[:16])
    sp = json.dumps(dict(SPEC), sort_keys=True, default=str)
    out["spec_fingerprint"] = hashlib.sha256(sp.encode()).hexdigest()[:16]
    out["oos"] = stats(o.net); out["oos_ci"] = boot(o.net)
    out["oos_unique_entries"] = int(o.j.nunique()); out["oos_duplicates"] = int(len(o) - o.j.nunique())
    out["oos_switch_days"] = int(o.day.isin(C["P"][5]).sum())
    out["oos_entry_before_signal_end"] = int((o.entry_time < pd.to_datetime(o.end)).sum())
    out["oos_entry_after_2200"] = int((pd.to_datetime(o.entry_time).dt.hour * 60 + pd.to_datetime(o.entry_time).dt.minute > 22 * 60).sum())
    out["oos_exit_after_2300"] = int((pd.to_datetime(o.exit_time).dt.hour * 60 + pd.to_datetime(o.exit_time).dt.minute > 23 * 60).sum())
    out["oos_monthly"] = o.groupby(o.day.dt.to_period("M").astype(str)).net.agg(["size", "mean", "sum"]).round(3).to_dict("index")
    out["all_years"] = X.groupby(X.day.dt.year).net.agg(["size", "mean", "sum"]).round(3).to_dict("index")
    out["exit_reasons_oos"] = dict(stop=int((o.gross <= -0.999).sum()), close=int((o.gross > -0.999).sum()))
    o[["end", "entry_time", "exit_time", "trig", "inv", "atr", "gross", "costR", "net"]].to_csv(OUT / "crsb_oos_trades.csv", index=False)
    X[["day", "end", "entry_time", "exit_time", "trig", "inv", "atr", "gross", "costR", "net"]].to_csv(OUT / "crsb_all_trades.csv", index=False)
    (OUT / "crsb_spec.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("oos_monthly", "all_years")}, indent=1, default=str))
    print("OOS monthly:", out["oos_monthly"]); print("all years (frozen rule applied to all data – years before 2026-07 are NOT independent):", out["all_years"])
    return X


# ── selection-aware max-statistic (CRSB-002) ───────────────────────────────────────────────────────────────────────────
class FastNull:
    """Matched time-permutation null for one stream's untouched-OOS trades: each real signal moves to a random OTHER OOS day
    at the same time-of-day candle; same side, same risk in ATR units, same execution and costs."""

    def __init__(self, name, tf, fam, sub, side, choice):
        C = data(name)
        flt, en, sp, ex = choice.split("|")
        self.en, self.sp = ("NXT", "STP").index(en), ("STR", "ATR").index(sp)
        self.ex = {"2R": 2.0, "3R": 3.0, "EOD": 0.0, "TRL": -1.0}[ex]
        sd = 1 if side == "BUY" else -1
        D = C["D"]
        S = D[(D.tf == tf) & (D.fam == fam) & (D["sub"] == sub) & (D.side == sd) & (D.day >= OOS0) & (D.day < OOS1)]
        self.F = E.apply_filter(S, flt)
        self.C = C
        X = E.simulate(self.F, C["arr"], C["cost"], self.en, self.sp, self.ex) if len(self.F) else pd.DataFrame()
        self.actual = (X.gross - X.costR).values if len(X) else np.array([])
        fr = {"15m": C["P"][1], "30m": C["P"][2], "60m": C["P"][3]}[tf].reset_index(drop=True)
        d5 = C["d5"]; t5 = d5.time.values
        eod_day = d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1])
        ok_day = (fr.day >= OOS0) & (fr.day < OOS1) & fr.day.isin(eod_day.index) & ~fr.day.isin(C["P"][5])
        end = fr.time.values + np.timedelta64(E.TFS[tf], "m")
        act = np.searchsorted(t5, end)
        valid = ok_day.values & (act < len(d5)) & (fr.atr.values > 0)
        valid &= np.array([a < len(d5) and d5.day.values[min(a, len(d5) - 1)] == dy for a, dy in zip(act, fr.day.values)])
        self.eodb = np.where(valid, fr.day.map(eod_day).fillna(-1).astype(int).values, -1)
        valid &= act < self.eodb
        self.fr, self.act, self.valid, self.sd = fr, act, valid, sd
        self.by_min = {m: np.flatnonzero(valid & (fr.m.values == m)) for m in np.unique(fr.m.values[valid])}
        self.sig_min = fr.m.values[self.F.i.values] if len(self.F) else np.array([])
        self.sig_day = self.F.day.values if len(self.F) else np.array([])
        self.risk = self.F.risk_atr.values if len(self.F) else np.array([])
        self.lastoff = 3 * E.TFS[tf] // 5 - 1

    def draw(self, rng):
        if not len(self.F):
            return np.nan
        idx = []
        for m, dy in zip(self.sig_min, self.sig_day):
            pool = self.by_min.get(m)
            if pool is None or len(pool) < 2:
                idx.append(-1); continue
            j = pool[rng.integers(len(pool))]
            if self.fr.day.values[j] == dy:
                j = pool[rng.integers(len(pool))]
            idx.append(j)
        idx = np.array(idx); keep = idx >= 0
        if not keep.any():
            return np.nan
        j = idx[keep]; s = self.sd
        fr = self.fr
        trig = (fr.high.values[j] if s > 0 else fr.low.values[j]).astype(np.float64)
        atr = fr.atr.values[j].astype(np.float64)
        inv = trig - s * self.risk[keep] * atr
        act = self.act[j].astype(np.int64); eod = self.eodb[j].astype(np.int64)
        last = np.minimum(act + self.lastoff, eod - 1).astype(np.int64)
        order = np.argsort(act, kind="stable")
        o, h, l, c = self.C["arr"]
        r = E.sim(o, h, l, c, act[order], np.full(len(j), s, np.int64), trig[order], inv[order], atr[order], eod[order], last[order],
                  self.en, self.sp, self.ex, self.C["cost"])
        m = ~np.isnan(r[:, 0])
        return float((r[m, 0] - r[m, 1]).mean()) if m.any() else np.nan


def maxstat(n_perm=10000, universe="survivors"):
    A = pd.read_csv(OUT / "mcxe2_wf.csv")
    if universe == "survivors":
        U = A[(A.wf_n >= 60) & (A.wf_R > 0) & (A.wf_stress > 0) & (A.wf_quarters_pos >= 0.6 * A.wf_quarters_traded)]
    else:
        U = A[A.chosen.notna()]
    U = U[U.chosen.notna()]
    rng = np.random.default_rng(E.SEED)
    Z, info = [], []
    for r in U.itertuples():
        nl = FastNull(r.name, r.tf, r.fam, r.sub, r.side, r.chosen)
        if len(nl.actual) < 5:
            continue
        null = np.array([nl.draw(rng) for _ in range(n_perm)])
        mu, sdv = np.nanmean(null), np.nanstd(null)
        if not sdv > 0:
            continue
        Z.append((null - mu) / sdv)
        z = (nl.actual.mean() - mu) / sdv
        info.append(dict(name=r.name, tf=r.tf, fam=r.fam, sub=r.sub, side=r.side, n=len(nl.actual), actual=nl.actual.mean(),
                         null_mean=mu, null_sd=sdv, z=z, raw_rank=float(np.nanmean(null < nl.actual.mean()))))
    Z = np.nan_to_num(np.vstack(Z), nan=-9)
    zmax = Z.max(axis=0)
    I = pd.DataFrame(info)
    I["adj_p"] = [(1 + (zmax >= z).sum()) / (1 + len(zmax)) for z in I.z]
    I["raw_p"] = 1 - I.raw_rank
    I = I.sort_values("z", ascending=False)
    I.to_csv(OUT / f"crsb_maxstat_{universe}.csv", index=False)
    cand = I[(I.name == "CRUDEOIL") & (I.tf == "30m") & (I.fam == "SR") & (I["sub"] == "BRK") & (I.side == "BUY")]
    res = dict(universe=universe, streams=len(I), n_perm=n_perm, seed=E.SEED, zmax_p95=float(np.percentile(zmax, 95)),
               zmax_p99=float(np.percentile(zmax, 99)), candidate=cand.iloc[0].to_dict() if len(cand) else None)
    (OUT / f"crsb_maxstat_{universe}.json").write_text(json.dumps(res, indent=1, default=str))
    pd.set_option("display.width", 220)
    print(json.dumps(res, indent=1, default=str)); print(I.head(10).round(4).to_string(index=False))
    return res


if __name__ == "__main__":
    what = (sys.argv[1:] or ["audit"])[0]
    if what in ("audit", "all"):
        audit()
    if what in ("maxstat", "all"):
        maxstat(int(sys.argv[2]) if len(sys.argv) > 2 else 10000, sys.argv[3] if len(sys.argv) > 3 else "survivors")

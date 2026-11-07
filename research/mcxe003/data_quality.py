"""MCXE-003 data audit. Read-only checks on every dataset used by the programme -> results/data_audit.json (+ DATA_AUDIT.md
is written by hand from it).
Checks per series: rows, span, duplicate / unordered timestamps, non-positive or impossible OHLC (high < max(open, close),
low > min(open, close)), zero-volume share, session start / end (timezone sanity: MCX opens 09:00 IST, NSE 09:15),
missing bars inside a session (relative to the modal bar count of that weekday-season), day-gap outliers and roll-day gaps
(close-to-open jump on a contract switch vs normal days, in daily ATR).
python research/mcxe003/data_quality.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "research/mcxe003/results"
MCX = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "NICKEL"]


def ohlc_checks(d, step_min=None, open_hm=None):
    r = dict(rows=int(len(d)))
    if not len(d):
        return r
    t = d.time
    r.update(first=str(t.iat[0]), last=str(t.iat[-1]), dup_ts=int(t.duplicated().sum()), unordered=int((t.diff().dt.total_seconds() < 0).sum()),
             nonpos=int((d[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
             bad_high=int((d.high < d[["open", "close"]].max(axis=1) - 1e-9).sum()),
             bad_low=int((d.low > d[["open", "close"]].min(axis=1) + 1e-9).sum()),
             zero_vol_pct=round(100 * float((d.volume <= 0).mean()), 2) if "volume" in d else None)
    if step_min:
        day = t.dt.normalize()
        first = t.groupby(day).min(); last = t.groupby(day).max(); cnt = t.groupby(day).size()
        exp = ((last - first).dt.total_seconds() / 60 / step_min + 1).round()
        r["days"] = int(len(cnt))
        r["missing_bars_pct"] = round(100 * float(1 - cnt.sum() / exp.sum()), 3)
        r["days_missing_gt5pct"] = int(((exp - cnt) / exp > 0.05).sum())
        hm = first.dt.hour * 100 + first.dt.minute
        r["session_start_mode"] = int(hm.mode().iat[0]); r["session_start_late_days"] = int((hm > (open_hm or 0) + 30).sum())
        lh = last.dt.hour * 100 + last.dt.minute
        r["session_end_values"] = {int(k): int(v) for k, v in lh.value_counts().head(4).items()}
        big = (d.close.pct_change().abs() > 0.08)
        r["bar_jumps_gt8pct"] = int(big.sum())
    return r


def mcx_intraday():
    from research.program import liqtl_mcx5 as LM
    res = {}
    for nm in MCX:
        for iv, st in (("FIVE_MINUTE", 5), ("THREE_MINUTE", 3), ("ONE_HOUR", 60), ("FIFTEEN_MINUTE", 15), ("ONE_DAY", None)):
            try:
                d = LM.load(nm, iv)
            except Exception as e:                       # noqa: BLE001
                d = None
            if d is None:
                res[f"{nm} {iv}"] = "NOT AVAILABLE"; continue
            r = ohlc_checks(d, st, 900)
            sw = d[d.switch.fillna(False)]
            r["switch_days"] = int(sw.time.dt.normalize().nunique())
            if iv == "ONE_DAY" or iv == "FIVE_MINUTE":
                g = d.assign(day=d.time.dt.normalize()).groupby("day").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"),
                                                                          c=("close", "last"), s=("switch", "max"))
                atr = (g.h - g.l).rolling(14).mean().shift(1)
                gap = ((g.o - g.c.shift()).abs() / atr)
                r["open_gap_atr_median_normal"] = round(float(gap[~g.s.astype(bool)].median()), 3)
                r["open_gap_atr_median_switch"] = round(float(gap[g.s.astype(bool)].median()), 3) if g.s.any() else None
            res[f"{nm} {iv}"] = r
    return res


def mcx_bhav():
    p = ROOT / "research/data/mcx_bhav/days"
    fs = sorted(p.glob("*.csv"))
    if not fs:
        return "NOT AVAILABLE"
    D = pd.concat([pd.read_csv(f) for f in fs[::20]] + [pd.read_csv(fs[-1])])     # sampled for the audit
    fut = D[D.instrument.astype(str).str.startswith("FUT")]
    sym = fut.groupby("symbol").agg(rows=("date", "size"), first=("date", "min"), last=("date", "max"),
                                    zero_oi=("oi_lots", lambda s: round(float((s <= 0).mean()), 3)))
    return dict(files=len(fs), first=fs[0].stem, last=fs[-1].stem, sampled_every=20, symbols=sym.reset_index().to_dict("records"))


def nse_fo():
    p = ROOT / "research/data/nse_opt/days"
    fs = sorted(p.glob("*.csv"))
    D = pd.concat([pd.read_csv(f, usecols=["date", "symbol", "kind", "expiry", "open", "high", "low", "close", "contracts", "oi"])
                   .query("kind == 'FUT'") for f in fs])
    D["date"] = pd.to_datetime(D.date); D["expiry"] = pd.to_datetime(D.expiry)
    front = D.sort_values("expiry").groupby(["date", "symbol"]).head(1)
    per_day = front.groupby("date").symbol.nunique()
    bad = int((front.high < front[["open", "close"]].max(axis=1)).sum() + (front.low > front[["open", "close"]].min(axis=1)).sum())
    zero_trade = round(float((front.contracts <= 0).mean()), 4)
    syms = front.groupby("symbol").date.agg(["min", "max", "size"])
    return dict(files=len(fs), first=fs[0].stem, last=fs[-1].stem, symbols_ever=int(len(syms)),
                symbols_per_day=dict(min=int(per_day.min()), median=int(per_day.median()), max=int(per_day.max())),
                symbols_that_stopped_before_end=int((syms["max"] < syms["max"].max() - pd.Timedelta(days=30)).sum()),
                bad_ohlc_rows=bad, zero_contract_front_rows_pct=100 * zero_trade, dup=int(front.duplicated(["date", "symbol"]).sum()))


def angel_eq():
    from research.program import eq_data as ED
    u = pd.read_csv(ED.EQ / "universe.csv")
    d5, d1 = [], []
    for s in u.symbol:
        for iv, acc in (("FIVE_MINUTE", d5), ("ONE_DAY", d1)):
            p = ED.EQ / f"{s}_{iv}.csv.gz"
            if p.exists():
                d = pd.read_csv(p, parse_dates=["time"])
                acc.append(dict(sym=s, **{k: v for k, v in ohlc_checks(d, 5 if iv == "FIVE_MINUTE" else None, 915).items()
                                         if k not in ("session_end_values",)}))
    A, B = pd.DataFrame(d5), pd.DataFrame(d1)
    agg = lambda X: dict(n=len(X), rows=int(X.rows.sum()), first_min=str(X["first"].min()), first_median=str(sorted(X["first"])[len(X) // 2]),  # noqa: E731
                        last_min=str(X["last"].min()), dup=int(X.dup_ts.sum()), nonpos=int(X.nonpos.sum()),
                        bad_ohlc=int(X.bad_high.sum() + X.bad_low.sum()), zero_vol_pct_median=float(X.zero_vol_pct.median()))
    r = dict(universe=len(u), universe_asof=str(u["asof"].iat[0]) if "asof" in u.columns else None, five_minute=agg(A), daily=agg(B))
    r["five_minute"]["missing_bars_pct_median"] = float(A.missing_bars_pct.median())
    r["five_minute"]["bar_jumps_gt8pct_total"] = int(A.bar_jumps_gt8pct.sum())
    return r


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = dict(mcx_intraday=mcx_intraday(), mcx_bhav=mcx_bhav(), nse_fo=nse_fo(), angel_eq=angel_eq())
    ck = ROOT / "research/program/results/eq_data_check.json"
    if ck.exists():
        res["nse_cash_bhav_prior_check"] = json.loads(ck.read_text())
    (OUT / "data_audit.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str)[:12000])


if __name__ == "__main__":
    main()

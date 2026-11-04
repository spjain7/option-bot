"""DATA-AUDIT-001 (4-Nov-2026): verify the Angel One MCX research series against the OFFICIAL MCX bhavcopy.

Why: a large strategy search on wrong volume / rollover / timestamps produces impressive but false results. Before any
more searching, every research dataset gets a measured quality status.

Checks per commodity (Angel vendor-stitched front-month series, Jul-2022 onward, where the bhavcopy exists):
  1. contract identification – every Angel daily bar is matched to the bhavcopy contract with the same open/high/low;
     close is compared separately (until ~2024 the MCX bhavcopy "Close" is MCX's closing price, not the last trade,
     so a small close difference with exact O/H/L is a definition difference, not an error)
  2. calendar – Angel days with no MCX session, MCX sessions missing in Angel, calendar holes
  3. volume – Angel volume ÷ bhavcopy contract volume (lots); zero / implausible volume
  4. liquidity of the contract used – days where Angel's contract had < 20 % of the most active contract's volume
     (expiry / tender days): prices from an illiquid contract are unreliable for signals and fills
  5. rolls – the day Angel switches contract, the TRUE roll gap (new − old close on the same day, both from the
     bhavcopy) and the error of the ESTIMATED gap used by research/roll_adjust.py
  6. intraday – 1-hour bars aggregated per day vs the daily bar, candlecheck validation, bars outside the MCX session
Status (per dataset): VERIFIED / ACCEPTABLE / DEGRADED / INVALID – rules in grade(). INVALID never feeds a call.

  python -m research.data_audit            -> research/data_quality/manifest.json, REPORT.md, rolls_true.csv
"""
import datetime as dt
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import candlecheck  # noqa: E402

DATA = ROOT / "research" / "data"
OUT = ROOT / "research" / "data_quality"
NAMES = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]
TOL = 3e-4                       # relative price tolerance for "same price" (1–2 ticks; vendor tick rounding seen in 2023)
ILLIQ = 0.20                     # contract volume share below this = illiquid contract day
SESSION = (dt.time(9, 0), dt.time(23, 55))
VERSION = "data-audit-1.0"
TICK = {"GOLD": 1.0, "SILVER": 1.0, "CRUDEOIL": 1.0, "NATURALGAS": 0.1, "COPPER": 0.05, "ZINC": 0.05, "ALUMINIUM": 0.05}


def bhav():
    fs = sorted(glob.glob(str(DATA / "mcx_bhav" / "days" / "*.csv")))
    b = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    b = b[b["instrument"] == "FUTCOM"].copy()
    b["date"] = pd.to_datetime(b["date"])
    b["exp"] = pd.to_datetime(b["expiry"], format="%d%b%Y")
    for c in ("open", "high", "low", "close", "volume_lots", "oi_lots"):
        b[c] = pd.to_numeric(b[c], errors="coerce")
    return b, len(fs)


def manifest_row(name, iv):
    m = pd.read_csv(DATA / "angel" / "manifest.csv")
    r = m[(m["exch"] == "MCX") & (m["name"] == name) & (m["interval"] == iv) & (m["front_stitched"].astype(str) == "True")]
    return None if r.empty else r.iloc[-1]


def load_angel(name, iv):
    r = manifest_row(name, iv)
    if r is None:
        return None, None
    f = DATA / "angel" / "MCX" / f"{r['symbol']}_{iv}.csv"
    if not f.exists():
        return None, None
    return pd.read_csv(f, parse_dates=["time"]), f


def match_contracts(a, g, tick=0.0):
    """a: Angel daily (time, OHLCV), g: bhav rows of one symbol. -> per Angel day the best-matching contract."""
    m = a.merge(g, left_on=a["time"].dt.normalize(), right_on="date", suffixes=("_a", ""))
    m["ohl_err"] = np.maximum.reduce([(m[f"{c}_a"] / m[c] - 1).abs() for c in ("open", "high", "low")])
    m["close_err"] = (m["close_a"] / m["close"] - 1).abs()
    m["score"] = m["ohl_err"] + 0.1 * m["close_err"]
    best = m.loc[m.groupby("date")["score"].idxmin()].copy()
    day = g.groupby("date").agg(max_vol=("volume_lots", "max"), front_exp=("exp", "min"))
    oi_top = g.loc[g.groupby("date")["oi_lots"].idxmax(), ["date", "exp"]].rename(columns={"exp": "oi_exp"})
    vol_top = g.loc[g.groupby("date")["volume_lots"].idxmax(), ["date", "exp"]].rename(columns={"exp": "vol_exp"})
    best = best.merge(day, left_on="date", right_index=True).merge(oi_top, on="date").merge(vol_top, on="date")
    best["share"] = best["volume_lots"] / best["max_vol"].replace(0, np.nan)
    best["vol_ratio"] = best["volume"] / best["volume_lots"].replace(0, np.nan)
    tol = np.maximum(TOL, 1.5 * tick / best["close"])           # at least 1–2 ticks
    best["kind"] = np.where(best["ohl_err"] > tol, "MISMATCH", np.where(best["close_err"] <= tol, "EXACT", "CLOSE_DEF"))
    return best.sort_values("date").reset_index(drop=True)


def rolls(best, g, name):
    """Angel contract switches with the TRUE roll gap from the bhavcopy: on the last day Angel used the old contract,
    new-contract close − old-contract close (both official). Angel jump = Angel close change across the switch."""
    rows = []
    prev = None
    for _, r in best.iterrows():
        if r["kind"] == "MISMATCH":
            continue
        if prev is not None and r["exp"] != prev["exp"]:
            nw = g[(g["date"] == prev["date"]) & (g["exp"] == r["exp"])]
            new_prev = float(nw["close"].iloc[0]) if len(nw) else np.nan
            rows.append(dict(name=name, switch_day=r["date"].date(), last_old_day=prev["date"].date(),
                             old_exp=prev["exp"].date(), new_exp=r["exp"].date(),
                             days_after_old_expiry=(r["date"] - prev["exp"]).days,
                             old_close=float(prev["close"]), new_close_same_day=new_prev,
                             true_gap=new_prev - float(prev["close"]),
                             true_gap_pct=(new_prev / float(prev["close"]) - 1) * 100,
                             angel_jump=float(r["close_a"]) - float(prev["close_a"]),
                             old_vol_last_day=float(prev["volume_lots"]), new_vol_that_day=float(nw["volume_lots"].iloc[0]) if len(nw) else np.nan))
        prev = r
    df = pd.DataFrame(rows)
    if len(df):          # when did the open-interest leader move to the new contract (the market's own roll)?
        df["oi_leader_from"] = [best.loc[best["oi_exp"] == pd.Timestamp(x), "date"].min() for x in df["new_exp"]]
        df["oi_leader_from"] = pd.to_datetime(df["oi_leader_from"]).dt.date
        df["days_on_old_after_oi_roll"] = [int(((best["date"] >= pd.Timestamp(o)) & (best["date"] < pd.Timestamp(s))).sum())
                                           if pd.notna(o) else None for o, s in zip(df["oi_leader_from"], df["switch_day"])]
    return df


def close_definition_switch(name):
    """Angel daily close vs last 1h close: equal while Angel's daily close is the last trade; differs once it is the
    MCX official closing price. -> first date of the regime that lasts to the end (None if never switched)."""
    d, _ = load_angel(name, "ONE_DAY"); h, _ = load_angel(name, "ONE_HOUR")
    if d is None or h is None:
        return None, None
    lc = h.groupby(h["time"].dt.normalize())["close"].last()
    dc = d.set_index(d["time"].dt.normalize())["close"]
    j = pd.concat([lc, dc], axis=1, keys=["h", "d"], sort=True).dropna()
    eq = ((j["h"] / j["d"] - 1).abs() <= 1e-4).astype(float).rolling(20).mean()
    later = eq[::-1].cummax()[::-1]              # max share of equality from each day to the end
    sw = later[later < 0.5]
    return (sw.index[0].date() if len(sw) else None), round(float(eq.iloc[-60:].mean()), 3)


def estimated_gaps(name):
    try:
        from research.roll_adjust import load_mcx
        _, tab = load_mcx(name, adjusted=True)
        return tab
    except Exception as e:
        return pd.DataFrame(dict(error=[f"{type(e).__name__}: {e}"]))


def intraday(name, daily):
    h, f = load_angel(name, "ONE_HOUR")
    if h is None:
        return dict(status="missing")
    clean, rep = candlecheck.validate(h[["time", "open", "high", "low", "close", "volume"]], interval_min=60, label=f"{name} 1h")
    t = clean["time"]
    outside = int(((t.dt.time < SESSION[0]) | (t.dt.time > SESSION[1])).sum())
    weekend = int((t.dt.weekday >= 5).sum())
    agg = clean.groupby(t.dt.normalize()).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                              close=("close", "last"), volume=("volume", "sum"))
    d = daily.set_index(daily["time"].dt.normalize())[["open", "high", "low", "close", "volume"]]
    j = agg.join(d, rsuffix="_d", how="inner")
    res = dict(file=f.name, bars=len(h), removed=rep["removed"], flags=rep["flags"], outside_session=outside,
               weekend_bars=weekend, days_compared=len(j))
    for c in ("open", "high", "low", "close"):
        res[f"{c}_match"] = round(float(((j[c] / j[f"{c}_d"] - 1).abs() <= TOL).mean()), 4) if len(j) else None
    if len(j):
        err = np.maximum.reduce([(j[c] / j[f"{c}_d"] - 1).abs() for c in ("open", "high", "low")])
        res["days_hl_off_gt_0_5pct"] = int((err > 0.005).sum())
        res["bad_days_sample"] = [str(x.date()) for x in j.index[err > 0.005][:10]]
    res["volume_ratio_median"] = round(float((j["volume"] / j["volume_d"].replace(0, np.nan)).median()), 3) if len(j) else None
    res["same_volume_per_bar_share"] = round(float((clean["volume"].diff() == 0).mean()), 4)   # repeated volumes = suspect
    return res


def grade(s):
    """Status rules (pre-registered here, before seeing other datasets):
    INVALID   price match (O/H/L) < 90 % of bhav days, or > 5 % of MCX sessions missing
    DEGRADED  price match < 98 %, or volume unusable (median ratio off by > 10 % or > 5 % zero), or any uncorrected roll
              gap used in an UNADJUSTED backtest (flagged separately per use), or illiquid-contract days > 5 %
    ACCEPTABLE price match >= 98 % with known, documented issues (close definition, illiquid expiry days, estimated rolls)
    VERIFIED  price match >= 99.5 %, volume ratio within 2 %, no missing sessions, rolls verified against bhavcopy"""
    why = []
    if s["ohl_match"] < 0.90 or s["missing_sessions_share"] > 0.05:
        return "INVALID", ["price match < 90 % or > 5 % sessions missing"]
    st = "VERIFIED"
    if s["ohl_match"] < 0.995:
        st = "ACCEPTABLE"; why.append(f"O/H/L match {s['ohl_match']:.1%}")
    if s["missing_sessions"]:
        st = "ACCEPTABLE"; why.append(f"{s['missing_sessions']} MCX sessions missing in Angel")
    if s["illiquid_share"] > 0.0:
        st = "ACCEPTABLE"; why.append(f"{s['illiquid_share']:.1%} days priced from an illiquid contract (expiry/tender)")
    if s["vol_ratio_median"] is None or abs(s["vol_ratio_median"] - 1) > 0.02:
        st = "ACCEPTABLE"; why.append(f"volume ratio median {s['vol_ratio_median']}")
    if s["roll_est_err_median"] is not None and s["roll_est_err_median"] > 0.25:
        px = " (proxy files absent – estimator fell back to the raw jump)" if (s.get("roll_est_proxy_missing") or 0) > 0.5 else ""
        why.append(f"estimated roll gaps off by median {s['roll_est_err_median']:.0%} of the true gap{px}; use exact gaps")
        st = "ACCEPTABLE" if st == "VERIFIED" else st
    if s["ohl_match"] < 0.98 or s["illiquid_share"] > 0.05 or s["vol_zero_share"] > 0.05 or \
            (s["vol_ratio_median"] is not None and abs(s["vol_ratio_median"] - 1) > 0.10):
        st = "DEGRADED"
    return st, why


def audit():
    OUT.mkdir(parents=True, exist_ok=True)
    b, nfiles = bhav()
    sessions = sorted(b["date"].unique())
    retrieved = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")
    man, all_rolls, report = {}, [], []
    for name in NAMES:
        a, f = load_angel(name, "ONE_DAY")
        if a is None:
            man[name] = dict(status="INVALID", reasons=["no Angel daily file"]); continue
        a = a[["time", "open", "high", "low", "close", "volume"]].sort_values("time")
        start, end = max(a["time"].min(), b["date"].min()), min(a["time"].max(), b["date"].max())
        aw = a[(a["time"] >= start) & (a["time"] <= end)].reset_index(drop=True)
        g = b[(b["symbol"] == name) & (b["date"] >= start) & (b["date"] <= end)]
        best = match_contracts(aw, g, TICK.get(name, 0.0))
        sess = [d for d in sessions if start <= d <= end and d in set(g["date"])]
        a_days = set(aw["time"].dt.normalize())
        missing = [pd.Timestamp(d).date() for d in sess if d not in a_days]
        extra = sorted(d.date() for d in a_days - set(pd.to_datetime(sess)))
        rl = rolls(best, g, name)
        est = estimated_gaps(name)
        err = None
        if len(rl) and "est_gap_pts" in est.columns:
            e = est.copy(); e["switch_day"] = pd.to_datetime(e["switch_day"]).dt.date; e["gap"] = e["est_gap_pts"]
            j = rl.merge(e[["switch_day", "gap", "proxy_missing"]], on="switch_day", how="left")
            rl["estimated_gap"] = j["gap"].values
            rl["estimator_found_roll"] = j["gap"].notna().values
            rl["estimator_proxy_missing"] = j["proxy_missing"].values
            ok = j["gap"].notna() & j["true_gap"].notna() & (j["true_gap"].abs() > 0)
            if ok.any():
                err = float(((j.loc[ok, "gap"] - j.loc[ok, "true_gap"]).abs() / j.loc[ok, "true_gap"].abs()).median())
        all_rolls.append(rl)
        ok = best[best["kind"] != "MISMATCH"]
        vr = ok["vol_ratio"].replace([np.inf, -np.inf], np.nan)
        s = dict(
            dataset=f"MCX/{f.name}", source="Angel One SmartAPI getCandleData (vendor-stitched front month)",
            reference="MCX official bhavcopy FUTCOM (research-mcx-bhav branch)", instrument=name, exchange="MCX",
            timeframe="ONE_DAY", period=f"{start.date()} – {end.date()}", retrieved_audit=retrieved, data_version=VERSION,
            adjustment="none (raw stitched; back-adjustment = research/roll_adjust.py ESTIMATE)",
            days=len(aw), bhav_sessions=len(sess),
            ohl_match=round(float((best["kind"] != "MISMATCH").mean()), 4),
            exact_ohlc=round(float((best["kind"] == "EXACT").mean()), 4),
            close_definition_diff=round(float((best["kind"] == "CLOSE_DEF").mean()), 4),
            close_def_by_year={int(y): round(float(v), 3) for y, v in
                               (best.assign(y=best["date"].dt.year).groupby("y")["kind"].apply(lambda k: (k == "CLOSE_DEF").mean())).items()},
            missing_sessions=len(missing), missing_sessions_share=round(len(missing) / max(len(sess), 1), 4),
            missing_sample=[str(x) for x in missing[:10]], extra_days=len(extra), extra_sample=[str(x) for x in extra[:10]],
            vol_ratio_median=round(float(vr.median()), 4) if vr.notna().any() else None,
            vol_ratio_within_5pct=round(float(((vr - 1).abs() <= 0.05).mean()), 4) if vr.notna().any() else None,
            vol_zero_share=round(float((aw["volume"] <= 1).mean()), 4),
            used_front=round(float((ok["exp"] == ok["front_exp"]).mean()), 4),
            used_oi_leader=round(float((ok["exp"] == ok["oi_exp"]).mean()), 4),
            used_volume_leader=round(float((ok["exp"] == ok["vol_exp"]).mean()), 4),
            illiquid_share=round(float((ok["share"] < ILLIQ).mean()), 4), illiquid_days=int((ok["share"] < ILLIQ).sum()),
            rolls=len(rl), roll_median_days_after_expiry=float(rl["days_after_old_expiry"].median()) if len(rl) else None,
            roll_true_gap_median_pct=round(float(rl["true_gap_pct"].abs().median()), 3) if len(rl) else None,
            roll_true_gap_max_pct=round(float(rl["true_gap_pct"].abs().max()), 3) if len(rl) else None,
            roll_estimator_found=round(float(rl.get("estimator_found_roll", pd.Series([np.nan])).mean()), 3) if len(rl) else None,
            roll_median_days_on_old_after_oi_roll=float(pd.to_numeric(rl["days_on_old_after_oi_roll"]).median()) if len(rl) else None,
            roll_est_err_median=round(err, 3) if err is not None else None,
            roll_est_proxy_missing=round(float(pd.Series(rl.get("estimator_proxy_missing", [])).astype(float).mean()), 3)
            if len(rl) and "estimator_proxy_missing" in rl else None,
            oi_in_angel=False, oi_source="bhavcopy only (Angel serves no MCX OI history)",
            intraday_1h=intraday(name, a))
        s["daily_close_definition_switch"], s["daily_close_eq_last_trade_recent"] = close_definition_switch(name)
        st, why = grade(s)
        s["status"], s["reasons"] = st, why
        man[name] = s
        best.assign(name=name)[["name", "date", "exp", "front_exp", "oi_exp", "kind", "ohl_err", "close_err", "volume",
                                "volume_lots", "vol_ratio", "share", "oi_lots"]].to_csv(OUT / f"match_{name}.csv.gz", index=False)
    rl = pd.concat([r for r in all_rolls if len(r)], ignore_index=True) if any(len(r) for r in all_rolls) else pd.DataFrame()
    rl.to_csv(OUT / "rolls_true.csv", index=False)
    meta = dict(audit=VERSION, run=retrieved, bhav_files=nfiles, bhav_first=str(b["date"].min().date()),
                bhav_last=str(b["date"].max().date()), tolerance=TOL, illiquid_share_below=ILLIQ)
    (OUT / "manifest.json").write_text(json.dumps(dict(meta=meta, datasets=man), indent=1, default=str))
    return meta, man, rl


if __name__ == "__main__":
    meta, man, rl = audit()
    for n, s in man.items():
        print(n, s.get("status"), "|", "; ".join(s.get("reasons", [])))
        print("   ", {k: s.get(k) for k in ("ohl_match", "exact_ohlc", "missing_sessions", "extra_days", "vol_ratio_median",
                                             "vol_zero_share", "used_front", "used_oi_leader", "illiquid_share", "rolls",
                                             "roll_median_days_after_expiry", "roll_true_gap_median_pct", "roll_est_err_median")})
        print("    1h:", s.get("intraday_1h"))

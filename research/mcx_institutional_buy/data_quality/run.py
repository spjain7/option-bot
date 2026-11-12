"""Data-quality audit: python -m research.mcx_institutional_buy.data_quality.run -> reports/data_quality.json + .md
Checks every source used by the engine: completeness, missing candles, duplicates, timestamps, session boundaries, contract
rolls, volume / OI anomalies, OHLC sanity, market depth, holidays, global benchmarks. Real vs calculated data is labelled."""
import gzip
import io
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.mcx_institutional_buy.backtesting import data as D  # noqa: E402
from research.mcx_institutional_buy.backtesting import costs as K  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "reports"


def angel_file(name, iv):
    d = D._raw(name, iv)
    if d is None:
        return dict(status="UNAVAILABLE")
    t = d.time; hm = t.dt.hour * 60 + t.dt.minute
    step = {"FIVE_MINUTE": 5, "ONE_HOUR": 60, "ONE_DAY": 1440}[iv]
    r = dict(status="REAL (Angel SmartAPI, front-month stitched)", rows=len(d), first=str(t.min()), last=str(t.max()),
             duplicate_timestamps=int(t.duplicated().sum()),
             weekend_bars=int(t.dt.weekday.isin([5, 6]).sum()),
             ohlc_violations=int(((d.high < d[["open", "close"]].max(axis=1)) | (d.low > d[["open", "close"]].min(axis=1)) | (d.high < d.low)).sum()),
             nonpositive_prices=int((d[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
             zero_volume_bars_pct=round(100 * float((d.volume <= 0).mean()), 2),
             volume_spikes_gt20x_median=int((d.volume > 20 * d.volume.rolling(200, min_periods=20).median()).sum()))
    if iv != "ONE_DAY":
        r["misaligned_timestamps"] = int(((hm - 540) % step != 0).sum()) if step < 60 else int((t.dt.minute != 0).sum())
        r["outside_session_bars"] = int(((hm < 540) | (hm >= 23 * 60 + 55)).sum())
        day = t.dt.normalize(); per = d.groupby(day).size()
        exp = per.rolling(20, min_periods=5).median()
        short = per < 0.8 * exp
        r["trading_days"] = int(len(per)); r["days_below_80pct_of_normal_bars"] = int(short.sum())
        r["short_day_examples"] = [str(x.date()) for x in per[short].index[-5:]]
        # missing candles inside the session: gaps larger than one step between consecutive bars on the same day
        gap = t.diff().dt.total_seconds() / 60
        same = day == day.shift(1)
        r["intraday_gaps_gt_1_step"] = int(((gap > step) & same).sum())
        last = d.groupby(day).time.max().dt.strftime("%H:%M").value_counts().head(4).to_dict()
        r["session_last_bar_times"] = last
        bd = pd.bdate_range(t.min().normalize(), t.max().normalize())
        r["weekdays_without_bars"] = int(len(set(bd) - set(per.index)))
    return r


def bhav_audit():
    B = D.bhav()
    out = {}
    files = sorted((D.DATA / "mcx_bhav/days").glob("*.csv"))
    out["files"] = len(files); out["first"] = files[0].stem; out["last"] = files[-1].stem
    for s in D.ALL9:
        g = B[B.symbol == s]
        tot = g.groupby("date").agg(oi=("oi_lots", "sum"), vol=("volume_lots", "sum"))
        ch = tot.oi.pct_change()
        out[s] = dict(status="REAL (MCX official bhavcopy, end-of-day)", days=int(len(tot)), first=str(tot.index.min().date()),
                      last=str(tot.index.max().date()), zero_volume_days=int((tot.vol <= 0).sum()), zero_oi_days=int((tot.oi <= 0).sum()),
                      oi_jumps_gt50pct=int((ch.abs() > 0.5).sum()), median_daily_volume_lots=float(tot.vol.median()),
                      median_total_oi_lots=float(tot.oi.median()),
                      contracts_per_day_median=float(g.groupby("date").size().median()))
    return out


def rolls():
    out = {}
    for s in D.ALL9:
        for tf in ("1h", "1d"):
            b = D.bars(s, tf)
            if b is None:
                continue
            idx = np.where(b.switch.astype(bool).values)[0]
            gaps = [abs(np.log(b.open.iloc[i] / b.close.iloc[i - 1])) for i in idx if i > 0]
            out[f"{s} {tf}"] = dict(switches=int(len(idx)), exact_ratio_from_bhavcopy=int((b.roll_src == 1).sum()),
                                    inferred_ratio=int((b.roll_src == 2).sum()),
                                    median_abs_switch_gap_pct=round(100 * float(np.median(gaps)), 2) if gaps else None,
                                    max_abs_switch_gap_pct=round(100 * float(np.max(gaps)), 2) if gaps else None)
    return out


def depth():
    """MCX best-5 snapshots recorded by the live WebSocket (ws-depth branch). Forward only: no history exists."""
    try:
        files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "origin/ws-depth"], cwd=ROOT, text=True).split()
    except Exception:
        return dict(status="UNAVAILABLE (ws-depth branch not fetched)")
    rows = []
    for f in [x for x in files if x.endswith(".csv.gz")]:
        raw = subprocess.check_output(["git", "show", f"origin/ws-depth:{f}"], cwd=ROOT)
        d = pd.read_csv(io.BytesIO(gzip.decompress(raw)))
        rows.append(d[d.exch == "MCX"])
    if not rows:
        return dict(status="UNAVAILABLE")
    d = pd.concat(rows, ignore_index=True)
    out = dict(status="REAL (Angel SNAP_QUOTE best-5) but FORWARD ONLY: first snapshot " + str(d.time.min()), snapshots=int(len(d)),
               files=len(rows), per_symbol={})
    for s, g in d.groupby("name"):
        base = next((k for k in D.ALL9 if str(s).upper().startswith(k)), None)
        tick = K.spec(base)["tick"] if base else np.nan
        # recorder columns A* hold the SDK "best_5_buy" side (the BID in 98-99 % of snapshots, DEPTH_AUDIT.md), B* the ask
        ok = (g.A1p > 0) & (g.B1p > 0) & (g.B1p >= g.A1p)
        sp = (g.B1p - g.A1p)[ok]
        out["per_symbol"][str(s)] = dict(snapshots=int(len(g)), valid_two_sided_pct=round(100 * float(ok.mean()), 1),
                                         median_spread_ticks=round(float(sp.median() / tick), 2) if len(sp) and tick == tick else None,
                                         p90_spread_ticks=round(float(sp.quantile(0.9) / tick), 2) if len(sp) and tick == tick else None,
                                         crossed=int(((g.A1p > g.B1p) & (g.B1p > 0)).sum()))
    return out


def holidays():
    bh = set(pd.to_datetime([p.stem for p in (D.DATA / "mcx_bhav/days").glob("*.csv")]))
    d = D._raw("GOLD", "ONE_DAY"); ang = set(d.time[d.time >= "2022-07-01"].dt.normalize())
    return dict(angel_days_missing_bhavcopy=sorted(str(x.date()) for x in ang - bh)[:30], n_angel_without_bhav=len(ang - bh),
                bhav_days_missing_angel_daily=len(bh - ang), examples_bhav_without_angel=sorted(str(x.date()) for x in bh - ang)[-10:])


def global_sources():
    out = {}
    for s in D.ALL9:
        p = D.proxy_daily(s)
        out[s] = "UNAVAILABLE" if p is None else f"REAL (Yahoo daily continuous, USD) {p.index.min().date()}..{p.index.max().date()}"
    out["USDINR"] = "REAL (Yahoo daily)"
    for k in ("Dollar index", "US yields", "Brent", "EIA crude inventory", "Henry Hub storage / weather", "LME official prices",
              "LME / SHFE inventories", "China demand indicators"):
        out[k] = "UNAVAILABLE in this environment (no data file, outbound network restricted)"
    return out


def main():
    res = dict(angel={}, bhav=bhav_audit(), rolls=rolls(), depth=depth(), holidays=holidays(), global_sources=global_sources())
    for s in D.INTRA:
        for iv in ("FIVE_MINUTE", "ONE_HOUR", "ONE_DAY"):
            res["angel"][f"{s} {iv}"] = angel_file(s, iv)
    for s in ("LEAD", "NICKEL"):
        res["angel"][f"{s} ALL"] = "UNAVAILABLE (no Angel files; daily series built from the bhavcopy)"
    res["real_vs_calculated"] = {
        "REAL": ["Angel 5-minute / 1-hour / daily OHLCV (7 commodities)", "MCX bhavcopy daily OHLC, volume, OI (9 commodities)",
                 "Yahoo international futures daily (6), USDINR daily", "MCX best-5 depth snapshots (forward, from 11-Nov-2026)"],
        "CALCULATED": ["15m / 30m from 5m; 4h from 1h", "LEAD / NICKEL daily continuous from bhavcopy",
                       "roll ratios and back-adjusted prices (indicators only)", "daily total OI = sum over expiries", "all indicators"],
        "INFERRED (disclosed)": ["pre-Jul-2022 daily roll ratios (switch open / previous close)",
                                 "LOWIMPACT_PROXY (high volume, small range) - NOT observed absorption"],
        "NOT AVAILABLE (experiments marked unavailable)": ["historical order book / depth", "trade-by-trade aggressor side, volume delta, footprint",
                                                            "historical intraday OI", "LEAD / NICKEL intraday", "NICKEL tradable history before Jun-2025"]}
    (OUT / "data_quality.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: (v if k in ("depth", "holidays") else "...") for k, v in res.items()}, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()

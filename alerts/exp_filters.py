"""ALERT-EXP-002 – which extra filter cuts fake RSI-reversal alerts? (research only)  python -m alerts.exp_filters

Baseline = the LIVE alert rule (RSI extreme + reversal candle + quality layer). Each filter is tested ALONE on top of it:
  F1 higher-timeframe trend : BUY only if the previous session's close > daily EMA20 (SELL only if below)
  F2 RSI divergence         : BUY only if price made a lower low than the last confirmed swing low (≤ 30 candles back)
                              while RSI made a higher low there (mirror for SELL)
  F3 next-candle confirm    : enter only if the NEXT candle trades through the signal candle's high (BUY) / low (SELL);
                              fill at that level (or the open if it gaps through); otherwise no trade
Pre-registered decision (written before the run, in alerts/EXPERIMENTS.md):
  switch a filter ON only if, pooled over all instruments/timeframes,
    (a) average R improves by ≥ +0.05R vs baseline, (b) the improvement holds in BOTH halves (≤2023, ≥2024),
    (c) it improves ≥ 60% of the instrument×timeframe groups that have ≥ 10 trades under both,
    (d) bootstrap 5th percentile of the improvement > 0, (e) ≥ 100 trades remain.
Everything is exploratory: this 2020-26 history has been looked at before.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from alerts import signals as S, stats as ST  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "alerts" / "results" / "EXP-002"
MAX_HOLD, COST_R = 20, ST.COST_R


def outcome(df, i0, entry, sl, s):
    """Score from candle i0 (the fill candle, stop checked in it too). Half at T1 (SL to entry), rest T2 / time exit."""
    dist = s * (entry - sl)
    t1, t2 = entry + s * dist, entry + 2 * s * dist
    t1hit = False
    for j in range(i0, min(i0 + MAX_HOLD, len(df))):
        h, l = df.at[j, "high"], df.at[j, "low"]
        stop = entry if t1hit else sl
        if (l <= stop) if s > 0 else (h >= stop):
            return (0.5 if t1hit else -1.0) - COST_R, t1hit
        if not t1hit and ((h >= t1) if s > 0 else (l <= t1)):
            t1hit = True
        if (h >= t2) if s > 0 else (l <= t2):
            return 1.5 - COST_R, True
    last = df.at[min(i0 + MAX_HOLD - 1, len(df) - 1), "close"]
    r = (0.5 + 0.5 * s * (last - entry) / dist) if t1hit else s * (last - entry) / dist
    return r - COST_R, t1hit


def daily_trend(df):
    d = df.groupby(df["time"].dt.normalize())["close"].last()
    e = I.ema(d, 20)
    lab = pd.Series(np.where(d > e, "UP", "DOWN"), index=d.index).where(e.notna(), "NA")
    return lab.shift(1)                              # previous completed session only


def divergence(df, r, i, side, k=2, back=30):
    lo, hi = I.pivots(df.iloc[max(0, i - back):i - 2].reset_index(drop=True), k)
    off = max(0, i - back)
    w = df.iloc[i - 2:i + 1]
    if side == "BUY":
        if not lo:
            return False
        j, p = lo[-1]
        cur_low = w["low"].min()
        return cur_low < p and np.nanmin(r[i - 2:i + 1]) > r[off + j]
    if not hi:
        return False
    j, p = hi[-1]
    return w["high"].max() > p and np.nanmax(r[i - 2:i + 1]) < r[off + j]


def run_one(df, h1, name, tf):
    df = df.reset_index(drop=True)
    r = I.rsi(df["close"], 14).values
    atr = I.atr(df, 14).values
    dtr = daily_trend(h1 if h1 is not None else df)
    rows = []
    for i in range(60, len(df) - 2):
        lo, hi = np.nanmin(r[i - 2:i + 1]), np.nanmax(r[i - 2:i + 1])
        if not (lo < S.RSI_BUY or hi > S.RSI_SELL) or not np.isfinite(atr[i]):
            continue
        bull, bear = S.patterns(df.iloc[i - 2:i + 1], atr[i])
        if not ((lo < S.RSI_BUY and bull) or (hi > S.RSI_SELL and bear)):
            continue
        hw = h1[h1["time"] <= df.at[i, "time"]].tail(200) if h1 is not None else None
        ev = S.evaluate(df.iloc[max(0, i - 300):i + 1], tf, hw)
        if ev["kind"] not in ("BUY", "SELL"):
            continue                                  # baseline = what the LIVE rule sends
        side, s = ev["kind"], (1 if ev["kind"] == "BUY" else -1)
        sl = ev["sl"]
        e0 = df.at[i + 1, "open"]
        if s * (e0 - sl) <= 0:
            continue
        base_r, _ = outcome(df, i + 1, e0, sl, s)
        # F3: stop-entry beyond the signal candle, valid for the next candle only
        trig = df.at[i, "high"] if s > 0 else df.at[i, "low"]
        nh, nl, no = df.at[i + 1, "high"], df.at[i + 1, "low"], df.at[i + 1, "open"]
        hit = (nh >= trig) if s > 0 else (nl <= trig)
        f3_r = None
        if hit:
            fill = max(no, trig) if s > 0 else min(no, trig)
            if s * (fill - sl) > 0:
                f3_r, _ = outcome(df, i + 1, fill, sl, s)
        day = df.at[i, "time"].normalize()
        trend = dtr.get(day, "NA")
        rows.append(dict(name=name, tf=tf, time=df.at[i, "time"], side=side, base=base_r,
                         f1=(trend == "UP") if s > 0 else (trend == "DOWN"), f1_known=trend != "NA",
                         f2=divergence(df, r, i, side), f3_r=f3_r))
    return pd.DataFrame(rows)


def compare(t, mask, rcol="base"):
    """Filter = keep rows where mask; returns stats + diff vs baseline."""
    kept = t[mask]
    rr = kept[rcol] if rcol == "base" else kept["f3_r"]
    rr = rr.dropna()
    return rr


def main():
    frames = []
    for exch, name in (("MCX", "CRUDEOIL"), ("MCX", "GOLD"), ("MCX", "SILVER"), ("MCX", "NATURALGAS"), ("MCX", "COPPER"),
                       ("NFO", "NIFTY"), ("NFO", "BANKNIFTY")):
        for tf, iv in (("15m", "FIFTEEN_MINUTE"), ("1h", "ONE_HOUR"), ("3h", "ONE_HOUR")):
            f = ST.front_file(exch, name, iv)
            if f is None or not f.exists():
                continue
            d = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
            h1 = d if iv == "ONE_HOUR" else d.groupby(d["time"].dt.floor("h")).agg(
                time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)
            src = ST.three_hour_generic(d) if tf == "3h" else d
            t = run_one(src, h1, name, tf)
            print(name, tf, len(t), flush=True)
            frames.append(t)
    T = pd.concat(frames, ignore_index=True)
    T["half"] = np.where(T["time"] < pd.Timestamp("2024-01-01"), "2020-23", "2024-26")
    variants = {"baseline": (pd.Series(True, index=T.index), "base"), "F1 daily trend": (T["f1"], "base"),
                "F2 RSI divergence": (T["f2"], "base"), "F3 next-candle confirm": (T["f3_r"].notna(), "f3")}
    rng = np.random.default_rng(7)
    base_mean = T["base"].mean()
    res = {}
    for v, (m, col) in variants.items():
        rr = compare(T, m, col)
        sub = T[m].copy()
        sub["rv"] = sub["base"] if col == "base" else sub["f3_r"]
        sub = sub.dropna(subset=["rv"])
        diff_boot = []
        for _ in range(3000):                            # resample groups of the whole candidate set
            idx = rng.integers(0, len(T), len(T))
            bt = T.iloc[idx]
            bm = m.iloc[idx]
            bv = (bt["base"] if col == "base" else bt["f3_r"])[bm.values].dropna()
            diff_boot.append((bv.mean() if len(bv) else np.nan) - bt["base"].mean())
        halves = {h: round(float(g["rv"].mean() - T[T["half"] == h]["base"].mean()), 3) for h, g in sub.groupby("half")}
        groups = []
        for (n, tf), g in T.groupby(["name", "tf"]):
            gv = g[m[g.index]]
            gv = (gv["base"] if col == "base" else gv["f3_r"]).dropna()
            if len(gv) >= 10 and len(g) >= 10:
                groups.append(gv.mean() > g["base"].mean())
        w, l = rr[rr > 0], rr[rr <= 0]
        imp = rr.mean() - base_mean
        res[v] = dict(trades=int(len(rr)), kept_pct=round(len(rr) / len(T) * 100, 1), avg_r=round(float(rr.mean()), 3),
                      win_pct=round(float((rr > 0).mean() * 100), 1), pf=round(float(w.sum() / -l.sum()), 2) if l.sum() < 0 else None,
                      improvement_r=round(float(imp), 3), improvement_by_half=halves,
                      groups_improved=f"{sum(groups)}/{len(groups)}",
                      boot_p5_improvement=round(float(np.nanpercentile(diff_boot, 5)), 3),
                      losers_removed_pct=round(float(100 - (rr <= 0).sum() / max(1, (T["base"] <= 0).sum()) * 100), 1),
                      winners_kept_pct=round(float((rr > 0).sum() / max(1, (T["base"] > 0).sum()) * 100), 1))
        if v != "baseline":
            c = res[v]
            c["decision_checks"] = {"≥ +0.05R": imp >= 0.05, "both halves better": all(x > 0 for x in halves.values()) and len(halves) == 2,
                                    "≥60% groups better": bool(groups) and sum(groups) / len(groups) >= 0.6,
                                    "bootstrap p5 > 0": c["boot_p5_improvement"] > 0, "≥ 100 trades": len(rr) >= 100}
            c["switch_on"] = all(c["decision_checks"].values())
        print(v, res[v], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "candidates.csv", index=False)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()

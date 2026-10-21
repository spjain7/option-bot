"""Contract-level data for the MCX paper engine: store, validation, roll mapping and the signal series.

Facts this module is built on (verified):
  * Angel's history on the NEAREST contract token is a vendor-stitched front month: it shows the expiring contract up
    to its expiry and the next contract from the following day, NOT back-adjusted.
  * Angel serves each listed contract's own candles (token + expiry) only while it is listed; expired contracts are
    not served, so past roll gaps cannot be measured after the fact.

Method:
  * ContractStore records every listed front/next contract's daily candles each run (persisted). From then on, the gap
    at each switch is EXACT: next-contract close minus expiring-contract close on the same day, from recorded data.
  * Vendor days are mapped to a contract by matching closes with the store; a change of mapped contract is a switch.
    Switches before the store has both contracts (history) are detected by the volume-jump rule and marked UNKNOWN.
  * The signal series is back-adjusted by EXACT gaps only. A bar whose breakout/ATR window contains an UNKNOWN switch
    is flagged; the engine then refuses to confirm a signal on it (NO TRADE). Estimated gaps are never used live.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

OHLC = ["open", "high", "low", "close"]


# ─────────────── data validation ───────────────
def validate(df, now=None, stale_days=4, hole_days=7):
    """Returns (clean frame, list of issues). Duplicate timestamps are dropped (first kept); rows with impossible OHLC
    are dropped; holes and staleness are reported (never filled)."""
    issues = []
    if df is None or df.empty:
        return df, ["no data"]
    d = df.copy()
    d["time"] = pd.to_datetime(d["time"])
    d = d.sort_values("time")
    dup = d["time"].duplicated()
    if dup.any():
        issues.append(f"{int(dup.sum())} duplicate candle(s) removed")
        d = d[~dup]
    bad = (d[OHLC] <= 0).any(axis=1) | (d["high"] < d[["open", "close", "low"]].max(axis=1)) | \
          (d["low"] > d[["open", "close", "high"]].min(axis=1)) | d[OHLC].isna().any(axis=1)
    if bad.any():
        issues.append(f"{int(bad.sum())} candle(s) with impossible OHLC removed (last {d.loc[bad, 'time'].max().date()})")
        d = d[~bad]
    g = d["time"].diff().dt.days
    if (g > hole_days).any():
        last = d.loc[g > hole_days, "time"].max()
        issues.append(f"data hole: {int(g.max())} days (latest hole ends {last.date()})")
    if now is not None and len(d):
        age = (pd.Timestamp(now).normalize() - d["time"].iloc[-1].normalize()).days
        if age > stale_days:
            issues.append(f"stale: last candle {d['time'].iloc[-1].date()} is {age} days old")
    return d.reset_index(drop=True), issues


# ─────────────── contract store ───────────────
class ContractStore:
    """Per-contract daily candles (symbol, token, expiry) recorded run after run. Directory layout:
    <dir>/<SYMBOL>.csv and <dir>/meta.json"""
    def __init__(self, folder):
        self.dir = Path(folder); self.dir.mkdir(parents=True, exist_ok=True)
        mf = self.dir / "meta.json"
        self.meta = json.loads(mf.read_text()) if mf.exists() else {}

    def put(self, symbol, name, token, expiry, candles):
        f = self.dir / f"{symbol}.csv"
        new = candles[["time"] + OHLC + ["volume"]].copy()
        new["time"] = pd.to_datetime(new["time"]).dt.normalize()
        if f.exists():
            old = pd.read_csv(f, parse_dates=["time"])
            new = pd.concat([old, new]).drop_duplicates("time", keep="last")
        new.sort_values("time").to_csv(f, index=False)
        self.meta[symbol] = dict(name=name, token=str(token), expiry=str(pd.Timestamp(expiry).date()))
        (self.dir / "meta.json").write_text(json.dumps(self.meta, indent=1))

    def get(self, symbol):
        f = self.dir / f"{symbol}.csv"
        return pd.read_csv(f, parse_dates=["time"]) if f.exists() else None

    def contracts(self, name):
        rows = [dict(symbol=s, **m) for s, m in self.meta.items() if m["name"] == name]
        return sorted(rows, key=lambda r: r["expiry"])

    def bar(self, symbol, day):
        d = self.get(symbol)
        if d is None:
            return None
        r = d[d["time"] == pd.Timestamp(day).normalize()]
        return None if r.empty else r.iloc[0]


# ─────────────── vendor series -> contract mapping and exact gaps ───────────────
def map_vendor(vendor, store, name, tol=0.0005):
    """For each vendor day, which recorded contract has the same close (relative tolerance). NaN = not recorded."""
    v = vendor.copy(); v["day"] = v["time"].dt.normalize(); v["contract"] = None
    for c in store.contracts(name):
        cd = store.get(c["symbol"])
        if cd is None:
            continue
        m = v[["day", "close"]].merge(cd[["time", "close"]].rename(columns={"time": "day", "close": "cc"}), on="day", how="left")
        hit = (m["cc"] - m["close"]).abs() <= tol * m["close"].abs()
        v.loc[hit.values & v["contract"].isna().values, "contract"] = c["symbol"]
    return v


def switches(vendor_mapped, store, name, unknown_days):
    """List of switches: dict(day=first day on the new contract, gap=exact or None, old, new)."""
    out = []
    v = vendor_mapped
    known = v.dropna(subset=["contract"])
    for k in range(1, len(known)):
        a, b = known.iloc[k - 1], known.iloc[k]
        if a["contract"] != b["contract"]:
            nb = store.bar(b["contract"], a["day"])                      # new contract's close on the old one's last day
            gap = None if nb is None else float(nb["close"] - a["close"])
            out.append(dict(day=b["day"], old=a["contract"], new=b["contract"], gap=gap,
                            method="exact (recorded contract closes)" if gap is not None else "unknown"))
    covered = set(x["day"] for x in out)
    first_known = known["day"].min() if len(known) else None
    for d in unknown_days:                                               # history before the store: unknown
        d = pd.Timestamp(d).normalize()
        if first_known is not None and d >= first_known:
            continue
        if d not in covered:
            out.append(dict(day=d, old=None, new=None, gap=None, method="unknown (before contract recording began)"))
    return sorted(out, key=lambda x: x["day"])


def signal_series(vendor, store, name, unknown_days, window=56):
    """Back-adjust the vendor series by EXACT gaps only; flag bars whose signal window holds an unknown switch."""
    v = map_vendor(vendor, store, name)
    sw = switches(v, store, name, unknown_days)
    v = v.reset_index(drop=True)
    gap = np.zeros(len(v)); unk = np.zeros(len(v), bool)
    for s in sw:
        idx = v.index[v["day"] >= s["day"]]
        if len(idx) == 0:
            continue
        i = idx[0]
        if s["gap"] is not None and i > 0:
            gap[i - 1] += s["gap"]                                       # prices before the switch shift by the gap
        elif s["gap"] is None:
            unk[i] = True
    shift = pd.Series(gap)[::-1].cumsum()[::-1].values
    for k in OHLC:
        v["raw_" + k] = v[k]; v[k] = v[k] + shift
    v["unknown_switch"] = unk
    v["unknown_in_window"] = pd.Series(unk.astype(int)).rolling(window, min_periods=1).max().astype(bool).values
    return v, sw

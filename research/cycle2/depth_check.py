"""Cycle 2 · 5 – validation of the LIVE Best-5 depth recorded by the production collector (ws-depth branch, from
11-Nov-2026). Checks, per exchange and instrument kind (MCX future, NSE stock future, NSE index future, NSE index spot,
NSE cash):
  ordering      which SDK list is the bid (A1 < B1 or A1 > B1), crossed / locked books, level monotonicity
  completeness  filled levels per side, zero-quantity levels
  timestamps    exchange time vs receive time (lag), stale snapshots (exchange time unchanged), minutes covered
  spread        (ask - bid) / mid in basis points
  persistence   files and rows saved per job, tokens with data vs tokens subscribed
No strategy uses depth: there is no history, and a few days of snapshots are not evidence.
python -m research.cycle2.depth_check  ->  results/depth_check.json"""
import io
import json
import subprocess
import numpy as np
import pandas as pd

from research.cycle2 import common as C


def load():
    root = str(C.ROOT)
    subprocess.run(["git", "-C", root, "fetch", "-q", "origin", "ws-depth"], check=True)
    names = subprocess.run(["git", "-C", root, "ls-tree", "-r", "--name-only", "FETCH_HEAD"], check=True, capture_output=True, text=True).stdout.split()
    parts, status, files = [], {}, []
    for n in names:
        blob = subprocess.run(["git", "-C", root, "show", f"FETCH_HEAD:{n}"], check=True, capture_output=True).stdout
        if n.endswith(".csv.gz"):
            x = pd.read_csv(io.BytesIO(blob), compression="gzip", dtype={"token": str}); x["file"] = n; parts.append(x)
            files.append(dict(file=n, rows=len(x), bytes=len(blob)))
        elif n.endswith("_status.json"):
            status[n] = json.loads(blob)
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()), status, files


def kind(r):
    if r.exch == "MCX":
        return "MCX future"
    if r.exch == "NSE":
        return "NSE index spot" if str(r.token).startswith("999") else "NSE cash"
    s = str(r.get("symbol", ""))
    return "NSE index future" if any(s.startswith(i) for i in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")) else "NSE stock future"


def main():
    X, status, files = load()
    out = dict(files=files, collector_status=status)
    if not len(X):
        out["verdict"] = "no depth file saved yet"
        json.dump(out, open(C.OUT / "depth_check.json", "w"), indent=1, default=str); print(out); return
    X["kind"] = X.apply(kind, axis=1)
    X["t"] = pd.to_datetime(X["time"])
    A = X[[f"A{i}p" for i in range(1, 6)]].values; B = X[[f"B{i}p" for i in range(1, 6)]].values
    Aq = X[[f"A{i}q" for i in range(1, 6)]].values; Bq = X[[f"B{i}q" for i in range(1, 6)]].values
    a1, b1 = A[:, 0], B[:, 0]
    X["filled_A"] = (A > 0).sum(1); X["filled_B"] = (B > 0).sum(1)
    X["both"] = (a1 > 0) & (b1 > 0)
    X["A_is_bid"] = X.both & (a1 < b1); X["B_is_bid"] = X.both & (b1 < a1); X["locked"] = X.both & (a1 == b1)
    bid = np.where(X.A_is_bid, a1, b1); ask = np.where(X.A_is_bid, b1, a1)
    X["spread_bp"] = np.where(X.both & (ask > bid), 1e4 * (ask - bid) / ((ask + bid) / 2), np.nan)
    # level monotonicity on the side identified as bid (descending) / ask (ascending), filled levels only
    def mono(P, desc):
        ok = []
        for row in P:
            v = row[row > 0]
            ok.append(bool(len(v) < 2 or (np.all(np.diff(v) <= 0) if desc else np.all(np.diff(v) >= 0))))
        return np.array(ok)
    bidP = np.where(X.A_is_bid.values[:, None], A, B); askP = np.where(X.A_is_bid.values[:, None], B, A)
    X["bid_mono"] = mono(bidP, True); X["ask_mono"] = mono(askP, False)
    X["zero_qty_levels"] = ((A > 0) & (Aq <= 0)).sum(1) + ((B > 0) & (Bq <= 0)).sum(1)
    X["recv_dt"] = pd.to_datetime(X["time"].str[:10] + " " + X["recv"].astype(str), errors="coerce")
    X["lag_s"] = (X.recv_dt - X.t).dt.total_seconds()
    X = X.sort_values(["token", "t"])
    X["stale"] = X.groupby("token").t.diff().dt.total_seconds().eq(0)
    rep = {}
    for k, g in X.groupby("kind"):
        mins = g.groupby("token").t.agg(lambda s: s.dt.floor("min").nunique())
        rep[k] = dict(rows=len(g), tokens=int(g.token.nunique()), days=sorted(g.t.dt.date.astype(str).unique()),
                      both_sides_pct=round(100 * g.both.mean(), 1), sdk_A_list_is_bid_pct=round(100 * g.A_is_bid.mean(), 1),
                      sdk_B_list_is_bid_pct=round(100 * g.B_is_bid.mean(), 1), locked_pct=round(100 * g.locked.mean(), 2),
                      five_levels_both_sides_pct=round(100 * ((g.filled_A == 5) & (g.filled_B == 5)).mean(), 1),
                      levels_filled_median=f"{g.filled_A.median():.0f} x {g.filled_B.median():.0f}",
                      bid_levels_descending_pct=round(100 * g.bid_mono.mean(), 1), ask_levels_ascending_pct=round(100 * g.ask_mono.mean(), 1),
                      zero_qty_levels_per_row=round(float(g.zero_qty_levels.mean()), 3),
                      lag_s_median=round(float(g.lag_s.median()), 2), lag_s_p95=round(float(g.lag_s.quantile(0.95)), 2),
                      lag_negative_pct=round(100 * float((g.lag_s < -1).mean()), 2), stale_pct=round(100 * float(g.stale.mean()), 2),
                      minutes_per_token_median=float(mins.median()),
                      spread_bp_median=round(float(np.nanmedian(g.spread_bp)), 2) if g.spread_bp.notna().any() else None,
                      spread_bp_p90=round(float(np.nanpercentile(g.spread_bp.dropna(), 90)), 2) if g.spread_bp.notna().any() else None)
    out["by_kind"] = rep
    out["spread_bp_by_symbol_top"] = X.groupby(["kind", "symbol"]).spread_bp.median().dropna().round(2).groupby(level=0).apply(
        lambda s: s.sort_values().iloc[[0, len(s) // 2, -1]].to_dict() if len(s) else {}).to_dict() if "symbol" in X else {}
    json.dump(out, open(C.OUT / "depth_check.json", "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()

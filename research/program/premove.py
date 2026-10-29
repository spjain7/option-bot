"""PREMOVE-001 (29-Oct-2026, owner: "what do volume / OI do BEFORE every 1-2 % move – find the hint").
Event = a quiet stretch, then a fast move: price was within ±0.4 % over the previous 30 min, and within the next 60 min it travels
≥ 1.5 % in one direction before going 0.5 % the other way. For the 30-60 min BEFORE each move start we measure:
  vol30 / vol60  volume vs the same time of day over the previous 10 sessions (5-min: NSE cash, all F&O stocks, ~3 months)
  oi30 / oi60    futures OI change (15-min futures with OI, 40 stocks, 20-Aug → 22-Oct; 5-min OI only from the live recorder)
  squeeze        range of the last 60 min ÷ the stock's average daily range
  vwap_pos       close vs the day's VWAP (in daily-range units) · near_hi / near_lo  within 0.2 daily range of the day's high / low
  drift30        tiny price drift in the last 30 min (in daily-range units) · nifty30  NIFTY futures move in the last 30 min
Output: how each hint differs before UP moves, DOWN moves and at ordinary times; how often a move follows when a hint shows
(vs normal); and whether the hint tells the direction.
python research/program/premove.py 5m|15m"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/program/results"


def load(kind):
    if kind == "5m":
        src = sorted((ROOT / "research/data/m5").glob("eq_*.csv")); bar = 5
    else:
        src = [p for p in sorted((ROOT / "research/data/obuy").glob("fut_*.csv")) if p.stem[4:] not in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")]; bar = 15
    return src, bar


def prep(p, bar):
    d = pd.read_csv(p, parse_dates=["time"]).sort_values("time").drop_duplicates("time")
    d["time"] = pd.to_datetime(d["time"]).dt.tz_localize(None) if getattr(d["time"].dt, "tz", None) is not None else d["time"]
    d = d[(d["time"].dt.strftime("%H:%M") >= "09:15") & (d["time"].dt.strftime("%H:%M") < "15:30")].reset_index(drop=True)
    d["day"] = d["time"].dt.normalize(); d["slot"] = d["time"].dt.strftime("%H:%M")
    n30, n60 = 30 // bar, 60 // bar
    tp = (d["high"] + d["low"] + d["close"]) / 3
    d["vwap"] = (tp * d["volume"]).groupby(d["day"]).cumsum() / d["volume"].groupby(d["day"]).cumsum().replace(0, np.nan)
    dr = d.groupby("day").agg(h=("high", "max"), l=("low", "min"))
    adr = ((dr["h"] - dr["l"]).rolling(10, min_periods=5).mean().shift(1))
    d["adr"] = d["day"].map(adr)
    d["dhi"] = d.groupby("day")["high"].cummax(); d["dlo"] = d.groupby("day")["low"].cummin()
    slotavg = d.groupby("slot")["volume"].transform(lambda v: v.shift(1).rolling(10, min_periods=5).mean())
    v30 = d["volume"].rolling(n30).sum(); a30 = slotavg.rolling(n30).sum()
    v60 = d["volume"].rolling(n60).sum(); a60 = slotavg.rolling(n60).sum()
    d["vol30"], d["vol60"] = v30 / a30, v60 / a60
    if "oi" in d and d["oi"].notna().mean() > 0.5:
        d["oi30"] = d["oi"] / d["oi"].shift(n30) - 1; d["oi60"] = d["oi"] / d["oi"].shift(n60) - 1
    else:
        d["oi30"] = d["oi60"] = np.nan
    d["squeeze"] = (d["high"].rolling(n60).max() - d["low"].rolling(n60).min()) / d["adr"]
    d["vwap_pos"] = (d["close"] - d["vwap"]) / d["adr"]
    d["near_hi"] = ((d["dhi"] - d["close"]) / d["adr"] <= 0.2).astype(int)
    d["near_lo"] = ((d["close"] - d["dlo"]) / d["adr"] <= 0.2).astype(int)
    d["drift30"] = (d["close"] - d["close"].shift(n30)) / d["adr"]
    quiet = (d["close"] / d["close"].shift(n30) - 1).abs() <= 0.004
    c, h, l = d["close"].values, d["high"].values, d["low"].values
    lab = np.zeros(len(d), int)
    same = d["day"].values
    for i in np.flatnonzero(quiet.values):
        up_t = c[i] * 1.015; dn_t = c[i] * 0.985; up_x = c[i] * 1.005; dn_x = c[i] * 0.995
        hit_up = hit_dn = False; bad_up = bad_dn = False
        for j in range(i + 1, min(i + 1 + n60, len(d))):
            if same[j] != same[i]:
                break
            if not hit_up and not bad_up:
                if l[j] <= dn_x: bad_up = True
                elif h[j] >= up_t: hit_up = True
            if not hit_dn and not bad_dn:
                if h[j] >= up_x: bad_dn = True
                elif l[j] <= dn_t: hit_dn = True
        lab[i] = 1 if hit_up and not hit_dn else (-1 if hit_dn and not hit_up else 0)
    d["event"] = np.where(quiet, lab, np.nan)
    d["hm_ok"] = (d["slot"] >= "09:45") & (d["slot"] <= "14:30")
    return d[quiet & d["hm_ok"] & d["adr"].notna()]


def main(kind):
    src, bar = load(kind)
    nifty = ROOT / "research/data/obuy/fut_NIFTY.csv"
    parts = []
    for p in src:
        try:
            x = prep(p, bar)
        except Exception as e:
            print("skip", p.name, e); continue
        x["name"] = p.stem.split("_", 1)[1]
        parts.append(x)
    X = pd.concat(parts, ignore_index=True)
    if nifty.exists():
        n = pd.read_csv(nifty, parse_dates=["time"]).sort_values("time")
        n["n30"] = n["close"].pct_change(30 // 15)
        X = pd.merge_asof(X.sort_values("time"), n[["time", "n30"]], on="time", direction="backward")
    X.to_csv(OUT / f"premove_{kind}.csv.gz", index=False)
    ev = X["event"]
    base_up, base_dn = (ev == 1).mean(), (ev == -1).mean()
    print(f"{kind}: {X['name'].nunique()} stocks, {X['day'].nunique()} sessions, {len(X):,} quiet moments; "
          f"a ≥1.5 % move followed within 60 min: UP {base_up * 100:.2f} %, DOWN {base_dn * 100:.2f} % (= normal chance)")
    feats = ["vol30", "vol60", "oi30", "oi60", "squeeze", "vwap_pos", "near_hi", "near_lo", "drift30", "n30"]
    print("\nMEDIAN of each hint: before UP moves | before DOWN moves | ordinary quiet moments")
    for f in feats:
        if X[f].notna().sum() < 1000:
            continue
        print(f"  {f:9s} {X.loc[ev == 1, f].median():9.4f} | {X.loc[ev == -1, f].median():9.4f} | {X.loc[ev == 0, f].median():9.4f}")
    print(f"\nWHEN THE HINT SHOWS -> chance of a 1.5 pct move in the next hour (normal: up {base_up * 100:.2f} / down {base_dn * 100:.2f})")
    rows = []
    for f in feats:
        x = X[[f, "event"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(x) < 2000:
            continue
        if x[f].nunique() <= 3:
            b = x.groupby(f)["event"]
        else:
            q = x[f].quantile(np.linspace(0, 1, 11)).values
            b = x.groupby(pd.cut(x[f], np.unique(q), include_lowest=True), observed=True)["event"]
        for k, g in b:
            rows.append(dict(hint=f, bucket=str(k), n=len(g), up=(g == 1).mean() * 100, down=(g == -1).mean() * 100,
                             lift=((g != 0).mean()) / ((x["event"] != 0).mean()), up_share=(g == 1).sum() / max((g != 0).sum(), 1) * 100))
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
    print(R.sort_values("lift", ascending=False).head(15).round(2).to_string(index=False))
    # combinations a trader would use
    combos = {"volume ≥ 2× in last 30 min": X["vol30"] >= 2, "volume ≥ 3×": X["vol30"] >= 3,
              "squeeze (60-min range ≤ 0.25 day range)": X["squeeze"] <= 0.25,
              "volume ≥ 2× + squeeze": (X["vol30"] >= 2) & (X["squeeze"] <= 0.25),
              "near day high + volume ≥ 2×": (X["near_hi"] == 1) & (X["vol30"] >= 2),
              "near day low + volume ≥ 2×": (X["near_lo"] == 1) & (X["vol30"] >= 2),
              "OI up ≥ 1 % in 30 min": X["oi30"] >= 0.01, "OI down ≥ 1 % in 30 min": X["oi30"] <= -0.01,
              "OI up ≥ 1 % + volume ≥ 2×": (X["oi30"] >= 0.01) & (X["vol30"] >= 2),
              "above VWAP + near high + volume ≥ 2×": (X["vwap_pos"] > 0) & (X["near_hi"] == 1) & (X["vol30"] >= 2),
              "below VWAP + near low + volume ≥ 2×": (X["vwap_pos"] < 0) & (X["near_lo"] == 1) & (X["vol30"] >= 2)}
    print("\nTRADER-STYLE HINTS -> what followed in the next hour")
    for k, m in combos.items():
        g = X.loc[m, "event"].dropna()
        if len(g) < 30:
            print(f"  {k:42s} too few ({len(g)})"); continue
        print(f"  {k:42s} n {len(g):6d}  move up {(g == 1).mean() * 100:5.2f} %  move down {(g == -1).mean() * 100:5.2f} %  "
              f"any {(g != 0).mean() * 100:5.2f} % ({(g != 0).mean() / (X['event'] != 0).mean():.1f}× normal)  "
              f"of the moves, up {(g == 1).sum() / max((g != 0).sum(), 1) * 100:4.0f} %")
    R.to_csv(OUT / f"premove_{kind}_lift.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "5m")

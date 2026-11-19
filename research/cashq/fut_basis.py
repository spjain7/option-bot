"""FUT-BASIS-001 (19-Nov-2026, owner: "go deeper, find setups for NSE futures"). NSE-futures-only information, point in time,
2018-26 (research/data/nse_fut_pit = official F&O bhavcopies, all stock futures; spot = official cash bhavcopy close):
  CARRY     near-month futures premium over spot, annualised by days to expiry (negative = futures at a DISCOUNT = shorts
            paying to stay short / heavy short positioning), also relative to the stock's own 60-day average carry
  OI5       5-session change of total stock-futures OI (all expiries)
  ROLL      rollover in the last 3 sessions before expiry: next-month OI share of total; vs the stock's own average
  BUILD     5-day price change x OI change sign (short build-up = price down + OI up)
Outcome: next open -> close 5 and 10 sessions later (spot, splits removed), absolute and EXCESS over all F&O stocks that day.
Every signal is judged by decile / bucket in 2018-20, 2021-23 and 2024-26 separately.
python -m research.cashq.fut_basis -> results/fut_basis_summary.csv"""
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "results"


def load():
    rows = []
    for p in sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz"))):
        d = pd.read_csv(p, usecols=["date", "symbol", "kind", "expiry", "close", "oi"])
        rows.append(d[d.kind == "STK"])
    F = pd.concat(rows, ignore_index=True)
    F["date"] = pd.to_datetime(F.date); F["expiry"] = pd.to_datetime(F.expiry)
    F = F[F.expiry >= F.date].sort_values(["symbol", "date", "expiry"])
    g = F.groupby(["symbol", "date"])
    near = g.first()[["expiry", "close", "oi"]].rename(columns={"close": "fut", "oi": "oi_near", "expiry": "exp"})
    tot = g.oi.sum().rename("oi")
    nxt = F.groupby(["symbol", "date"]).nth(1).set_index(["symbol", "date"])["oi"].rename("oi_next")
    X = near.join(tot).join(nxt)
    cm = []
    for p in sorted(glob.glob(str(ROOT / "research/data/nse_cm/20*.csv.gz"))):
        if int(Path(p).name[:4]) >= 2017:
            cm.append(pd.read_csv(p, usecols=["date", "symbol", "series", "open", "close"]))
    for p in sorted(glob.glob(str(ROOT / "research/data/nse_cm/days/*.csv.gz"))):
        cm.append(pd.read_csv(p, usecols=["date", "symbol", "series", "open", "close"]))
    C = pd.concat(cm); C = C[C.series == "EQ"]; C["date"] = pd.to_datetime(C.date)
    C = C.drop_duplicates(["symbol", "date"]).set_index(["symbol", "date"])[["open", "close"]]
    X = X.join(C, how="inner").reset_index().sort_values(["symbol", "date"])
    return X


def main():
    X = load()
    g = X.groupby("symbol")
    dte = (X.exp - X.date).dt.days.clip(lower=1)
    X["carry"] = (X.fut / X.close - 1) * 365 / dte
    X["carry_rel"] = X.carry - g.carry.transform(lambda s: s.rolling(60, min_periods=30).mean().shift(1))
    X["oi5"] = g.oi.pct_change(5)
    X["r5"] = g.close.pct_change(5)
    X["build"] = np.select([(X.r5 < 0) & (X.oi5 > 0), (X.r5 > 0) & (X.oi5 > 0), (X.r5 > 0) & (X.oi5 < 0), (X.r5 < 0) & (X.oi5 < 0)],
                           ["SB short build-up", "LB long build-up", "SC short covering", "LU long unwinding"], "none")
    X["roll"] = np.where(dte <= 5, X.oi_next / X.oi, np.nan)
    X["roll_rel"] = X.roll - g.roll.transform(lambda s: s.ffill().rolling(60, min_periods=10).mean().shift(1))
    for H in (5, 10):
        fo = g.open.shift(-1); fc = g.close.shift(-H)
        r = fc / fo - 1
        X[f"f{H}"] = r.where(r.abs() < 0.4)                                 # drop split / bonus jumps
        X[f"x{H}"] = X[f"f{H}"] - X.groupby("date")[f"f{H}"].transform("mean")
    X["period"] = np.where(X.date.dt.year <= 2020, "2018-20", np.where(X.date.dt.year <= 2023, "2021-23", "2024-26"))
    X = X[X.date >= "2018-03-01"]
    B = {"carry decile": X.groupby("date").carry.transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False) + 1),
         "carry vs own avg decile": X.groupby("date").carry_rel.transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False) + 1 if s.notna().sum() > 20 else np.nan),
         "OI 5-day change decile": X.groupby("date").oi5.transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False) + 1),
         "5-day build-up": X.build,
         "rollover vs own avg (expiry week)": pd.cut(X.roll_rel, [-9, -0.10, -0.03, 0.03, 0.10, 9], labels=["much lower", "lower", "normal", "higher", "much higher"]),
         "discount + short build-up": np.where((X.carry < 0) & (X.build == "SB short build-up"), "discount + SB", "other")}
    rows = []
    for nm, b in B.items():
        for v, s in X.groupby(b, observed=True):
            row = dict(signal=nm, bucket=str(v), n=len(s))
            for H in (5, 10):
                row[f"f{H}_avg%"] = round(100 * s[f"f{H}"].mean(), 3); row[f"x{H}_avg%"] = round(100 * s[f"x{H}"].mean(), 3)
                row[f"f{H}_down%"] = round(100 * (s[f"f{H}"] < 0).mean(), 1)
            for p in ("2018-20", "2021-23", "2024-26"):
                q = s[s.period == p]; row[f"{p}_x10%"] = round(100 * q.x10.mean(), 3); row[f"{p}_down10%"] = round(100 * (q.f10 < 0).mean(), 1)
            rows.append(row)
    L = pd.DataFrame(rows); L.to_csv(OUT / "fut_basis_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print("rows", len(X), "stocks", X.symbol.nunique(), X.date.min().date(), X.date.max().date())
    print(L.to_string(index=False))


if __name__ == "__main__":
    main()

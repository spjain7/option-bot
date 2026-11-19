"""FII-POI-001 (19-Nov-2026, owner: "find setups for NSE futures"). NSE participant-wise OI 2012-26
(research/data/nse_poi via poi_fetch.py) vs NIFTY front-month futures (official F&O bhavcopy, research/data/nse_fut).
The file for day d is published that evening -> signal at d's close, trade at d+1's open (no look-ahead).
Signals (index futures, contracts):
  FII_FLIP_LONG   FII net (long - short) turns positive        FII_FLIP_SHORT  FII net turns negative
  FII_LR_UP30     FII long ratio (long / (long + short)) crosses above 30 %   FII_LR_DN       crosses below 20 %
  FII_EXT_SHORT   FII long ratio <= 15 % (extreme short)       FII_EXT_LONG    FII long ratio >= 70 %
  FII_ADD_SHORT5  FII added >= 10 % of their index-futures shorts in 5 sessions (and net negative)
  CLIENT_EXT_LONG retail (Client) long ratio in its top 10 % of the past 250 days (contrarian SELL idea)
  CLIENT_EXT_SHORT retail long ratio in its bottom 10 %
Outcome: NIFTY futures next open -> close after 5 / 10 / 20 / 30 sessions (contract rolls removed: returns chain only
within the same contract). "Hit %" = share of events where NIFTY moved the signal's way, vs the base rate of all days.
Periods 2012-16 / 2017-21 / 2022-26. Events within 5 sessions of the previous one of the same signal are merged.
python -m research.cashq.fii_poi -> results/fii_poi_summary.csv"""
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "results"
HS = (5, 10, 20, 30)


def nifty():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "research/data/nse_fut/days/*.csv"))):
        d = pd.read_csv(f)
        d = d[(d["symbol"] == "NIFTY")]
        if d.empty:
            continue
        d = d[pd.to_datetime(d["expiry"]) >= pd.to_datetime(d["date"])].sort_values("expiry")
        rows.append(d.iloc[0])
    N = pd.DataFrame(rows)[["date", "expiry", "open", "high", "low", "close"]]
    N["date"] = pd.to_datetime(N.date)
    N = N.set_index("date").sort_index()
    N["same"] = N.expiry == N.expiry.shift(1)
    r = (N.close / N.close.shift(1)).where(N.same, N.close / N.open)          # roll day: use that contract's intraday move
    N["idx"] = r.fillna(1).cumprod()                                             # roll-free index level (close)
    N["idx_open"] = N.idx * N.open / N.close
    return N


def main():
    P = pd.read_parquet(ROOT / "research/data/nse_poi/poi.parquet")
    P["ct"] = P["Client Type"].astype(str).str.strip()
    W = {}
    for ct in ("FII", "Client", "Pro", "DII"):
        x = P[P.ct == ct].set_index("date").sort_index()
        W[ct] = x
    F = W["FII"]; C = W["Client"]
    fl, fs = F["Future Index Long"], F["Future Index Short"]
    net = fl - fs; lr = fl / (fl + fs)
    clr = C["Future Index Long"] / (C["Future Index Long"] + C["Future Index Short"])
    cq = clr.rolling(250, min_periods=120).rank(pct=True)
    S = pd.DataFrame(index=F.index)
    S["FII_FLIP_LONG"] = (net > 0) & (net.shift(1) <= 0)
    S["FII_FLIP_SHORT"] = (net < 0) & (net.shift(1) >= 0)
    S["FII_LR_UP30"] = (lr > .30) & (lr.shift(1) <= .30)
    S["FII_LR_DN20"] = (lr < .20) & (lr.shift(1) >= .20)
    S["FII_EXT_SHORT"] = lr <= .15
    S["FII_EXT_LONG"] = lr >= .70
    S["FII_ADD_SHORT5"] = (fs / fs.shift(5) - 1 >= .10) & (net < 0)
    S["CLIENT_EXT_LONG"] = cq >= .90
    S["CLIENT_EXT_SHORT"] = cq <= .10
    SIDE = {"FII_FLIP_LONG": 1, "FII_FLIP_SHORT": -1, "FII_LR_UP30": 1, "FII_LR_DN20": -1, "FII_EXT_SHORT": -1, "FII_EXT_LONG": 1,
            "FII_ADD_SHORT5": -1, "CLIENT_EXT_LONG": -1, "CLIENT_EXT_SHORT": 1}
    N = nifty()
    idx = N.index.intersection(S.index)
    S = S.reindex(idx).fillna(False); N = N.reindex(idx)
    fwd = {H: N.idx.shift(-H) / N.idx_open.shift(-1) - 1 for H in HS}
    per = np.where(idx.year <= 2016, "2012-16", np.where(idx.year <= 2021, "2017-21", "2022-26"))
    rows = []
    for sname, s in S.items():
        s = s.values.copy()
        last = -99
        for i in range(len(s)):                                   # merge events within 5 sessions
            if s[i]:
                if i - last <= 5:
                    s[i] = False
                else:
                    last = i
        side = SIDE[sname]
        for H in HS:
            f = fwd[H].values
            ok = s & np.isfinite(f)
            row = dict(signal=sname, side="BUY" if side > 0 else "SELL", H=H, events=int(ok.sum()),
                       hit=round(100 * float((side * f[ok] > 0).mean()), 1) if ok.any() else None,
                       avg_pct=round(100 * float(side * f[ok].mean()), 2) if ok.any() else None,
                       base_hit=round(100 * float((side * f[np.isfinite(f)] > 0).mean()), 1))
            for p in ("2012-16", "2017-21", "2022-26"):
                m = ok & (per == p)
                row[f"{p}_n"] = int(m.sum()); row[f"{p}_hit"] = round(100 * float((side * f[m] > 0).mean()), 1) if m.any() else None
                b = np.isfinite(f) & (per == p)
                row[f"{p}_base"] = round(100 * float((side * f[b] > 0).mean()), 1)
            rows.append(row)
    L = pd.DataFrame(rows); L.to_csv(OUT / "fii_poi_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
    print("days", len(idx), idx.min().date(), idx.max().date())
    print(L.to_string(index=False))


if __name__ == "__main__":
    main()

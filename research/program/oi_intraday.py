"""OI-INTRA-001 (25-Nov-2026, owner: "can we trust OI calls mixed with other indicators – check for intraday").
Intraday OI history is not stored anywhere (Angel keeps it only for live contracts), so two tests use what exists:
A) MCX bhavcopy Jul-2022..Nov-2026, 9 commodities: yesterday's OI build-up (price change sign x total-OI change sign, all
   contracts) -> INTRADAY trade today: entry at the open, stop 0.5 daily ATR (checked first), exit at the close.
   Labels: LB long build-up (P up, OI up) -> BUY · SB short build-up (P down, OI up) -> SELL · SC short covering -> BUY ·
   LU long unwinding -> SELL. Mixed with: daily trend (EMA20/50), strong close (close in the top / bottom 30 % of the day),
   volume >= 1.5x 20-day, OI change >= 2 %, RSI(14) side. Benchmark: every day traded in the same direction (drift).
B) MCX GOLD / SILVER day-trend rule (alerts/mcx_dtc, 5-min 2023-26) split by yesterday's OI label agreeing or not.
Costs 0.03 % of price per round trip (intraday MCX fees + 1-2 ticks).   python research/program/oi_intraday.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import mcx_pos as M  # noqa: E402

COST = 0.0003
P1, P2 = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01")
D = M.load()
rows = []
for sym in M.COMS:
    S = M.series(D, sym)
    x = D[D.symbol == sym]
    oi = x.groupby("date").oi_lots.sum().reindex(S.time).values
    S["oi"] = oi
    c, o, h, l = S.close, S.open, S.high, S.low
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    trend = np.where((e20 > e50) & (c > e50), 1, np.where((e20 < e50) & (c < e50), -1, 0))
    dp = c - c.shift(1); doi = S.oi / S.oi.shift(1) - 1
    # a contract switch distorts the price change: skip switch days and the day after
    sw = S.switch | S.switch.shift(1, fill_value=False)
    pos = (c - l) / (h - l).replace(0, np.nan)
    vx = S.volume / S.volume.rolling(20).mean().shift(1)
    d_ = c.diff(); rsi = 100 - 100 / (1 + d_.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean() / (-d_.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean())
    for i in range(60, len(S) - 1):
        if sw.iat[i] or sw.iat[i + 1] or not np.isfinite(doi.iat[i]) or abs(doi.iat[i]) > 0.5:
            continue
        lab = ("LB" if doi.iat[i] > 0 else "SC") if dp.iat[i] > 0 else ("SB" if doi.iat[i] > 0 else "LU")
        j = i + 1; e = o.iat[j]; R = 0.5 * atr.iat[i]
        for side in (1, -1):
            stop = e - side * R
            hit = (l.iat[j] <= stop) if side > 0 else (h.iat[j] >= stop)
            px = stop if hit else c.iat[j]
            rows.append(dict(sym=sym, t=S.time.iat[j], side=side, lab=lab, R=side * (px - e) / R - COST * e / R,
                             trend=trend[i] * side, strong=(pos.iat[i] >= 0.7) if side > 0 else (pos.iat[i] <= 0.3),
                             vol=vx.iat[i] >= 1.5, big=abs(doi.iat[i]) >= 0.02, rsi=(rsi.iat[i] > 50) if side > 0 else (rsi.iat[i] < 50)))
T = pd.DataFrame(rows)
T["per"] = np.where(T.t < P1, "22-23", np.where(T.t < P2, "2024", "25-26"))
T["oi_ok"] = ((T.side > 0) & T.lab.isin(["LB", "SC"])) | ((T.side < 0) & T.lab.isin(["SB", "LU"]))
T["oi_strict"] = ((T.side > 0) & (T.lab == "LB")) | ((T.side < 0) & (T.lab == "SB"))
pd.set_option("display.width", 200)


def st(g):
    return pd.Series(dict(n=len(g), win=round(100 * (g.R > 0).mean()), R=round(g.R.mean(), 3),
                          **{p: round(g[g.per == p].R.mean(), 3) for p in ("22-23", "2024", "25-26")}))


print("A) next-day intraday, MCX 9 commodities")
tests = {"every day (drift benchmark)": T.R.notna(), "OI build-up only (LB->BUY, SB->SELL)": T.oi_strict,
         "OI any agreeing label (LB/SC BUY, SB/LU SELL)": T.oi_ok, "OI build-up + daily trend": T.oi_strict & (T.trend > 0),
         "OI build-up + strong close": T.oi_strict & T.strong, "OI build-up + big OI change (>=2%)": T.oi_strict & T.big,
         "OI build-up + volume 1.5x": T.oi_strict & T.vol, "OI build-up + RSI side": T.oi_strict & T.rsi,
         "OI build-up + trend + strong close": T.oi_strict & (T.trend > 0) & T.strong,
         "OI build-up + trend + strong close + big OI": T.oi_strict & (T.trend > 0) & T.strong & T.big,
         "trend + strong close, NO OI": (T.trend > 0) & T.strong, "trend + strong close, OI AGAINST": (T.trend > 0) & T.strong & ~T.oi_ok}
out = pd.DataFrame({k: st(T[m]) for k, m in tests.items()}).T
print(out.to_string())
print(T[T.oi_strict & (T.trend > 0) & T.strong].groupby("sym").R.agg(["size", "mean"]).round(2).T.to_string())
T.to_csv(ROOT / "research/program/results/oi_intraday_A.csv", index=False)

# B) (run 25-Nov, see PR "MCX day-trend: BUY only after an OI rise"): alerts/mcx_dtc trades (research/program/dtc_daily_filter.py
# output) split by yesterday's total-OI change from the bhavcopy. With the daily-trend filter: BUY after OI fell 146 trades
# -0.07R (GOLD -0.03, SILVER -0.11; 2024 -0.48, 2026 -0.14), BUY after OI rose 163 trades +0.33R (GOLD +0.23, SILVER +0.48,
# every year positive); SELL positive either way. Rule with BUY-after-OI-rise only: 243 trades, 58 % won, +0.39R/trade.

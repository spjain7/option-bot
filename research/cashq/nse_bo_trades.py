"""Trade list for the NSE cash breakout setups that passed research/cashq/nse_bo_tf.py (owner 18-Nov-2026: "artifact with high,
low, best profit and worst loss after the call, on 100 shares"). Same rules: signal at the candle close, entry next candle's
open, SL k ATR (of that timeframe) below the entry, target 3R, max 12 monthly / 26 weekly / 60 daily candles, delivery costs
0.393 %. Prices are back-adjusted for splits / bonuses (NSE PREVCLOSE), so old prices can differ from today's chart.
  M_ATH   monthly close at an all-time closing high · market (top-100 EW index) above its 200-day average · SL 2 ATR
  W_ATH   weekly close at an all-time closing high · volume >= 1.5x the 20-week average · SL 3 ATR
  W_MARU  weekly strong candle (body >= 70 % of range, range >= 1.5 ATR) closing above the 20-week high · uptrend · SL 3 ATR
  D_HI52  daily 52-week closing high · volume >= 1.5x · uptrend · SL 3 ATR
  W_MY260 weekly close above the 5-year high, that high made >= 1 year earlier · volume >= 1.5x · SL 3 ATR (18-Nov)
  M_MY60  monthly close above the 5-year high, made >= 12 months earlier · market above its 200-day average · SL 2 ATR
python -m research.cashq.nse_bo_trades -> results/nse_bo_trades.json ({rows, meta})"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D, ind as I  # noqa: E402
from research.cashq import nse_bo_tf as T  # noqa: E402

QTY = 100
SETUPS = {"M_ATH": ("1M", "Monthly all-time-high breakout (market up)", 2.0),
          "W_ATH": ("1w", "Weekly all-time-high breakout on volume", 3.0),
          "W_MARU": ("1w", "Weekly strong-candle 20-week breakout (uptrend)", 3.0),
          "D_HI52": ("1d", "Daily 52-week-high breakout on volume (uptrend)", 3.0),
          "W_MY260": ("1w", "Weekly 5-year (multi-year) breakout on volume", 3.0),
          "M_MY60": ("1M", "Monthly 5-year (multi-year) breakout (market up)", 2.0)}


def signals(P, tf, sid, mkt):
    o, h, l, c, v = (P[x].astype("float64") for x in ("open", "high", "low", "close", "volume"))
    atr = I.atr(h, l, c, 14); em = c.ewm(span=50, adjust=False, min_periods=50).mean(); vx = v / v.rolling(20).mean().shift(1)
    trend = (c > em) & (em > em.shift(5))
    mk = mkt.reindex(c.index, method="ffill").fillna(False).values
    MK = pd.DataFrame(np.repeat(mk[:, None], c.shape[1], 1), index=c.index, columns=c.columns)
    if sid in ("M_ATH", "W_ATH"):
        s = (c >= c.cummax()) & (c.notna().cumsum() >= (24 if tf == "1M" else 104))
    elif sid in ("W_MY260", "M_MY60"):                      # 18-Nov: multi-year breakout (research/cashq/multiyear_bo.py)
        from research.cashq.multiyear_bo import age_of_max
        N = 260 if sid == "W_MY260" else 60
        s = (c > h.shift(1).rolling(N, min_periods=N).max()) & (age_of_max(h, N) >= (52 if sid == "W_MY260" else 12))
    elif sid == "W_MARU":
        rg = h - l; s = (c > o) & ((c - o).abs() >= 0.7 * rg) & (rg >= 1.5 * atr) & (c > h.shift(1).rolling(20).max())
    else:
        s = c >= c.rolling(252, min_periods=240).max()
    s = s.fillna(False); s = s & ~s.shift(1).rolling(3, min_periods=1).max().fillna(0).astype(bool)
    s = s & (MK if sid in ("M_ATH", "M_MY60") else True) & (vx >= 1.5 if sid in ("W_ATH", "D_HI52", "W_MY260") else True) & (trend if sid in ("W_MARU", "D_HI52") else True)
    return s & P["elig"].reindex_like(c).fillna(False).astype(bool), o, h, l, c, atr


def main():
    W = D.daily_panel(); mk = W["market"]["close"]; mkt = mk > mk.rolling(200).mean(); sym = W["symbol"]
    panels = {"1d": W, "1w": D.weekly(W), "1M": T.monthly(W)}
    rows = []; tid = 0
    for sid, (tf, label, k) in SETUPS.items():
        P = panels[tf]
        s, o, h, l, c, atr = signals(P, tf, sid, mkt)
        days = c.index; cols = list(c.columns); MAXH = T.MAXH[tf]
        S, O, H, L, C, A = (np.asarray(x.values, float) if x is not s else np.asarray(x.values, bool) for x in (s, o, h, l, c, atr))
        last_day = days[-1]
        for j in np.where(S.any(0))[0]:
            t = 0; n = len(days)
            while t < n - 1:
                if not S[t, j] or not A[t, j] > 0:
                    t += 1; continue
                e = t + 1
                while e < n and np.isnan(O[e, j]):
                    e += 1
                if e >= n:
                    break
                px = O[e, j]; risk = k * A[t, j]
                if not (0.25 * A[t, j] <= risk <= 6 * A[t, j]):
                    t += 1; continue
                st, tg = px - risk, px + 3 * risk
                hi, lo = px, px; out = None; why = None; x = e
                while x < n:
                    if np.isnan(C[x, j]):
                        x += 1; continue
                    hi = max(hi, H[x, j]); lo = min(lo, L[x, j])
                    if L[x, j] <= st:
                        out = min(O[x, j], st) if x > e else st; why = "stop-loss"; lo = min(lo, out); break
                    if H[x, j] >= tg:
                        out = max(O[x, j], tg) if x > e else tg; why = "target 3R"; break
                    if x - e + 1 >= MAXH:
                        out = C[x, j]; why = "time exit"; break
                    x += 1
                if out is None:
                    x = n - 1
                    while np.isnan(C[x, j]):
                        x -= 1
                    out = C[x, j]; why = "OPEN (last close)"
                if why == "target 3R":
                    hi = max(hi, out)
                cost = 0.00393 * px * QTY
                pnl = (out - px) * QTY - cost
                tid += 1
                rows.append(dict(id=f"T{tid}", setup=label, setup_id=sid, timeframe={"1M": "Monthly", "1w": "Weekly", "1d": "Daily"}[tf],
                                 symbol=str(sym[cols[j]]), signal_date=str(days[t].date()), entry_date=str(days[e].date()),
                                 exit_date=str(days[x].date()), entry=round(px, 2), sl=round(st, 2), target=round(tg, 2), exit=round(out, 2),
                                 high_after=round(hi, 2), low_after=round(lo, 2), best_profit_100=int(round((hi - px) * QTY)),
                                 worst_loss_100=int(round((lo - px) * QTY)), pnl_100=int(round(pnl)), pnl_pct=round(100 * (pnl / (px * QTY)), 2),
                                 R=round(((out - px) * QTY - cost) / (risk * QTY), 2), result=why, candles=int(x - e + 1),
                                 year=int(days[e].year), period="2005-14" if days[e].year <= 2014 else "2015-19" if days[e].year <= 2019 else "2020-26",
                                 status="open" if why.startswith("OPEN") else "closed"))
                t = x + 1
        print(sid, sum(r["setup_id"] == sid for r in rows), flush=True)
    code = Path(__file__).read_text()
    meta = [{"label": "nse_bo_trades.py", "value": code, "type": "code", "lang": "python"},
            {"label": "Input", "value": f"Official NSE cash bhavcopies 2005-01 to {last_day.date()} (back-adjusted, delisted stocks included), point-in-time liquid universe (₹25 cr median turnover, ≥ ₹50, ≥ 250 sessions)"},
            {"label": "Rules", "value": "Signal at the candle close, entry next candle's open, SL k ATR, target 3R, max 12 monthly / 26 weekly / 60 daily candles; P&L for 100 shares after 0.393 % delivery costs; prices back-adjusted"},
            {"label": "Branch", "value": "spjain7/option-bot exp/cash-equity-engine (research only, not live)"}]
    (T.OUT / "nse_bo_trades.json").write_text(json.dumps(dict(rows=rows, meta=meta), allow_nan=False))
    R = pd.DataFrame(rows)
    print(R.groupby("setup_id").agg(n=("id", "size"), win=("pnl_100", lambda x: round(100 * (x > 0).mean(), 1)), avg=("pnl_pct", "mean"),
                                    best=("best_profit_100", "max"), worst=("worst_loss_100", "min"), open=("status", lambda x: (x == "open").sum())))


if __name__ == "__main__":
    main()

"""BIGMOVE-LOG (29-Oct-2026): each day's top-5 predicted big movers, last 2 months, with real prices (NSE bhavcopy) for the
owner's review page. Model trained only on data BEFORE the review period (no look-ahead). Entry = ATM CE / PE close on the
pick day (the evening scan), exit = next day's close; 'best' = next day's option high (not tradable, shown for reference).
P&L per lot after ₹ costs (brokerage ₹40 + STT/charges ≈ 0.15 % of the sell value + 1 % slippage each side)."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from sklearn.ensemble import HistGradientBoostingClassifier
from research.program.bigmove import FEATS
from research.search import stock_search as SR

START = pd.Timestamp("2026-08-26")
X = pd.read_csv(ROOT / "research/program/results/bigmove_features.csv.gz", parse_dates=["date", "fexp"])
lots = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")["lot"].to_dict()
tr, te = X[X.date < START - pd.Timedelta(days=3)], X[X.date >= START].copy()
m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0).fit(tr[FEATS], tr["big"])
te["p"] = m.predict_proba(te[FEATS])[:, 1]
days = sorted(X.date.unique()); nxt = {d: days[i + 1] for i, d in enumerate(days[:-1])}
cache = {}


def day(d):
    if d not in cache:
        cache[d] = pd.read_csv(ROOT / f"research/data/nse_opt/days/{pd.Timestamp(d):%Y%m%d}.csv", parse_dates=["expiry"])
    return cache[d]


def pnl(e, x, lot):
    if e is None or x is None:
        return None
    buy, sell = e * 1.01, x * 0.99
    return round((sell - buy) * lot - 40 - 0.0015 * sell * lot)


rows = []
picks = te.sort_values("p", ascending=False).groupby("date").head(5).sort_values(["date", "p"], ascending=[True, False])
for r in picks.itertuples():
    if r.date not in nxt:
        continue
    a, b = day(r.date), day(nxt[r.date])
    o = a[(a.symbol == r.symbol) & (a.kind != "FUT") & (a.expiry >= r.date + pd.Timedelta(days=5))]
    if o.empty:
        continue
    e = o.expiry.min(); o = o[o.expiry == e]
    K = float(o.iloc[(o.strike - r.close).abs().argsort().iloc[0]].strike)
    f1 = b[(b.symbol == r.symbol) & (b.kind == "FUT")].sort_values("expiry")
    f1 = f1[f1.expiry == r.fexp] if (f1.expiry == r.fexp).any() else f1.head(1)
    if f1.empty:
        continue
    f1 = f1.iloc[0]
    lot = int(lots.get(r.symbol, 0)) or None
    leg = {}
    for typ in ("CE", "PE"):
        q0 = o[(o.kind == typ) & (o.strike == K)]
        q1 = b[(b.symbol == r.symbol) & (b.expiry == e) & (b.strike == K) & (b.kind == typ)]
        e0 = float(q0.close.iloc[0]) if len(q0) and q0.close.iloc[0] > 0 else None
        x1 = float(q1.close.iloc[0]) if len(q1) and q1.close.iloc[0] > 0 else None
        hi = float(q1.high.iloc[0]) if len(q1) and q1.high.iloc[0] > 0 else None
        leg[typ] = dict(entry=e0, exit=x1, high=hi, pnl=pnl(e0, x1, lot) if lot else None, best=pnl(e0, hi, lot) if lot else None)
    why = []
    if r.iv_hv == r.iv_hv: why.append(f"IV {r.iv * 100:.0f}% = {r.iv_hv:.1f}× actual move")
    if r.volx == r.volx and r.volx >= 1.5: why.append(f"volume {r.volx:.1f}×")
    if r.oi1 == r.oi1 and abs(r.oi1) >= 0.03: why.append(f"OI {r.oi1 * 100:+.0f}%")
    if r.iv5 == r.iv5 and r.iv5 >= 0.15: why.append(f"IV +{r.iv5 * 100:.0f}% in 5 days")
    st = [leg["CE"]["pnl"], leg["PE"]["pnl"]]
    rows.append(dict(date=f"{r.date:%Y-%m-%d}", next=f"{nxt[r.date]:%Y-%m-%d}", stock=r.symbol, lot=lot, prob=round(r.p * 100),
                     why=" · ".join(why), close=round(r.close, 2), move_today=round(r.ret1 * 100, 2) if r.ret1 == r.ret1 else None,
                     move_5d=round(r.ret5 * 100, 2) if r.ret5 == r.ret5 else None, normal=round(r.absmv20 * 100, 2),
                     n_open=round(float(f1.open), 2), n_high=round(float(f1.high), 2), n_low=round(float(f1.low), 2), n_close=round(float(f1.close), 2),
                     move_next=round(float(f1.close) / r.close * 100 - 100, 2), up_max=round(float(f1.high) / r.close * 100 - 100, 2),
                     dn_max=round(float(f1.low) / r.close * 100 - 100, 2), big=bool(r.big == 1), strike=K, expiry=f"{e:%d-%b}",
                     ce=leg["CE"], pe=leg["PE"], straddle=(st[0] + st[1]) if None not in st else None))
out = ROOT / "research/program/results/bigmove_log.json"
out.write_text(json.dumps(rows, default=lambda v: None if isinstance(v, float) and v != v else v))
R = pd.DataFrame(rows)
print(len(R), "picks", R.date.min(), "→", R.date.max(), "| big moves", R.big.mean().round(3),
      "| straddle ₹ total", R.straddle.sum(), "avg", round(R.straddle.mean()), "win%", round((R.straddle > 0).mean() * 100, 1))
print("CE ₹ total", sum(x["pnl"] or 0 for x in R.ce), "PE ₹ total", sum(x["pnl"] or 0 for x in R.pe))

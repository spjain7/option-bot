"""REAL MCX sanity check with Angel One contract candles (descriptive only - too short to grade).

1. Proxy quality: daily returns of each listed MCX contract vs the Yahoo proxy (correlation, beta), on common dates.
2. Strategy A on REAL MCX hourly candles of the most-traded listed contract, for whatever history Angel serves.
Run after fetching branch research-data:  python -m research.angel_check
"""
from pathlib import Path
import numpy as np
import pandas as pd
from research import continuous as CO, engine_hourly as EH, metrics as MT
from research.instruments import REGISTRY

ROOT = Path(__file__).resolve().parent
ANG = ROOT / "data" / "angel"
OUT = ROOT / "output"


def main():
    man = pd.read_csv(ANG / "manifest.csv")
    rows, arows = [], []
    for name, g in man[man.exch == "MCX"].groupby("name"):
        prox = CO.load_proxy(name, "1d")
        for sym in g.symbol.unique():
            f = ANG / "MCX" / f"{sym}_ONE_DAY.csv"
            if not f.exists():
                continue
            d = pd.read_csv(f, parse_dates=["time"]); d["date"] = d["time"].dt.normalize()
            d = d[d.volume > 0]
            if len(d) < 20:
                rows.append(dict(instrument=name, contract=sym, traded_days=len(d), note="too few traded days")); continue
            rec = dict(instrument=name, contract=sym, traded_days=len(d), first=d.date.min().date(), last=d.date.max().date(),
                       avg_volume=round(d.volume.mean()))
            if prox is not None:
                p = prox.assign(date=prox.time.dt.normalize()).set_index("date")["close"].pct_change()
                m = d.set_index("date")["close"].pct_change().to_frame("mcx").join(p.rename("proxy"), how="inner").dropna()
                if len(m) > 15:
                    rec.update(common_days=len(m), corr=round(m.corr().iloc[0, 1], 3),
                               beta=round(np.polyfit(m.proxy, m.mcx, 1)[0], 3))
            rows.append(rec)
        # strategy A on the real hourly candles of the contract with the most hourly bars
        hs = g[(g.interval == "ONE_HOUR") & (g.bars > 0)].sort_values("bars", ascending=False)
        if not hs.empty:
            sym = hs.iloc[0].symbol
            h = pd.read_csv(ANG / "MCX" / f"{sym}_ONE_HOUR.csv", parse_dates=["time"])
            t = EH.run(name, h) if len(h) > EH.BASE["trend"] + 10 else pd.DataFrame()
            st = MT.stats(t) if not t.empty else dict(trades=0)
            arows.append(dict(instrument=name, contract=sym, hourly_bars=len(h), first=h.time.min(), last=h.time.max(),
                              **{k: st.get(k) for k in ("trades", "expectancy_R", "gross_expectancy_R", "pf", "total_R", "win_pct")}))
    OUT.mkdir(exist_ok=True)
    a, b = pd.DataFrame(rows), pd.DataFrame(arows)
    a.to_csv(OUT / "mcx_real_vs_proxy.csv", index=False); b.to_csv(OUT / "mcx_real_strategyA.csv", index=False)
    print(a.to_string()); print(b.to_string())


if __name__ == "__main__":
    main()

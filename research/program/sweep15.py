"""SWEEP-15 (29-Oct-2026) – owner's request: intraday liquidity-sweep reversals on 15-minute candles with volume and OI layers.
Data: 15-minute futures with OI, Aug–Oct 2026 only (33 stocks, NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY, 4 MCX) – EXPLORATORY,
split into first / second half. Levels as sweep.py: PD previous-day high/low, SW 20-candle, EQ equal highs/lows.
Entry: break of the sweep candle's low (SELL) / high (BUY) within 3 candles, same day; stop 0.05 ATR beyond the sweep
extreme; target 1R; exit at the day's last candle. No entries in the first 15 minutes or after 14:30 (MCX after 22:00).
Layers (known at the sweep candle's close):
  V   sweep-candle volume ≥ 1.5× its 20-candle average
  OU  OI rose on the sweep candle (fresh positions opened beyond the level – then trapped)
  OD  OI fell on the sweep candle (positions closed into the sweep)
  OL  last-hour OI label confirms the trade: SELL after long buildup (trapped longs), BUY after short buildup
Trades whose round-trip cost exceeds 1/3 of the risk are skipped (tiny 15-minute candles).
Costs: this bot's contract costs (stocks 0.05 % STT era included via stkfut_cmp.cost_units; index/MCX research costs)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import reversal as RV, stkfut_cmp as SC, sweep as SWP  # noqa: E402
from research.search import stock_search as SR  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"


def load(p, nm, kind):
    seg, f, cost, _ = RV.m15(p, nm, kind)
    raw = pd.read_csv(p, parse_dates=["time"]).sort_values("time").drop_duplicates("time").reset_index(drop=True)
    f = f.reset_index(drop=True)
    f["oi"] = raw["oi"].values if "oi" in raw else np.nan
    f["day"] = f["time"].dt.normalize(); f["hhmm"] = f["time"].dt.strftime("%H:%M")
    return seg.split()[0], f, cost


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")
    jobs = [(p, p.stem[4:], "index" if p.stem[4:] in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY") else "stock")
            for p in sorted((ROOT / "research/data/obuy").glob("fut_*.csv"))]
    jobs += [(p, p.stem[4:], "mcx") for p in sorted((ROOT / "research/data/obuy_mcx").glob("fut_*.csv"))]
    rows = []
    for p, nm, kind in jobs:
        try:
            mk, f, cost = load(p, nm, kind)
        except Exception as e:
            print("skip", nm, e); continue
        if len(f) < 200:
            continue
        f["atr"] = I.atr(f, 14)
        lot = int(man.loc[nm, "lot"]) if nm in man.index else 1
        o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
        v = f["volume"].astype(float); vx = (v / v.rolling(20).mean().shift(1)).values
        doi = f["oi"].astype(float).diff().values
        lab = f["oi_lab"].values
        late = "22:00" if mk == "MCX" else "14:30"
        first = f.groupby("day").cumcount().values
        for lvname, (hi_lv, lo_lv) in SWP.levels(f, "15m").items():
            for side in (1, -1):
                lv = lo_lv if side > 0 else hi_lv
                sweep = np.nan_to_num((l < lv) & (c > lv) if side > 0 else (h > lv) & (c < lv), nan=0).astype(bool)
                busy = -1
                for i in np.flatnonzero(sweep):
                    if i < 60 or i <= busy or first[i] == 0 or f["hhmm"].iat[i] > late or not f["atr"].iat[i] > 0:
                        continue
                    a = f["atr"].iat[i]
                    stop = l[i] - 0.05 * a if side > 0 else h[i] + 0.05 * a
                    trig = h[i] if side > 0 else l[i]
                    t = SC.simulate(f, i, side, stop, "stop", trig, True, 1, lot)
                    if t is None:
                        continue
                    cr = cost[i] / t["R"] if mk != "STOCKS" else t["cost_R"]
                    if cr > 1 / 3:                                  # risk too small for the costs – no trader takes it
                        continue
                    net = t["gross_R"] - cr
                    busy = t["j"]
                    rows.append(dict(market=mk, name=nm, level=lvname, side="BUY" if side > 0 else "SELL", time=f["time"].iat[i],
                                     V=bool(vx[i] >= 1.5), OU=bool(doi[i] > 0), OD=bool(doi[i] < 0),
                                     OL=bool(lab[i] == ("SB" if side > 0 else "LB")), gross_R=t["gross_R"], net_R=net,
                                     why=t["why"]))
    T = pd.DataFrame(rows)
    T.to_csv(OUT / "sweep15_trades.csv.gz", index=False)
    mid = T["time"].quantile(0.5)
    out = []
    for (mk, lv, sd), g in T.groupby(["market", "level", "side"]):
        for cb in [(), ("V",), ("OU",), ("OD",), ("OL",), ("V", "OU"), ("V", "OD"), ("V", "OL")]:
            x = g
            for k in cb:
                x = x[x[k]]
            if len(x) < 15:
                continue
            out.append(dict(market=mk, level=lv, side=sd, layer="+".join(cb) or "none", n=len(x), win=round((x.net_R > 0).mean() * 100, 1),
                            gross=round(x.gross_R.mean(), 3), net=round(x.net_R.mean(), 3),
                            h1=round(x[x.time < mid].net_R.mean(), 3), h2=round(x[x.time >= mid].net_R.mean(), 3)))
    R = pd.DataFrame(out)
    R.to_csv(OUT / "sweep15_variants.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 300)
    print(T["time"].min(), "→", T["time"].max(), len(T), "trades")
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()

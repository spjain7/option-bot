"""LIQTL-002 (3-Nov-2026, owner: "tested for commodity? I traded silver and got 4000 points today").
Same port as liqtl.py on MCX futures.
 A. 4 years (Jul-2022 → Oct-2026), 7 commodities, 1-hour candles (and 2h built from them) – the only MCX intraday history we have.
    Intraday version: flat at 23:20; also a swing version (held up to 40 bars, across days).
 B. SILVER on 3/5/10/15/30-min from the live 1-minute stream – only 30-Oct, 2-Nov evening, 3-Nov 16:17-19:46 exist (tiny sample).
Stop 1 ATR14, targets 1R/2R/3R, entry next bar open, costs 2x the MCX model.  python research/program/liqtl_mcx.py"""
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, liqtl as LT  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from crude import indicators as I  # noqa: E402

NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]


def trades(f, buy, sell, tgt, cost, swing, eod=2320, maxh=40):
    o, h, l, c = (f[x].values for x in ("open", "high", "low", "close"))
    tm = f["time"]; day = tm.dt.normalize().values; hm = (tm.dt.hour * 100 + tm.dt.minute).values
    sw = f["switch"].values if "switch" in f else np.zeros(len(c), bool)
    atr = I.atr(f, 14).values
    out, busy = [], -1
    for i in np.flatnonzero(buy | sell):
        if i <= busy or i + 1 >= len(c) or not atr[i] > 0 or sw[i + 1]:
            continue
        if not swing and (day[i + 1] != day[i] or hm[i] >= eod - 100):
            continue
        s = 1 if buy[i] else -1
        e0 = o[i + 1]; R = atr[i]; st, tp = e0 - s * R, e0 + s * tgt * R
        px = None; j = i + 1
        while j < len(c):
            if j > i + 1 and sw[j]:
                px, j = c[j - 1], j - 1; break
            if not swing and (day[j] != day[i] or hm[j] >= eod):
                px = o[j]; break
            if j > i + 1 and s * (o[j] - st) <= 0:
                px = o[j]; break
            if j > i + 1 and s * (o[j] - tp) >= 0:
                px = o[j]; break
            if (l[j] <= st) if s > 0 else (h[j] >= st):
                px = st; break
            if (h[j] >= tp) if s > 0 else (l[j] <= tp):
                px = tp; break
            if swing and j - i >= maxh:
                px = c[j]; break
            j += 1
        if px is None:
            px, j = c[-1], len(c) - 1
        g = s * (px - e0); k = 2 * cost[min(i, len(cost) - 1)]
        out.append(dict(side="BUY" if s > 0 else "SELL", time=tm.iat[i], entry=e0, pts=g - k, gross_r=g / R, r2=(g - k) / R))
        busy = j
    return out


def part_a():
    rows = []
    for nm in NAMES:
        fr = EX.frames(("mi", nm, "MCX"))
        f1, c1 = [(f, c) for s, f, o, c in fr if s == "MCX 1h"][0]
        f1 = f1.reset_index(drop=True).copy(); f1["volume"] = f1["volume"].clip(lower=0)
        for tf, f in (("1h", f1),):
            b, s = LT.signals(f)
            for swing in (False, True):
                for tg in (1.0, 2.0, 3.0):
                    for x in trades(f, b, s, tg, c1, swing):
                        x.update(name=nm, tf=tf, mode="swing" if swing else "intraday", target=f"{tg:g}R"); rows.append(x)
    T = pd.DataFrame(rows); T["time"] = pd.to_datetime(T["time"])
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    K = ["mode", "target", "side"]
    S = T.groupby(K).agg(n=("r2", "size"), win=("r2", lambda s: (s > 0).mean() * 100), gross_R=("gross_r", "mean"), net_R=("r2", "mean")) \
        .join(T.pivot_table(index=K, columns="split", values="r2", aggfunc="mean")[["train", "valid", "test"]])
    print("A. MCX 7 commodities, 1-hour, Jul-2022 → Oct-2026 (stop 1 ATR)"); print(S.round(3).to_string())
    sv = T[(T["name"] == "SILVER") & (T.target == "2R")]
    print("\nSILVER only, 2R:"); print(sv.groupby(["mode", "side"]).agg(n=("r2", "size"), win=("r2", lambda s: (s > 0).mean() * 100),
                                                                     net_R=("r2", "mean"), avg_pts=("pts", "mean")).round(2).to_string())
    print("\nper commodity, intraday 2R net R:"); print(T[(T["mode"] == "intraday") & (T.target == "2R")].pivot_table(index="name", columns="side", values="r2", aggfunc="mean").round(3).to_string())
    S.reset_index().to_csv(LT.OUT / "liqtl_mcx_summary.csv", index=False)


def part_b():
    D = "/tmp/claude-0/-home-claude/9dfb3327-26db-5f33-89ad-b39b1ae569a9/scratchpad/ws"
    x = pd.concat([pd.read_csv(p, parse_dates=["time"]) for p in glob.glob(D + "/ws_*.csv.gz")])
    s = x[(x.name == "SILVER") & x.symbol.str.endswith("FUT")].sort_values("time").drop_duplicates("time")
    s = s[(s.time.dt.hour * 100 + s.time.dt.minute >= 900) & (s.time.dt.hour * 100 + s.time.dt.minute < 2355)]
    print("\nB. SILVER from the live 1-minute stream (30-Oct, 2-Nov eve, 3-Nov 16:17-19:46) – each signal, 2R target, stop 1 ATR:")
    for m in (3, 5, 10, 15, 30):
        day = s.time.dt.normalize()
        k = ((s.time - day).dt.total_seconds() // 60 - 540) // m
        f = s.groupby([day, k]).agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                    close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)
        b, sl = LT.signals(f)
        tr = trades(f, b, sl, 2.0, np.full(len(f), 30.0), False)
        pts = sum(t["pts"] for t in tr)
        print(f"  {m:>2} min: {len(f)} candles, {len(tr)} trades, wins {sum(t['pts'] > 0 for t in tr)}, net {pts:+,.0f} points"
              + ("  · " + ", ".join(f"{pd.Timestamp(t['time']):%d-%b %H:%M} {t['side']} {t['pts']:+,.0f}" for t in tr[-8:]) if tr else ""))


if __name__ == "__main__":
    part_a(); part_b()

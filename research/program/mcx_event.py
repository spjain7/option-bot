"""MCXI-002 – scheduled US data releases (materially different from MCXI-001: larger moves, so costs matter less).

Hypothesis: the EIA weekly petroleum report (Wednesday 10:30 ET) moves CRUDEOIL and the EIA natural-gas storage report
(Thursday 10:30 ET) moves NATURALGAS far more than an ordinary hour; a break of the 60-minute pre-release range in the
first 60 minutes after the release continues. Control: the same clock times on the other weekdays.
Release time in IST: 21:00 when the US is on standard time, 20:00 during US daylight saving (2nd Sun Mar - 1st Sun Nov).
US holidays that shift a release by a day are not modelled (they add noise, not bias).
Rules: 5-min candles; pre-range = 60 min before the release; entry = stop at the range high (BUY) / low (SELL), active
for 60 min after the release, first trigger only; stop = other side of the range (0.3-3 ATR(14, 5m)) or 1.5 ATR;
exit 2R / 3R / square-off 23:00; 2 x MCX round-trip costs. Periods: HIST 2023-…-2025-11-05, DEV 2025-11-06 … 2026-06-30,
VALID 2026-07-01 … 2026-11-03.
python research/program/mcx_event.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import liqtl_mcx5 as LM  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
EVENTS = {"CRUDEOIL": 2, "NATURALGAS": 3}            # weekday of the EIA release (Mon=0)


def us_dst(d):
    y = d.year
    mar = pd.Timestamp(y, 3, 1); start = mar + pd.Timedelta(days=(6 - mar.weekday()) % 7 + 7)
    nov = pd.Timestamp(y, 11, 1); end = nov + pd.Timedelta(days=(6 - nov.weekday()) % 7)
    return start <= d < end


def run(name, wd_event):
    f = LM.load(name, "FIVE_MINUTE")
    f = f[f.time >= "2023-01-01"].reset_index(drop=True)
    o, h, l, c = (f[x].values for x in ("open", "high", "low", "close"))
    a = I.atr(f, 14).values
    t = f.time; day = t.dt.normalize(); mins = (t.dt.hour * 60 + t.dt.minute).values
    sw = f.switch.fillna(False).values
    rows = []
    for d, idx in pd.Series(np.arange(len(f))).groupby(day.values):
        idx = idx.values
        d = pd.Timestamp(d)
        if d.weekday() > 4 or sw[idx[0]]:
            continue
        rel = 20 * 60 if us_dst(d) else 21 * 60
        mm = mins[idx]
        pre = idx[(mm >= rel - 60) & (mm < rel)]; post = idx[(mm >= rel) & (mm < rel + 60)]; ok = idx[mm <= 23 * 60]
        if len(pre) < 10 or len(post) < 6 or not len(ok):
            continue
        hi, lo = h[pre].max(), l[pre].min(); A = a[pre[-1]]
        if not A > 0:
            continue
        eod = ok[-1]
        move = (h[post].max() - l[post].min()) / A                   # size of the post-release hour in ATRs
        for side in (1, -1):
            L, V = (hi, lo) if side > 0 else (lo, hi)
            j = next((k for k in post if (side > 0 and h[k] > L) or (side < 0 and l[k] < L)), None)
            if j is None:
                continue
            if any((side > 0 and l[k] < V) or (side < 0 and h[k] > V) for k in post if k < j):
                continue
            e = max(L, o[j]) if side > 0 else min(L, o[j])
            if side * (e - L) > 0.5 * A:
                continue
            cost = 2 * INS.cost_points(name, e, 1.0)
            for sp in ("STR", "ATR"):
                st = V - side * 0.1 * A if sp == "STR" else e - side * 1.5 * A
                R = side * (e - st)
                if not (0.3 * A < R < 3 * A):
                    continue
                for ex in (2.0, 3.0, 0.0):
                    tg = e + side * ex * R if ex else None; px = c[eod]
                    for k in range(j, eod + 1):
                        if (side > 0 and l[k] <= st) or (side < 0 and h[k] >= st):
                            px = st; break
                        if tg is not None and k > j and ((side > 0 and h[k] >= tg) or (side < 0 and l[k] <= tg)):
                            px = tg; break
                    g = side * (px - e) / R
                    rows.append(dict(name=name, day=d, event=d.weekday() == wd_event, side="BUY" if side > 0 else "SELL", stop=sp,
                                     exit="EOD" if not ex else f"{ex:g}R", gross=g, R=g - cost / R, cost=cost / R, move=move))
    return pd.DataFrame(rows)


def main():
    T = pd.concat([run(n, wd) for n, wd in EVENTS.items()])
    T["per"] = np.where(T.day < "2025-11-06", "hist", np.where(T.day < "2026-07-01", "dev", "valid"))
    T.to_csv(OUT / "mcxev_trades.csv.gz", index=False)
    pd.set_option("display.width", 220)
    mv = T.drop_duplicates(["name", "day"]).groupby(["name", "event"]).move.median().round(2)
    print("median size of the post-release hour (ATR units): event days vs control days\n", mv.unstack())
    g = T.groupby(["name", "event", "side", "stop", "exit", "per"]).agg(n=("R", "size"), win=("R", lambda x: 100 * (x > 0).mean()),
                                                                     R=("R", "mean"), gross=("gross", "mean"), cost=("cost", "mean"))
    G = g.unstack("per")
    G.columns = [f"{a}_{b}" for a, b in G.columns]
    G = G.reset_index()
    G.to_csv(OUT / "mcxev_summary.csv", index=False)
    cols = ["name", "event", "side", "stop", "exit", "n_hist", "R_hist", "n_dev", "R_dev", "n_valid", "R_valid", "gross_dev", "cost_dev"]
    print(G[G.event][cols].round(3).sort_values("R_dev", ascending=False).to_string(index=False))
    print("\ncontrol (non-release days), average R by period:", G[~G.event][["R_hist", "R_dev", "R_valid"]].mean().round(3).to_dict())


if __name__ == "__main__":
    main()

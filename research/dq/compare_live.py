"""STOCK-DQ-001: live Stock OI rules before vs after the data-quality fixes, replayed day by day on the stored history.
Each day uses only the 400 calendar days the live scan fetches (and the 60-day OI window), exactly like alerts/stocks.scan.
python research/dq/compare_live.py  (needs research/data/angel/NFO_STK, which is not in git)"""
import sys
from pathlib import Path
from multiprocessing import Pool
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import stocks as STK, dataquality as DQ  # noqa: E402

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "research/data/angel/NFO_STK"
START, END = pd.Timestamp("2024-01-01"), pd.Timestamp("2026-10-22")


def one(name):
    f1, fo = DATA / f"{name}_ONE_HOUR.csv", DATA / f"{name}_OI_ONE_DAY.csv"
    if not (f1.exists() and fo.exists()):
        return []
    h = pd.read_csv(f1, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
    h = h.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    oi = pd.read_csv(fo)
    oi["time"] = pd.to_datetime(oi["time"].astype(str).str[:10])
    days = sorted(set(h["time"].dt.normalize()))
    out = []
    for day in days:
        if not (START <= day <= END):
            continue
        hw = h[(h["time"] >= day - pd.Timedelta(days=400)) & (h["time"] < day + pd.Timedelta(days=1))]
        ow = oi[(oi["time"] >= day - pd.Timedelta(days=60)) & (oi["time"] <= day)]
        d0 = STK.daily_with_oi(hw.reset_index(drop=True), ow)
        if len(d0) < 30:
            continue
        old = STK.evaluate(d0)
        old_be = STK.evaluate_bear_engulf(d0)["side"] if not old["side"] else None
        d1, _, dq = DQ.reconcile(name, d0)
        if dq["holds"]:
            new, new_be, why = dict(side=None), None, "hold: " + "; ".join(dq["holds"])
        else:
            d1 = DQ.validate_daily_oi(d1, None, dq["ca_days"])
            new = STK.evaluate(d1)
            new_be = STK.evaluate_bear_engulf(d1)["side"] if not new["side"] else None
            why = new.get("why", "")
        rec = dict(name=name, day=day, old=old["side"], new=new["side"], old_be=old_be, new_be=new_be, why=why,
                   applied=bool(dq["applied"]), truncated=dq["truncated"] is not None, hold=bool(dq["holds"]),
                   old_doi=old.get("doi"), new_doi=new.get("doi"))
        if rec["old"] or rec["new"] or rec["old_be"] or rec["new_be"]:
            out.append(rec)
    return out


if __name__ == "__main__":
    man = pd.read_csv(DATA / "manifest_stocks.csv")
    with Pool(8) as p:
        rows = [r for x in p.map(one, list(man["name"])) for r in x]
    T = pd.DataFrame(rows)
    out = ROOT / "research/dq/results"; out.mkdir(parents=True, exist_ok=True)
    T.to_csv(out / "signals_old_vs_new.csv", index=False)
    L = ["# Live Stock OI rules – signals before vs after the data-quality fixes (2024-01-01 → 2026-10-22)\n"]
    for lab, a, b in (("OI breakout (BUY + SELL)", "old", "new"), ("Bearish engulfing SELL", "old_be", "new_be")):
        same = ((T[a] == T[b]) & T[a].notna()).sum()
        rem = T[T[a].notna() & (T[a] != T[b])]
        add = T[T[b].notna() & (T[a] != T[b])]
        L.append(f"## {lab}\n- unchanged: {same} · removed: {len(rem)} · added: {len(add)}\n")
        if len(rem):
            cause = np.where(rem["hold"], "data hold (unexplained gap / mismatch)", np.where(rem["truncated"], "demerger – history dropped",
                             np.where(rem["applied"], "price adjusted for a verified split/bonus", "OI validation")))
            L.append("removed by cause: " + str(pd.Series(cause).value_counts().to_dict()) + "\n")
            L.append(rem[["name", "day", a, "why", "old_doi"]].head(40).to_markdown(index=False) + "\n")
        if len(add):
            cause = np.where(add["applied"], "price adjusted for a verified split/bonus", "other")
            L.append("added by cause: " + str(pd.Series(cause).value_counts().to_dict()) + "\n")
            L.append(add[["name", "day", b, "new_doi"]].head(40).to_markdown(index=False) + "\n")
        unrelated = T[(T[a] != T[b]) & ~T["applied"] & ~T["truncated"] & ~T["hold"] & (T[a].notna() | T[b].notna())]
        if a == "old":
            unrelated = unrelated[~unrelated["why"].astype(str).str.contains("OI change not usable")]
        L.append(f"changes NOT explained by a corporate action, hold or OI validation: {len(unrelated)}\n")
    (out / "compare.md").write_text("\n".join(L))
    print("\n".join(L))

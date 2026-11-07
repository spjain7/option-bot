"""MCXE-004 – strict rolling 1-YEAR data windows (owner rule, 7-Nov-2026). Read-only.
For every market x dataset x timeframe: last complete session (reference), window start = reference - 1 calendar year
(+1 day, so the window is exactly one year inclusive), chronological DEV / VALID / OOS split (6 / 3 / 3 months), and the
sessions, bars and instruments inside each part. Writes research/mcxe004/windows.json and windows.csv.
Nothing older than the window start may be read by any MCXE-004 research script (enforced by mcxe004.window.clip()).
python research/mcxe004/windows.py"""
import json
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "research/mcxe004"
MCX7 = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]


def split(ref):
    ref = pd.Timestamp(ref).normalize()
    start = ref - pd.DateOffset(years=1) + pd.Timedelta(days=1)
    v0 = start + pd.DateOffset(months=6); o0 = start + pd.DateOffset(months=9)
    return start, v0, o0, ref


def summarise(name, market, tf, frames, complete_last):
    """frames: dict inst -> DataFrame(time, ...). complete_last: function(df)->last complete session date."""
    lasts = {k: complete_last(d) for k, d in frames.items() if len(d)}
    ref = max(lasts.values())
    behind = {k: str(v.date()) for k, v in lasts.items() if v < ref - pd.Timedelta(days=4)}
    start, v0, o0, ref = split(ref)
    rows = dict(market=market, dataset=name, timeframe=tf, reference=str(ref.date()), start=str(start.date()),
                valid_from=str(v0.date()), oos_from=str(o0.date()), instruments=len(frames), instruments_behind=len(behind))
    for lab, a, b in (("DEV", start, v0), ("VALID", v0, o0), ("OOS", o0, ref + pd.Timedelta(days=1))):
        days = set(); bars = 0; inst = 0
        for d in frames.values():
            x = d[(d.time >= a) & (d.time < b)]
            if len(x):
                inst += 1; bars += len(x); days |= set(x.time.dt.normalize())
        rows[f"{lab}_sessions"] = len(days); rows[f"{lab}_bars"] = bars; rows[f"{lab}_instruments"] = inst
    rows["behind_examples"] = dict(list(behind.items())[:5])
    return rows


def full_session(d):
    """last session whose bar count is >= 80 % of the median session (drops a truncated final day)."""
    day = d.time.dt.normalize(); c = day.value_counts().sort_index()
    ok = c[c >= 0.8 * c.median()]
    return ok.index.max()


def main():
    R = []
    from research.program import liqtl_mcx5 as LM
    for iv, tf in (("FIVE_MINUTE", "5m (-> 15/30/60m, daily)"), ("ONE_HOUR", "1h"), ("ONE_DAY", "1d")):
        fr = {n: LM.load(n, iv) for n in MCX7}
        R.append(summarise(f"Angel front-month {iv}", "MCX", tf, {k: v for k, v in fr.items() if v is not None},
                           full_session if iv != "ONE_DAY" else (lambda d: d.time.max().normalize())))
    from research.program import eq_data as ED
    syms = sorted(p.name.split("_FIVE_MINUTE")[0] for p in ED.EQ.glob("*_FIVE_MINUTE.csv.gz"))
    fr = {s: pd.read_csv(ED.EQ / f"{s}_FIVE_MINUTE.csv.gz", parse_dates=["time"], usecols=["time"]) for s in syms}
    R.append(summarise("Angel 5-min (today's 218 liquid names)", "NSE_EQ", "5m", fr, full_session))
    cm = sorted((ROOT / "research/data/nse_cm").glob("*.csv.gz"))
    last_years = [f for f in cm if int(f.name[:4]) >= 2025]
    P = pd.concat([pd.read_csv(f, usecols=["date", "symbol"], parse_dates=["date"]) for f in last_years])
    fr = {"ALL": P.rename(columns={"date": "time"})[["time"]].drop_duplicates()}
    r = summarise("official cash bhavcopy (point-in-time)", "NSE_EQ", "1d", fr, lambda d: d.time.max())
    start = pd.Timestamp(r["start"]); r["instruments"] = int(P[P.date >= start].symbol.nunique()); R.append(r)
    from research.adapters import nse_stkfut_pit as NF
    D = NF.load(start="2025-01-01", kinds=("STK",))
    fr = {"ALL": D.rename(columns={"date": "time"})[["time"]].drop_duplicates()}
    r = summarise("official F&O bhavcopy (point-in-time)", "NSE_FUT", "1d", fr, lambda d: d.time.max())
    r["instruments"] = int(D[D.date >= pd.Timestamp(r["start"])].symbol.nunique()); R.append(r)
    fr = {p.name.split("_ONE_HOUR")[0]: pd.read_csv(p, parse_dates=["time"], usecols=["time"])
          for p in (ROOT / "research/data/angel/NFO_STK").glob("*_ONE_HOUR.csv")}
    R.append(summarise("Angel 1-hour (today's list)", "NSE_FUT", "1h", fr, full_session))
    T = pd.DataFrame(R)
    T.to_csv(OUT / "windows.csv", index=False)
    (OUT / "windows.json").write_text(json.dumps(R, indent=1, default=str))
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(T.drop(columns=["behind_examples"]).to_string(index=False))
    for r in R:
        if r["behind_examples"]:
            print(r["market"], r["dataset"], "behind:", r["behind_examples"])


if __name__ == "__main__":
    main()

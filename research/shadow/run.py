"""Nightly shadow run (after NSE publishes the day's files, ~20:00 IST). SHADOW ONLY – no alerts, no orders.
python -m research.shadow.run [--state DIR] [--asof YYYY-MM-DD] [--local-cm research/data/nse_cm]
State DIR (the shadow-state branch): meta.json · signals_<id>.csv (append-only) · trades_<id>.csv (rebuilt) ·
bands/<date>.csv · reports/daily/<date>.md · reports/weekly/<year>-W<week>.md"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.shadow import rules as RU, data as DA, engine as EN, report as RP  # noqa: E402

IDS = ("SF-CONT-SELL-v1", "CM-CONT-BUY-v1")


def guard(state):
    """immutability: a ledger is bound to the rule hash it started with."""
    f = state / "meta.json"
    meta = json.loads(f.read_text()) if f.exists() else {}
    for sid in IDS:
        h = RU.rule_hash(sid)
        if sid in meta and meta[sid]["rule_hash"] != h:
            raise SystemExit(f"{sid}: rule code changed (stored {meta[sid]['rule_hash']}, now {h}). Rules are immutable during a "
                             f"test – create a new version id with its own ledger.")
        meta.setdefault(sid, dict(rule_hash=h, started=str(EN.START.date()), label=RU.RULES[sid]["label"], params=RU.RULES[sid]))
    f.write_text(json.dumps(meta, indent=1, default=str))
    return meta


def append(state, sid, new, run_day):
    f = state / f"signals_{sid}.csv"
    old = pd.read_csv(f, parse_dates=["signal_date", "detected_on"]) if f.exists() else pd.DataFrame()
    if len(new):
        new = new.assign(detected_on=pd.Timestamp(run_day), rule_hash=RU.rule_hash(sid))
        new["signal_id"] = new["strategy"] + "|" + new["symbol"] + "|" + pd.to_datetime(new["signal_date"]).dt.strftime("%Y-%m-%d")
        if len(old):
            new = new[~new.signal_id.isin(old.signal_id)]
        L = pd.concat([old, new], ignore_index=True)
    else:
        L = old
    if len(L):
        assert L.signal_id.is_unique, "duplicate signal in the ledger"
        L.to_csv(f, index=False)
    return L, (len(new) if len(new) else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--state", default=str(ROOT / "research/shadow/state_local"))
    ap.add_argument("--asof"); ap.add_argument("--local-cm"); a = ap.parse_args(argv)
    state = Path(a.state); state.mkdir(parents=True, exist_ok=True)
    run_day = pd.Timestamp(a.asof) if a.asof else pd.Timestamp(dt.date.today())
    meta = guard(state)
    P = DA.cm_history(EN.HIST_FROM, run_day, local=a.local_cm)
    days = pd.DatetimeIndex(sorted(P.date.unique()))
    asof = days[-1]
    EN.P_RAW.clear()
    q = P[(P.date >= EN.START) & (P.series == "EQ")]
    EN.P_RAW.update({(d, s): (o, h, l, pc, v) for d, s, o, h, l, pc, v in zip(q.date, q.symbol, q.open, q.high, q.low, q.prevclose, q.value)})
    A = EN.adjusted(P)
    regime = EN.market_regime(A); sectors = EN.sector_map()
    fo = DA.fo_days(EN.START - pd.Timedelta(days=7), asof)
    fo_ok = len(fo) and fo.date.max() == asof
    bands = {}
    b_today = DA.bands(run_day.date())
    if b_today:
        bands[pd.Timestamp(run_day.date())] = b_today
        (state / "bands").mkdir(exist_ok=True)
        pd.Series(b_today).rename("band").to_csv(state / "bands" / f"{run_day:%Y%m%d}.csv")
    for f in sorted((state / "bands").glob("*.csv")) if (state / "bands").exists() else []:
        bands.setdefault(pd.Timestamp(f.stem), pd.read_csv(f, index_col=0)["band"].astype(str).to_dict())
    bans = {d: DA.ban(d) for d in days[days >= EN.START]}
    mom = set()
    try:
        import subprocess
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "--depth", "1", "origin", "cash-state"], check=True, capture_output=True)
        st = json.loads(subprocess.run(["git", "-C", str(ROOT), "show", "FETCH_HEAD:cashstock/state.json"], check=True, capture_output=True, text=True).stdout)
        mom = {h["symbol"] if isinstance(h, dict) else str(h) for h in st.get("holdings", [])}
    except Exception:
        pass
    status = dict(run_day=str(run_day.date()), cash_data_to=str(asof.date()), fo_data_to=str(fo.date.max().date()) if len(fo) else None,
                  fo_complete=bool(fo_ok), bands_today=bool(b_today), ban_lists={str(d.date()): (v is not None) for d, v in bans.items()},
                  momentum_holdings=sorted(mom))
    res = {}
    # SF needs the F&O file of the signal day; without it no signal day is evaluated (never guessed)
    sf_new = EN.detect_sf(A, fo) if len(fo) else pd.DataFrame()
    if len(sf_new):
        sf_new = sf_new[sf_new.signal_date.isin(set(fo.date))]
    L, n_new = append(state, "SF-CONT-SELL-v1", sf_new, run_day)
    T = EN.lifecycle_sf(L, A, fo, days, regime, sectors, asof, bans) if len(L) else pd.DataFrame()
    res["SF-CONT-SELL-v1"] = dict(ledger=L, trades=T, new=n_new, redetected=sf_new)
    EN.WEEKLY = EN.weekly_panels(A)
    cm_new = EN.detect_cm(A, week_complete=lambda d: pd.Timestamp(d).weekday() == 4)
    L, n_new = append(state, "CM-CONT-BUY-v1", cm_new, run_day)
    T = EN.lifecycle_cm(L, A, days, regime, sectors, asof, bands, mom) if len(L) else pd.DataFrame()
    res["CM-CONT-BUY-v1"] = dict(ledger=L, trades=T, new=n_new, redetected=cm_new)
    for sid, r in res.items():
        if len(r["trades"]):
            r["trades"].to_csv(state / f"trades_{sid}.csv", index=False)
    RP.daily(state, run_day, status, res, meta)
    if run_day.weekday() == 4 or a.asof:
        RP.weekly(state, run_day, res, meta)
    print(json.dumps({k: dict(new=v["new"], ledger=len(v["ledger"]), trades=len(v["trades"])) for k, v in res.items()}), json.dumps(status))


if __name__ == "__main__":
    main()

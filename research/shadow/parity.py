"""Requirement 1 (owner 11-Nov): verify that the shadow rules (rules.py) reproduce the research trades EXACTLY before any
forward test. Rebuilds both candidates' historical trades with rules.sf_signal / cm_signal + rules.walk on the same
research data and compares them trade by trade with the research trade files.
python -m research.shadow.parity   ->  research/shadow/results/parity.json"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.shadow import rules as RU  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(exist_ok=True)


def replay(frames, signal_fn, p, cost_fn, expid_fn=None):
    """frames: list of per-instrument frames -> all trades with one open trade per instrument (signals inside an open
    trade are kept with status 'overlap')."""
    rows = []
    for b in frames:
        sig, risk, r, a = signal_fn(b)
        o, h, l, c = (b[x].astype(float).values for x in ("open", "high", "low", "close"))
        t = b["time"].values; exp = expid_fn(b) if expid_fn else np.zeros(len(b), np.int64)
        busy_until = -1
        for i in np.where(sig)[0]:
            base = dict(name=b["name"].iloc[0], signal=t[i])
            if i + 1 >= len(b) or not np.isfinite(risk[i]) or risk[i] <= 0:
                rows.append(dict(base, status="no next bar / no risk")); continue
            if i <= busy_until:
                rows.append(dict(base, status="overlap")); continue
            w = RU.walk(o, h, l, c, i + 1, p["side"], risk[i], p["target_R"], p["max_bars"])
            e, j = i + 1, w["exit_i"]
            cf = cost_fn(t[e]) * (2.0 if exp[j] != exp[e] else 1.0)
            costR = cf * o[e] / risk[i]
            rows.append(dict(base, status="trade" if w["done"] else "open", entry=t[e], exit=t[j], reason=w["reason"], grossR=w["gross_R"],
                             costR=costR, netR=w["gross_R"] - costR, mfe_R=w["mfe_R"], mae_R=w["mae_R"], bars=w["bars"]))
            busy_until = j
    return pd.DataFrame(rows)


def compare(mine, ref):
    m = mine[mine.status.isin(["trade", "open"])].copy()
    k = lambda x: x["name"].astype(str) + "|" + pd.to_datetime(x["entry"]).dt.strftime("%Y-%m-%d")
    m["k"], ref = k(m), ref.assign(k=k(ref))
    j = m.merge(ref[["k", "netR", "exit"]], on="k", how="outer", suffixes=("", "_ref"), indicator=True)
    both = j[j._merge == "both"]
    d = (both.netR - both.netR_ref).abs()
    return dict(shadow_trades=len(m), research_trades=len(ref), matched=len(both), only_shadow=int((j._merge == "left_only").sum()),
                only_research=int((j._merge == "right_only").sum()), max_abs_R_diff=round(float(d.max()), 6) if len(d) else None,
                same_exit_date=int((pd.to_datetime(both.exit) == pd.to_datetime(both.exit_ref)).sum()),
                shadow_mean_R=round(float(m.netR.mean()), 4), research_mean_R=round(float(ref.netR.mean()), 4),
                overlap_signals_not_taken=int((mine.status == "overlap").sum()))


def sf():
    from research.rsidiv import sf_check as SC, stockfut as SF
    stocks = SC.load()

    def expid(b):
        e = pd.Series(b["exp"]).astype("datetime64[ns]")
        return np.where(e.notna(), e.values.astype("datetime64[D]").astype(np.int64), -1)
    mine = replay(stocks, RU.sf_signal, RU.RULES["SF-CONT-SELL-v1"], lambda t: float(SF.fut_cost(np.array([t]))[0]), expid)
    ref = pd.read_csv(ROOT / "research/rsidiv/results/sf_check_trades.csv.gz")
    return mine, compare(mine, ref)


def cm_frames():
    from research.cashq import data as D
    W = D.daily_panel(); Wk = D.weekly(W); del W
    el = Wk["elig"].astype(bool)
    tor = Wk["value"].rolling(12, min_periods=8).median().shift(1).where(el).rank(axis=1, pct=True)
    idx = Wk["close"].index; frames = []
    for k in Wk["close"].columns:
        ok = Wk["close"][k].notna().values
        if ok.sum() < 60:
            continue
        b = pd.DataFrame(dict(time=idx[ok], **{f: Wk[f][k].values[ok] for f in ("open", "high", "low", "close", "volume", "value")}))
        b["elig"] = el[k].values[ok]; b["liq_rank"] = tor[k].values[ok]; b["name"] = str(Wk["symbol"][k])
        frames.append(b)
    return frames


def cm():
    frames = cm_frames()
    p = RU.RULES["CM-CONT-BUY-v1"]
    fixed = []
    for b in frames:
        b = b.copy()
        for col in ("open", "high", "low"):
            b[col] = b[col].where(b[col] > 0).fillna(b["close"])
        fixed.append(b)
    mine = replay(fixed, RU.cm_signal, p, lambda t: p["cost_round_trip"])
    ref = pd.read_csv(ROOT / "research/rsidiv/results/cash_check_trades.csv.gz")
    return mine, compare(mine, ref)


def main():
    res = {}
    for nm, fn in (("SF-CONT-SELL-v1", sf), ("CM-CONT-BUY-v1", cm)):
        mine, r = fn(); res[nm] = r; print(nm, r, flush=True)
        mine.to_csv(OUT / f"parity_{nm}.csv.gz", index=False, compression="gzip")
    json.dump(res, open(OUT / "parity.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

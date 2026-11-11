"""Daily reconciliation and weekly performance reports for the shadow test (markdown + the trade CSVs beside them)."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REF = {"SF-CONT-SELL-v1": ROOT / "research/rsidiv/results/sf_check_trades.csv.gz",
       "CM-CONT-BUY-v1": ROOT / "research/rsidiv/results/cash_check_trades.csv.gz"}
CLOSED = ("TARGET", "STOP", "TIME")


def _closed(T):
    return T[T.status.astype(str).str.startswith(CLOSED)] if len(T) and "status" in T else T.iloc[0:0] if len(T) else pd.DataFrame()


def stats(r):
    r = pd.Series(r, dtype=float).dropna()
    if not len(r):
        return dict(n=0)
    w = r > 0; gl = -r[~w].sum()
    return dict(n=len(r), win_pct=round(100 * w.mean(), 1), avg_R=round(r.mean(), 3), sum_R=round(r.sum(), 2),
                PF=round(r[w].sum() / gl, 2) if gl > 0 else None)


def expectation(sid, n):
    try:
        x = pd.read_csv(REF[sid]).netR
    except Exception:
        return ""
    if n == 0:
        return f"research: {len(x)} trades, avg {x.mean():+.3f}R"
    se = x.std(ddof=1) / np.sqrt(n)
    return f"research avg {x.mean():+.3f}R; with {n} closed trades a result between {x.mean() - 1.96 * se:+.2f}R and {x.mean() + 1.96 * se:+.2f}R is consistent with it"


def _tbl(df, cols):
    if not len(df):
        return "_none_\n"
    c = [k for k in cols if k in df]
    h = "| " + " | ".join(c) + " |\n|" + "---|" * len(c) + "\n"
    return h + "".join("| " + " | ".join("" if pd.isna(v) else (str(v.date()) if isinstance(v, pd.Timestamp) else str(v)) for v in row) + " |\n"
                       for row in df[c].itertuples(index=False))


def daily(state, run_day, status, res, meta):
    d = Path(state) / "reports" / "daily"; d.mkdir(parents=True, exist_ok=True)
    s = [f"# Shadow test – daily reconciliation {run_day:%d-%b-%Y}\n",
         "SHADOW ONLY: nothing was sent and no order was placed. Rules are fixed (hash in meta.json).\n",
         f"Data: cash bhavcopy to **{status['cash_data_to']}** · F&O bhavcopy to **{status['fo_data_to']}** "
         f"({'complete' if status['fo_complete'] else 'NOT complete – stock-futures signals for the missing day are not evaluated yet'}) · "
         f"cash price bands today: {'saved' if status['bands_today'] else 'not available'} · "
         f"F&O ban lists: {sum(status['ban_lists'].values())} of {len(status['ban_lists'])} sessions available\n"]
    for sid, r in res.items():
        L, T = r["ledger"], r["trades"]
        s.append(f"\n## {sid} – {meta[sid]['label']} (rule hash {meta[sid]['rule_hash']})\n")
        s.append(f"New signals recorded today: **{r['new']}** · in ledger: {len(L)}\n")
        if len(L) and len(r["redetected"]) is not None:
            red = set(r["redetected"].get("signal_id", pd.Series(dtype=str))) if "signal_id" in r["redetected"] else \
                set((r["redetected"]["strategy"] + "|" + r["redetected"]["symbol"] + "|" + pd.to_datetime(r["redetected"]["signal_date"]).dt.strftime("%Y-%m-%d"))) if len(r["redetected"]) else set()
            miss = sorted(set(L.signal_id) - red)
            s.append(f"Reconciliation (full re-detection vs ledger): {len(red)} re-detected; ledger signals NOT re-detected: "
                     f"{len(miss)}{' – ' + ', '.join(miss[:10]) if miss else ''}\n")
            late = L[pd.to_datetime(L.detected_on) > pd.to_datetime(L.signal_date)]
            s.append(f"Detected after the signal day (a missed or late run; real-time entry may have been impossible): {len(late)}\n")
        if len(T):
            vc = T.status.astype(str).str.split(" –").str[0].value_counts().to_dict()
            s.append("Status: " + " · ".join(f"{k} {v}" for k, v in vc.items()) + "\n")
            today = T[pd.to_datetime(T.signal_date) == pd.Timestamp(status["cash_data_to"])]
            s.append("\n**Signals of the latest session**\n\n" + _tbl(today, ["symbol", "close", "rsi", "risk_pct", "market_up", "sector", "status"]))
            act = T[T.status.astype(str).str.startswith(("ACTIVE", "PENDING"))]
            s.append("\n**Open / pending**\n\n" + _tbl(act, ["symbol", "signal_date", "entry_date", "contract", "entry_px", "stop_px", "target_px",
                                                          "last_px", "sessions", "exec_R", "mfe_R", "mae_R", "depth", "half_spread_pct", "status"]))
            ne = T[T.status.astype(str).str.startswith(("NOT EXECUTABLE", "OVERLAP"))]
            s.append("\n**Not executed (with reason)**\n\n" + _tbl(ne, ["symbol", "signal_date", "entry_date", "status"]))
            c = _closed(T)
            s.append("\n**Closed**\n\n" + _tbl(c, ["symbol", "signal_date", "entry_date", "exit_date", "status", "exec_R", "research_R",
                                                 "exec_net_pct", "pnl_per_lot_rs", "pnl_per_100_shares_rs", "mfe_R", "mae_R"]))
    (d / f"{run_day:%Y-%m-%d}.md").write_text("\n".join(s))


def weekly(state, run_day, res, meta):
    d = Path(state) / "reports" / "weekly"; d.mkdir(parents=True, exist_ok=True)
    y, w, _ = run_day.isocalendar()
    s = [f"# Shadow test – weekly performance, week {w} of {y} (to {run_day:%d-%b-%Y})\n",
         "SHADOW ONLY. Forward evidence starts 11-Nov-2026. Losses, missed and non-executable signals are all included.\n"]
    for sid, r in res.items():
        T = r["trades"]
        s.append(f"\n## {sid} – {meta[sid]['label']}\n")
        if not len(T):
            s.append("No signals yet.\n"); continue
        c = _closed(T)
        s.append(f"Signals {len(T)} · executed {int(T.get('entry_px', pd.Series(dtype=float)).notna().sum())} · "
                 f"not executable {int(T.status.astype(str).str.startswith('NOT EXECUTABLE').sum())} · overlap {int(T.status.astype(str).str.startswith('OVERLAP').sum())} · "
                 f"open {int(T.status.astype(str).str.startswith('ACTIVE').sum())} · closed {len(c)}\n")
        st = stats(c.get("exec_R", pd.Series(dtype=float)))
        s.append(f"Closed, execution basis: {st}\n\nClosed, research basis: {stats(c.get('research_R', pd.Series(dtype=float)))}\n")
        s.append(f"{expectation(sid, st.get('n', 0))}\n")
        if len(c):
            s.append(f"Average MFE {c.mfe_R.mean():.2f}R · MAE {c.mae_R.mean():.2f}R · sessions held {c.sessions.mean():.1f} · "
                     f"execution minus research {(c.exec_R - c.research_R).mean():+.3f}R per trade\n")
            for col in ("market_up", "sector"):
                g = c.groupby(col).exec_R.agg(["size", "mean"]).round(3)
                s.append(f"\nBy {col}:\n\n" + _tbl(g.reset_index(), [col, "size", "mean"]))
    (d / f"{y}-W{w:02d}.md").write_text("\n".join(s))

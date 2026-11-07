"""MCXE-004 research execution register, metrics, status system and alert card.

REGISTER  Every research execution writes ONE JSON line to research/mcxe004/register/executions.jsonl (append-only) with
          the fields required by the owner (experiment_id ... error_details). Missing values are null, never guessed.
          Lifecycle (enforced):  PENDING -> RUNNING -> COMPLETED | FAILED | BLOCKED | INSUFFICIENT_DATA
STATUS    validation_status of a strategy / signal (enforced vocabulary):
          RESEARCH_ONLY · PAPER_ONLY · VALIDATED_CANDIDATE · REJECTED · INSUFFICIENT_DATA · BLOCKED · ERROR
          classify() applies the pre-registered MCXE-004 rules (PROTOCOL.md §3-§4) – nothing is promoted on win rate alone.
METRICS   metrics(trades) from trade-level net R only. Without trade outcomes a script is SIGNAL-ONLY: no accuracy is computed.
CARD      alert_card(signal, evidence) – the transparent alert text; accuracy is shown only with its sample size, unique dates
          and confidence interval, and only from OOS trades; otherwise "INSUFFICIENT DATA". Never "x % accurate".
"""
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "research/mcxe004/register/executions.jsonl"
RUN_STATES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "BLOCKED", "INSUFFICIENT_DATA")
TRANSITIONS = {"PENDING": {"RUNNING", "BLOCKED", "FAILED"}, "RUNNING": {"COMPLETED", "FAILED", "BLOCKED", "INSUFFICIENT_DATA"}}
VALIDATION = ("RESEARCH_ONLY", "PAPER_ONLY", "VALIDATED_CANDIDATE", "REJECTED", "INSUFFICIENT_DATA", "BLOCKED", "ERROR")
FIELDS = ["experiment_id", "script_id", "strategy_name", "market", "instrument", "timeframe", "data_start_date", "data_end_date",
          "execution_start", "execution_end", "status", "progress_stage", "total_signals", "eligible_signals",
          "executed_backtest_trades", "rejected_signals", "rejection_reasons", "win_rate", "net_expectancy_R", "profit_factor",
          "net_pnl", "max_drawdown", "costs", "sample_dates", "confidence_interval", "validation_status", "conclusion",
          "artifact_paths", "code_commit", "error_details"]
# PROTOCOL.md §3 minimum OOS sample by horizon
MIN_OOS = {"intraday": (30, 20), "btst": (30, 20), "positional": (20, 15)}


def code_commit():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:                                          # noqa: BLE001
        return None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Execution:
    """with Execution(script_id=..., strategy_name=..., ...) as ex: ... ex.stage('...'); ex.finish(**fields)"""

    def __init__(self, path=REG, **meta):
        self.path = Path(path)
        self.rec = {k: None for k in FIELDS}
        self.rec.update(meta)
        self.rec["experiment_id"] = meta.get("experiment_id") or f"{meta.get('script_id', 'X')}-{uuid.uuid4().hex[:8]}"
        self.rec["status"] = "PENDING"
        self.rec["code_commit"] = code_commit()

    def _to(self, new):
        cur = self.rec["status"]
        if new not in TRANSITIONS.get(cur, set()):
            raise ValueError(f"illegal status transition {cur} -> {new}")
        self.rec["status"] = new

    def __enter__(self):
        self._to("RUNNING"); self.rec["execution_start"] = _now(); self.rec["progress_stage"] = "started"
        return self

    def stage(self, s):
        self.rec["progress_stage"] = s

    def finish(self, status="COMPLETED", **fields):
        bad = set(fields) - set(FIELDS)
        if bad:
            raise KeyError(f"unknown register fields {bad}")
        if fields.get("validation_status") not in (None,) + VALIDATION:
            raise ValueError(f"unknown validation_status {fields.get('validation_status')}")
        self.rec.update(fields)
        self._to(status)

    def __exit__(self, et, ev, tb):
        if et is not None:
            self.rec["status"] = "FAILED"
            self.rec["error_details"] = f"{et.__name__}: {ev}"
            self.rec["validation_status"] = "ERROR"
        elif self.rec["status"] == "RUNNING":                 # finished without an explicit result
            self.rec["status"] = "FAILED"; self.rec["error_details"] = "execution ended without finish()"
            self.rec["validation_status"] = "ERROR"
        self.rec["execution_end"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(_clean(self.rec), default=str) + "\n")
        return True                                            # failures are recorded, never silent, never crash the batch


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


def load(path=REG):
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=FIELDS)
    return pd.DataFrame([json.loads(x) for x in p.read_text().splitlines() if x.strip()])


# ── metrics ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def metrics(T, r="r1", date="date"):
    """T: trades with net R column `r` (after realistic costs) and entry `date`. Returns the required accuracy /
    profitability numbers; win = net R > 0 after costs. Empty -> n = 0 and everything else None."""
    from research.mcxe003 import bootstrap as BT
    x = pd.Series(np.asarray(T[r], float), index=T.index) if len(T) else pd.Series(dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return dict(trades=0, wins=0, losses=0, win_rate=None, avg_win=None, avg_loss=None, expectancy_R=None,
                    profit_factor=None, net_R=None, max_drawdown_R=None, unique_dates=0, ci95=None)
    w, l = x[x > 0], x[x <= 0]
    eq = x.cumsum().values
    dd = float((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max())
    ci = BT.block_ci(pd.to_datetime(T.loc[x.index, date]).values if len(T) else [], x.values) if len(x) > 1 else None
    return dict(trades=int(len(x)), wins=int(len(w)), losses=int(len(l)), win_rate=round(100 * len(w) / len(x), 1),
                avg_win=round(float(w.mean()), 3) if len(w) else None, avg_loss=round(float(l.mean()), 3) if len(l) else None,
                expectancy_R=round(float(x.mean()), 4),
                profit_factor=(round(float(w.sum() / -l.sum()), 3) if len(l) and l.sum() < 0 else None),
                net_R=round(float(x.sum()), 2), max_drawdown_R=round(dd, 2),
                unique_dates=int(pd.to_datetime(T.loc[x.index, date]).dt.normalize().nunique()),
                ci95=(ci or {}).get("ci95_conservative"))


def classify(oos, oos2x, horizon, selection_overlaps_window, controls_run, error=None, blocked=None):
    """Pre-registered MCXE-004 decision (PROTOCOL.md §3-§4). Returns (validation_status, reason)."""
    if error:
        return "ERROR", error
    if blocked:
        return "BLOCKED", blocked
    n_min, d_min = MIN_OOS[horizon]
    if not oos or oos.get("trades", 0) < n_min or oos.get("unique_dates", 0) < d_min:
        return "INSUFFICIENT_DATA", (f"OOS {oos.get('trades', 0) if oos else 0} trades / {oos.get('unique_dates', 0) if oos else 0} "
                                     f"dates < required {n_min} / {d_min}")
    lo = (oos.get("ci95") or [None])[0]
    fails = []
    if not (oos.get("expectancy_R") or 0) > 0:
        fails.append("OOS expectancy <= 0 at 1x cost")
    if not ((oos2x or {}).get("expectancy_R") or 0) > 0:
        fails.append("OOS expectancy <= 0 at 2x cost")
    if lo is None or not lo > 0:
        fails.append(f"OOS 95% CI lower bound {lo} not > 0")
    if fails:
        return "REJECTED", "; ".join(fails)
    if selection_overlaps_window:
        return "PAPER_ONLY", "passes OOS checks, but the rule was selected on data that includes this window – forward paper test only"
    if not controls_run:
        return "PAPER_ONLY", "passes OOS checks, matched controls not run – forward paper test only"
    return "VALIDATED_CANDIDATE", "all pre-registered OOS checks passed (still not promoted without forward evidence)"


# ── alert card ──────────────────────────────────────────────────────────────────────────────────────────────────────
def alert_card(sig, ev):
    """sig: dict(strategy, script_id, market, instrument, side, entry, sl, target, invalidation, time, timeframe,
    data_age_min, cost_R). ev: register record of the strategy's latest window evaluation (OOS metrics nested in ev['oos']).
    Accuracy appears only as an OOS historical frequency with n, dates and CI – never as a prediction."""
    o = (ev or {}).get("oos") or {}
    st = (ev or {}).get("validation_status") or "RESEARCH_ONLY"
    if not ev or "oos" not in ev:
        acc = "NOT EVALUATED inside the 1-year window – no historical accuracy available"
    elif o.get("trades"):
        acc = (f"OOS {o['wins']}/{o['trades']} trades profitable after costs ({o['win_rate']:.0f} %), {o['unique_dates']} dates · "
               f"expectancy {o['expectancy_R']:+.2f}R · PF {o['profit_factor'] if o['profit_factor'] is not None else 'n/a'} · "
               f"max DD {o['max_drawdown_R']}R · 95 % CI of expectancy {o['ci95']}")
    else:
        acc = "OOS: no trades"
    if st == "INSUFFICIENT_DATA":
        acc = "INSUFFICIENT DATA – " + acc
    lv = lambda k: ("—" if sig.get(k) is None else f"{sig[k]:,}")  # noqa: E731
    lines = [f"[{st}] {sig.get('side')} {sig.get('instrument')} ({sig.get('market')}) · {sig.get('strategy')} · {sig.get('script_id')}",
             f"signal {sig.get('time')} · {sig.get('timeframe')} · data age {sig.get('data_age_min', 'n/a')} min",
             f"entry {lv('entry')} · SL {lv('sl')} · target {lv('target')} · invalidation {sig.get('invalidation') or '—'}",
             f"est. cost {sig.get('cost_R', 'n/a')} R · window {ev.get('data_start_date') if ev else '—'} → {ev.get('data_end_date') if ev else '—'}",
             f"evidence: {acc}",
             f"reason: {(ev or {}).get('conclusion') or 'no window evaluation'}",
             "historical frequency in a past window, not a probability of this trade; research / paper only"]
    return "\n".join(lines)

"""CASHQ-BUY stage 3 – SHADOW positional BUY candidates (logged only: no Telegram, no orders).
Reads results/buy_events_scored.csv.gz (run buy_events + buy_score first, on the latest bhavcopy) and writes
  results/shadow_candidates.csv  – signals of the last 5 sessions with score >= 55, ranked, with the trade plan
  results/shadow_ledger.csv      – every signal with score >= 55 since SHADOW_START and its tracked outcome
Plan per candidate: entry = next session's open (skip if it opens more than 1 ATR above the signal close), stop = entry −
3 ATR, T1 = +1R, T2 = +2R, then trail: exit on a close below EMA50; max 250 sessions. Quantity for ₹10,000 risk shown.
python -m research.cashq.buy_shadow"""
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "results"
SHADOW_START = "2026-11-01"
RISK_RS = 10_000


def main():
    T = pd.read_csv(OUT / "buy_events_scored.csv.gz", parse_dates=["entry_time", "signal_time", "exit_time"])
    last = T["exit_time"].max()
    S = T[(T["signal_time"] >= SHADOW_START) & (T["score"] >= 55)].copy()
    atr = S["risk"] / 3
    S["status"] = np.where(S["open_trade"], "OPEN", "CLOSED")
    S["stop"] = (S["entry"] - S["risk"]).round(2)
    S["T1"], S["T2"] = (S["entry"] + S["risk"]).round(2), (S["entry"] + 2 * S["risk"]).round(2)
    S["qty_for_10k_risk"] = np.floor(RISK_RS / S["risk"]).astype(int)
    S["stop_pct"] = (100 * S["risk"] / S["entry"]).round(1)
    led = S[["signal_time", "symbol", "score", "entry_time", "entry", "stop", "T1", "T2", "stop_pct", "qty_for_10k_risk", "status", "exit_time",
             "exit", "netR", "bars", "rs126", "adx", "tight", "clv", "breadth50", "turnover_cr"]].sort_values(["signal_time", "score"], ascending=[True, False])
    led.loc[led.status == "OPEN", ["exit", "netR"]] = np.nan
    led.round(3).to_csv(OUT / "shadow_ledger.csv", index=False)
    days = sorted(T["signal_time"].unique())[-5:]
    C = led[led["signal_time"].isin(days)].sort_values("score", ascending=False)
    C.round(3).to_csv(OUT / "shadow_candidates.csv", index=False)
    print(f"data to {last.date()} · shadow signals since {SHADOW_START}: {len(led)} (open {int((led.status == 'OPEN').sum())})")
    print(C[["signal_time", "symbol", "score", "entry", "stop", "T1", "T2", "stop_pct", "status", "rs126", "adx"]].to_string(index=False))


if __name__ == "__main__":
    main()

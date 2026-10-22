# Alert experiments (registered before running)

## ALERT-EXP-002 – extra filters against fake reversal calls (registered 22-Oct-2026)
Baseline: the LIVE alert rule (RSI extreme + reversal candle + quality layer), next-candle-open entry, half at T1, 0.1R costs.
Each filter is tested alone on top of the baseline: F1 daily-trend alignment, F2 RSI divergence, F3 next-candle break confirmation.
A filter is switched ON only if ALL hold: ≥ +0.05R improvement pooled; better in both halves (≤2023 / ≥2024);
better in ≥ 60% of instrument×timeframe groups (≥ 10 trades); bootstrap p5 of the improvement > 0; ≥ 100 trades remain.
Data 2020-26 already seen → exploratory. Code: `alerts/exp_filters.py`; results: `alerts/results/EXP-002/`.

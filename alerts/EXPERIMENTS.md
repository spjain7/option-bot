# Alert experiments (registered before running)

## ALERT-EXP-002 – extra filters against fake reversal calls (registered 22-Oct-2026)
Baseline: the LIVE alert rule (RSI extreme + reversal candle + quality layer), next-candle-open entry, half at T1, 0.1R costs.
Each filter is tested alone on top of the baseline: F1 daily-trend alignment, F2 RSI divergence, F3 next-candle break confirmation.
A filter is switched ON only if ALL hold: ≥ +0.05R improvement pooled; better in both halves (≤2023 / ≥2024);
better in ≥ 60% of instrument×timeframe groups (≥ 10 trades); bootstrap p5 of the improvement > 0; ≥ 100 trades remain.
Data 2020-26 already seen → exploratory. Code: `alerts/exp_filters.py`; results: `alerts/results/EXP-002/`.

### Result (706 baseline alerts, 2020-26): **no filter passes – none switched on**
| | Alerts kept | Avg R | Win % | PF | Improvement | Both halves | Groups better | Boot p5 | Losers removed / winners kept |
|---|---|---|---|---|---|---|---|---|---|
| Baseline (live rule) | 706 | −0.099 | 48.3 | 0.81 | – | – | – | – | – |
| F1 daily trend | 144 (20%) | −0.046 | 52.1 | 0.90 | +0.053 | no (+0.27 / −0.07) | 2/2 | −0.063 | 81% / 22% |
| F2 RSI divergence | 18 (3%) | −0.285 | 38.9 | 0.58 | −0.186 | no | – | −0.606 | 97% / 2% |
| F3 next-candle confirm | 469 (66%) | −0.060 | 49.9 | 0.88 | +0.039 | yes (+0.03 / +0.05) | 10/13 | −0.011 | 36% / 69% |
F3 is the most consistent (better in both halves and 10 of 13 groups) but misses the +0.05R and bootstrap thresholds;
all variants remain negative after costs.

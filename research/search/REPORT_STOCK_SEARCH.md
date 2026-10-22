# STOCK-SEARCH-001 – result: no rule passes → stock-futures alerts stay OFF
Design Jul-2022 → Jun-2024 (strong bull market) · hold-out Jul-2024 → Oct-2026 (weak / sideways market) · 181 stocks.
| Rule | Design trades | Design avg R | PF | Bootstrap p5 | Shortlisted | Hold-out |
|---|---|---|---|---|---|---|
| Bollinger lower-band buy in uptrend | 286 | +0.11 | 1.41 | +0.04 | yes | **−0.13R**, PF 0.68 → FAIL |
| Gap & go | 499 | +0.08 | 1.18 | +0.00 | no | – |
| 250-day high + volume | 417 | +0.05 | 1.12 | −0.05 | no | – |
| Volume breakout + market / relative-strength filter | 648–762 | +0.04 | 1.08–1.09 | −0.04 | no | – |
| NR7 trend breakout | 1,253 | +0.04 | 1.08 | −0.02 | no | – |
| RSI(2) pullback (long / both) | 946–1,145 | +0.02–0.03 | 1.12–1.14 | −0.01 | no | – |
| Trend pullback RSI 40 | 81 | +0.03 | 1.12 | −0.12 | no | – |

**Momentum top-10 portfolio:**

| Period | Strategy, annualised | Equal-weight benchmark, annualised | Strategy Sharpe | Benchmark Sharpe |
|---|---|---|---|---|
| Design | +119% | +55% | 3.15 | 2.99 |
| Hold-out | −5.7% | −2.6% | −0.15 | −0.07 |

Result: FAIL in the hold-out.

What worked in the 2023-24 bull market (buying dips, momentum, longs) stopped working in 2024-26. Short setups were negative in every family.
Conclusion: there is no stock-futures formula with evidence that survives unseen data, so no stock alerts are switched on.

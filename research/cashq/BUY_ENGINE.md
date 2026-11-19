# CASHQ-BUY – NSE cash BUY-call engine: research dashboard (10-Nov-2026)

Status: **SHADOW only** (no Telegram, no orders). Branch `exp/cash-equity-engine`, PR #65.

## Verified starting point (from the ledgers, not from memory)
* 2,001 earlier variants: 0 intraday / 0 swing / 0 OI pass; 5 positional-trend PASS (F1 52-week high, F2 RS breakout,
  weekly Donchian / pull-back). F1 ledger re-computed independently: 785 / 785 closed trades identical.
* Monthly momentum portfolio (cashstock/, EQ-MOM-003): 2016-26 CAGR 23.9 %, max DD −20.6 % – still the best cash result.

## Engine (two stages)
1. **Discovery** – every point-in-time liquid stock (₹25 cr turnover, ≥ ₹50, ≥ 250 sessions): first close above the
   50-session high in 5 sessions → 7,617 events 2006-26 (`buy_events.py`).
2. **Confirmation / rank** – 100-point score (`buy_score.py`), built only from features that worked in BOTH 2005-14 and
   2015-19: relative strength 35 · trend strength (ADX) 25 · tight base before the breakout 20 · entry not a blow-off
   close 10 · market breadth 10. No sector points (no sector data).
Plan: entry next open · stop 3 ATR · T1 +1R · T2 +2R · then exit on a close below EMA50 (avg hold ~35 sessions).

## Feature ablation (net R per trade, low / mid / high tercile; DEV 2005-14 | VALID 2015-19)
| feature | DEV | VALID | kept? |
|---|---|---|---|
| relative strength 126d | +0.15 / +0.18 / **+0.35** | −0.12 / −0.07 / **+0.09** | yes |
| ADX | +0.13 / +0.23 / **+0.32** | −0.13 / +0.01 / **+0.05** | yes |
| tight base (ATR10/50 low) | **+0.30** / +0.13 / +0.25 | **+0.09** / −0.08 / −0.07 | yes |
| close at the very top of the day (clv high) | +0.33 / +0.26 / **+0.10** | +0.07 / −0.10 / −0.07 | yes (penalised) |
| breadth (stocks above EMA50) | +0.18 / +0.32 / +0.18 | −0.10 / +0.07 / +0.27 | weak, small weight |
| relative volume | +0.28 / +0.21 / +0.20 | −0.13 / +0.05 / −0.03 | **no** – volume expansion did not help |
| OBV high / CMF / up-down volume | flat or inconsistent | flat or inconsistent | **no** |
| market MA100 filter | +0.14 off / +0.26 on | −0.02 / −0.03 | **no** (no effect 2015-19) |
| RS acceleration, extension, 52-week high, new highs − lows | inconsistent | inconsistent | no |

## Scorecard – completed trades only, after costs (stop-first; open trades excluded)
| period | score | trades | win % | T1 hit % | T2 hit % | stopped % | avg R | PF | max DD (R) |
|---|---|---|---|---|---|---|---|---|---|
| OOS 2020-26 | all | 4,585 | 33.2 | 43.8 | 25.3 | 24.0 | +0.20 | 1.40 | 299 |
| OOS 2020-26 | 0-39 | 1,901 | 32.6 | 41.0 | 23.1 | 19.7 | +0.17 | 1.36 | 119 |
| OOS 2020-26 | 40-54 | 1,210 | 32.1 | 44.1 | 24.5 | 24.1 | +0.10 | 1.20 | 134 |
| OOS 2020-26 | 55-69 | 1,013 | 34.9 | 46.1 | 28.3 | 26.9 | +0.29 | 1.58 | 82 |
| OOS 2020-26 | **70-100** | 461 | 34.5 | 48.8 | 29.7 | 34.7 | **+0.35** | 1.65 | 72 |
| VALID 2015-19 | 70-100 | 161 | 31.7 | 44.1 | 26.1 | 30.4 | +0.28 | 1.51 | 33 |
| VALID 2015-19 | 0-39 | 604 | 26.0 | 35.4 | 17.2 | 18.5 | −0.15 | 0.70 | 98 |

Score ≥ 70 by year (OOS): 2020 +1.77R · 2021 +0.25 · 2022 −0.44 · 2023 +1.85 · **2024 −0.55 · 2025 −0.22 · 2026 −0.06**.

## Honest verdict
* The score ranks correctly (higher bucket → better result in DEV, VALID and OOS), so it is useful for choosing among
  candidates. It is a rank, not a probability.
* **Accuracy is low: about 1 in 3 trades wins, T1 is reached in about half.** The profit comes from a few large winners.
  No tested BUY setup has both a high win rate and a positive result after costs.
* The last three years (2024-26) are negative for the top bucket. Not ready for calls; forward shadow first.
* Intraday BUY: no validated strategy (1,680 variants negative after costs) → no intraday shadow (it would log a known loser).

## Dashboard
1 best intraday BUY: none · 2 best positional: score ≥ 70 breakout (above) · 3 best breakout: F1 52-week high + EMA50 trail
(OOS +0.34R, PF 1.71) · 4 best relative strength: F2 (OOS +0.24R) / monthly momentum portfolio · 5 best volume: none
(volume filters did not add) · 6 best divergence: none passed (W%R regular +0.02R OOS) · 7 best combination: the score ·
8 best risk-adjusted: monthly momentum portfolio (DD −20.6 %) · 9 current shadow candidates: `results/shadow_candidates.csv`
· 10 completed shadow trades: `results/shadow_ledger.csv` (started 1-Nov-2026; none closed yet) · 11 failed: `results/REPORT.md`
· 12 gaps: sector map, delivery %, NIFTY history, daily auto-refresh of the bhavcopy for the shadow (needs a scheduled job).

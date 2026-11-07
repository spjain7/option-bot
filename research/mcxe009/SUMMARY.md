# MCXE-009 weighted indicator scoring: summary (EXPLORATORY; nothing here is validation)

## Does weighting beat equal weights, single indicators and simple baselines? (VALID 2× of the DEV-chosen picks, `selection.csv`)

| Market / side | Best weighted | Equal | Best single | Donchian-20 | Verdict |
|---|---|---|---|---|---|
| MCX 1h BUY | +0.60R (equal won on DEV) | +0.60R | +0.65R (adx) | +0.25R | Scores beat the breakout baseline; weighting adds nothing over equal / single |
| MCX 1h SELL | +0.05R | +0.32R | +0.29R | +0.34R | Weighting worse |
| MCX 4h BUY | +0.41R (trend; VALID n = 17) | +0.40R | +0.03R | +0.16R | Sample too small (VALID < 30 trades) |
| MCX 4h SELL | +0.51R (data-driven; n = 22) | +0.52R | +0.41R | +0.36R | Sample too small; DEV was ≈ 0 |
| MCX daily | — (DEV samples below the minimum) | — | ±0.1 to 0.4R (n ≈ 22) | −0.30R | Insufficient data |
| Stock fut BUY | **+0.20R** (data-driven, 170 trades) | −0.15R | −0.19R | −0.22R | Weighting helps, but see controls |
| Stock fut SELL | −0.01R | −0.27R | −0.20R | −0.28R | Fail |
| Index 1d / 1h | −0.31 to −0.06R | −0.50 to −0.31R | −0.23 to −0.01R | −0.32 to −0.10R | Fail / insufficient |

## Controls on the two standouts (`controls.json`)
- **Stock futures BUY, data-driven (θ 0.6): rejected as a strategy.**
  - The DEV-fitted weights are **negative** on trend and momentum (ema −0.21, adx −0.17, brk −0.16, price −0.16). So the score buys the most oversold stocks.
  - It beats random long entries (DEV +0.27R vs −0.19R; VALID +0.20R vs −0.18R) and NIFTY on the same dates.
  - But **84 % of DEV + VALID profit comes from March 2026** (the post-crash rebound), with up to 67 trades on one day. The combined DEV + VALID CI is [−0.33, +0.80].
  - It is a market-timing effect concentrated in one month.
- **MCX 1h BUY, equal weights (θ 0.6): exploratory pass, but not new.**

  | Period | Trades | Strategy at 2× | Random entries (95th percentile) |
  |---|---|---|---|
  | DEV | 117 | +0.80R | +0.44R (0.75) |
  | VALID | 44 (31 dates) | +0.60R | +0.00R (0.55) |

  - VALID: 43 % win rate, profit factor 2.28.
  - Combined CI [+0.30, +1.32]; 7 of 9 months positive; largest month 26 %, largest commodity 25 % (SILVER).
  - **However, 77 % of its trades coincide with H1.12L trades** (same commodity, within 24 h), and daily P&L correlation is 0.77. It is the same MCX 1-hour long-trend effect as H1.12L, with a stricter entry.

## Overfitting risks
- 34 configurations per market and side were screened. The DEV-best choice is itself a selection, so DEV numbers are inflated.
- The data-driven weights are fitted on 3–6 months of DEV. For stocks they encoded a single crash-and-rebound episode.
- VALID was already seen in earlier programs. A positive VALID here is not independent evidence.
- MCX BUY results sit in a 2025–26 metals uptrend, and random MCX longs were already positive in DEV.

## Data blockers
- No fresh data after the windows yet:
  - MCX 5-minute data ends 2026-11-03 (see DATA_PIPELINE.md: one Angel workflow run is needed);
  - NSE ends 2026-11-06 (it updates automatically).
- No OI for MCX intraday.
- FINNIFTY's 1h file is missing.

## Verdict
- **No new winning strategy.**
- Weighted scoring did not improve on equal weights or the best single indicator in a consistent way.
- Its only clear gain (stock BUY) is a one-month market-timing artifact.
- The one robust-looking result (MCX 1h BUY score) duplicates H1.12L. It merits forward validation only **alongside H1.12L**, as a variant, once fresh MCX data arrives. It is not a separate candidate.

**Reproduce:** `python research/mcxe009/weighted.py && python research/mcxe009/controls9.py`

## Owner decision, 7-Nov: H1.12L as EXPERIMENTAL live alerts
- Implemented on branch `feat/h112l-experimental` (commit d7267bd) and opened as **PR #50** for owner review. **Not merged**, so production is unchanged.
- The rule is labelled 🧪 EXPERIMENTAL / NOT VALIDATED in every message.
- S4 files are untouched. Existing rules and breakout signals are verified identical to bc3153e6.
- Experimental calls use their own ledger category, so they never block existing calls and stay out of the scorecard.
- **7-Nov, owner: "Do active". PR #50 merged into `main` as 567805d.** H1.12L EXPERIMENTAL alerts are live from the next market-loop run (Mon 9-Nov).
- Checks on the merged `main`, all passing:
  - the 11 H1.12L checks;
  - the 71 alert and 71 trade-plan checks;
  - the rulebook tests;
  - the 6 S4 preservation tests (PETRONET / GLENMARK / TITAN files byte-identical).

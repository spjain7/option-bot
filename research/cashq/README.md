# CASHQ – NSE cash-equity research engine (research only)

Branch `exp/cash-equity-engine` (from `exp/strategy-program-001`). No alerts, no orders, no imports into production.

## Modules
`data.py` (bhavcopy panel, PIT universe, weekly bars, 5-min loader + split adjust + complete-bar resampling) ·
`ind.py` (RSI, ATR, ADX, EMA, MACD-hist, Stoch, W%R, CCI, MFI, OBV, CMF, RVOL, candles) · `div.py` (regular / hidden
divergence with swing-break confirmation, no look-ahead) · `sim.py` (numba simulator: next-bar entry, stop-first, gap fills,
locked-bar no-fill, time / trail / square-off exits, long & short) · `engine.py` (ledgers, costs) · `validate.py` (splits,
metrics, day-block bootstrap CI, BH-FDR, promotion gate) · runners `daily_run`, `weekly_run`, `intra_run`, `oi_run`,
`robust`, `walkforward`, `report`. Tests: `python -m research.cashq.tests.test_engine` (12 checks).

## Protocol
Daily: DEV 2005-14 · VALID 2015-19 · OOS 2020-26 (⚠ 2016-26 was looked at in earlier EQ research, so the OOS is not fully
virgin for the momentum / 52-week-high families). Intraday: DEV 2024-10…2025-09 · VALID 2025-10…2026-03 · OOS 2026-04…11.
OI: DEV 2018-21 · VALID 2022-23 · OOS 2024-26. A variant is SELECTED only on DEV + VALID; the OOS then decides (gate in
`validate.verdict`). Costs: delivery 0.393 %, intraday 0.163 % round trip (Angel schedule + slippage); 2x / 3x tested.

## Results (10-Nov-2026) – 2,001 variants, 25.2 M simulated trade records (overlapping across exit variants)
| engine | variants | PASS | finding |
|---|---|---|---|
| intraday 5/15/30/60 min, long + short (I1-I13 incl. full-confluence ablations; + 2x / 3x ATR stop follow-up) | 1,680 | 0 | gross edge up to +0.18R (5-min short confluence, all 3 periods) but costs 0.15-0.52R per trade -> negative everywhere |
| daily swing ≤ 20 sessions: RSI (10), divergence (12 incl. hidden + grouped), volume (6), price action (10), combos (14) × 5 exits | 260 | 0 | gross ≈ 0 (−0.06…+0.06R) vs costs 0.05-0.08R |
| F&O exact-contract OI (LB / SC / SB / LU, aggregate, combos) | 33 | 0 | 2024-26 OOS negative in every variant |
| **positional trend (daily)**: 52-week-high breakout + EMA50 trail; RS top-10 % 50-day breakout + trail | 10 | **3** | OOS +0.18…+0.34R/trade, PF 1.37-1.71 |
| **positional trend (weekly)**: 10-week Donchian + weekly EMA10 trail; weekly EMA10 pullback | 18 | **2** | OOS +0.14…+0.25R/trade |

### Why the PASSes are NOT a green light
* VALID 2015-19 only +0.03…+0.13R; positive in just 10-12 of 21 years; profits come in bull bursts (2020 +1.5R, 2023 +1.2R)
  and 2024 was negative.
* Capital-constrained portfolio (10 slots, 2020-26): 19.6 % (52-week high) / 23.4 % (RS breakout) CAGR, max DD −41 % / −47 %
  vs the equal-weight eligible universe 17.7 % / −41 % – only a small edge over simply holding the universe, same drawdown.
* Robust to parameters (all 45 neighbours positive OOS, still positive at 3x costs) – but the same is true of the regime:
  it is a trend / bull-market premium. The existing monthly relative-strength portfolio (cashstock/, OOS 23.9 % CAGR,
  DD −20.6 %) remains the better cash strategy.
* Independent re-implementation (plain Python, no engine code) of the F1 ledger: 785 / 785 closed trades identical.

Status: **research PASS, not promoted**. Next step would be a forward shadow (no Telegram) of F1 / F2 next to cashstock.

## Blocked / missing
Delivery quantity / %: not in our bhavcopy files (delivery strategies not tested) · sector map / sector indices: not
available (sector-strength tests not run) · intraday history only ~2 years and only today's 218 liquid stocks
(survivorship bias) · NIFTY index history: EW top-100 proxy used.

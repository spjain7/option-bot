# MCXE-009 weighted indicator scoring: method (exploratory, research only)

**Code:** `research/mcxe009/weighted.py` (screen), `controls9.py` (controls).

**Data:** DEV + VALID of the approved MCXE-004 windows only.
- OOS is masked in the engine and was never read.
- VALID is **not fresh** (MCXE-005/006/007 already used it), so every number here is exploratory.

## Indicators available and reused (no new indicators written)
- `crude/indicators.py`: EMA, RSI, ATR, ADX, true range, volume ratio, pivots.
- Inline, as in MCXE-005 `signals.py`: MACD, DI+/DI−, Bollinger Bands, Donchian channel.
- Frame columns: ATR, volume, exchange OI change (`doi`, NSE futures daily only), VWAP (intraday frames, not used).
- Candle-pattern detectors (`research/mcxe003`) were not needed. The candle-body score covers direction.

## Score normalization (each component in [−1, +1]; causal; NaN never filled)

| Component | Definition | Meaning |
|---|---|---|
| ema | clip((EMA20 − EMA50) / ATR) | trend |
| price | clip((close − EMA50) / 2 ATR) | trend |
| adx | (DI+ − DI−) / (DI+ + DI−) × min(ADX / 25, 1) | directional trend strength |
| macd | clip(MACD histogram / 0.5 ATR) | momentum |
| rsi | clip((RSI14 − 50) / 25) | momentum |
| rsirev | −clip((RSI14 − 50) / 20) only if RSI > 70 or < 30, else 0 | reversal |
| bb | clip((close − SMA20) / 2 sd) | band position |
| brk | +1 / −1 beyond the prior 20-bar high / low, else 0.5 × channel position | breakout |
| vol | sign(close − open) × clip(volume / avg20 − 1, 0, 1) | directional participation |
| candle | (close − open) / (high − low) | body direction |
| oi | sign(close change) × clip(OI change / 5 %) | build-up (futures daily only) |

**Model score:** Σ wᵢsᵢ / Σ|wᵢ|, taken over the components that are available at that bar. Missing OI or volume is dropped from the score, not set to zero.

**Signals**
- BUY when the score crosses above +θ; SELL when it crosses below −θ; θ ∈ {0.4, 0.6}. Between the thresholds there is no trade (neutral).
- **Exit (identical for every model):** 2-ATR stop, 4-ATR trailing stop, time cap (1h: 240 bars; 4h: 120; daily: 40).
- Entry at the next bar's open; stop checked first; gap fills at the open; forced exit before a contract roll.
- **Costs:** MCXE-003 cost model, also at 2×.

## Weighting families tested
1. **Equal:** all 11 components weight 1.
2. **Trend-heavy:** ema 3, price 2, adx 2, macd 1, others 0.5.
3. **Momentum-heavy:** macd 3, rsi 3, candle 1, bb 1, others 0.5.
4. **Breakout / volume-heavy:** brk 3, vol 2, oi 2, bb 1, others 0.5.
5. **RSI-reversal-heavy:** rsirev 3, candle 1, ema / price / adx 0.5.
6. **Data-driven:** weight = Spearman information coefficient of each component vs the forward 10- or 20-bar return / ATR, fitted on **DEV bars only** (with the forward window also inside DEV). Weights are in `results_weights.json`.

**Also run with the same exits:**
- each component alone (11 single-indicator models);
- the Donchian-20 breakout baseline.

## Markets
MCX 1h, 4h and daily (7 commodities); stock futures daily (209 point-in-time symbols); index futures daily (5) and 1h (4; FINNIFTY's 1h file is missing).

## Selection (pre-stated; VALID never used for choosing)
- For each market and side, pick the model and θ with the best **DEV** 2× expectancy.
- Minimum DEV sample: ≥ 30 trades on ≥ 20 dates (1h / 4h); ≥ 20 trades on ≥ 15 dates (daily).
- VALID was read once for the picks, then controls were run.

**Run size:** 6 markets × (6 families + 11 single models) × 2 θ × 2 sides + baselines = **420 rows** in RESULTS.csv.

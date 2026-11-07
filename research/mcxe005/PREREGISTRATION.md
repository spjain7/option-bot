# MCXE-005 pre-registration (written before any MCXE-005 result, 7-Nov-2026)

**Data.** Only the approved MCXE-004 one-year windows (`research/mcxe004/windows.json`). All loading goes through window
clipping **before** any indicator is computed. The first 60 bars of each frame are warm-up and produce no signals.
DEV / VALID / OOS are the MCXE-004 splits (6 / 3 / 3 months).

The S4 regression fixture is the one exception. It uses F&O bhavcopy from 2025-09 to rebuild the three live signals
exactly as production saw them (EMA200 needs about 200 sessions). It serves only to understand and preserve existing
behaviour, never research evidence.

**Market cells:**

| Market cell | Data | Timeframes | Horizon / exit set |
|---|---|---|---|
| MCX (7 commodities) intraday | Angel 5-min, clipped, resampled | 15m, 30m | exit by the session's last bar |
| MCX positional | same 5-min data, resampled | 1h, 4h, 1d | max 20 bars, no hold across a contract switch |
| MCX overnight | same, daily | 1d | close → next open (BTST / STBT) |
| NSE cash intraday | Angel 5-min, 218 liquid names (survivorship noted) | 15m, 60m | exit by 15:15; no entries after 14:45 |
| NSE cash BTST / positional (BUY only, owner rule) | official bhavcopy, point-in-time, liquid universe computed inside the window | 1d | BTST close → next open; positional max 20 bars |
| NSE stock futures intraday | Angel 1-hour, today's list (survivorship noted) | 1h | exit at the session's last bar |
| NSE futures BTST / STBT / positional | point-in-time F&O bhavcopy, front month, roll-adjusted inside the window | 1d | BTST / STBT close → next open; positional max 20 bars, no hold across a roll |

**Families (both sides; cash BUY only):**
- **A trend / momentum:** EMA 9/21 cross, EMA 20/50 cross, MACD signal cross, MACD zero cross, RSI 50 cross,
  +DI/−DI cross with ADX ≥ 20, Supertrend(10, 3) flip, EMA50 slope turn.
- **B breakout:** 20-bar close breakout, 20-bar breakout with volume ≥ 1.5×, ATR breakout (close ≥ previous close + 1 ATR),
  NR7 breakout, compression (3 bars < 0.6 ATR) breakout, range-expansion bar, failed 20-bar breakout fade.
- **C reversal:** RSI 30/70 cross back, RSI divergence plus reversal candle, exhaustion fade (3 bars ≥ 1.5 ATR).
- **D patterns:** engulfing, hammer / shooting star, inside-bar breakout, double top / bottom, head & shoulders,
  trendline break with ≥ 3 touches. Detectors are the causal MCXE-003 ones, swing method f3.

**Filters (E):**
- **none:** base, no filter.
- **trend:** EMA50 > EMA200 and close > EMA50 for BUY, mirrored for SELL. Intraday frames use the previous session's
  daily trend.
- **adx20:** ADX(14) ≥ 20.
- **vol15:** volume ≥ 1.5× its 20-bar mean, using previous bars only.
- **volreg:** ATR(14) ≥ 0.8 × its 100-bar median, i.e. not a low-volatility regime.
- **trend+vol:** trend and vol15 together.

**Exits (2 per horizon, fixed):**
- **Intraday:**
  - X1: stop 1.5 ATR, target 2R, session-end exit;
  - X2: stop 1.0 ATR, no target, session-end exit.
- **Positional:**
  - X1: stop 2 ATR, target 3R, 20 bars;
  - X2: stop 1.5 ATR, 2.5-ATR trailing stop, 20 bars.
- **Overnight:**
  - X1: entry at the signal close, exit at the next open;
  - X2: entry at the signal close, exit at the next close.

**Execution and costs:**
- Signals are taken on completed bars and entered at the next bar's open (overnight: at the signal close).
- The stop is checked first; a gap through the stop fills at the open; one position at a time per instrument and cell.
- Costs: MCX statutory fees + 1.5 ticks/side; NSE cash intraday 0.163 %, delivery 0.393 %; NSE futures fees + 0.05 %/side.
  Every result is shown at 1× and 2×.

**Selection (DEV only):**
- A cell is (market horizon, timeframe, family, side, filter, exit), pooled over the market's instruments.
- To pass DEV, a cell needs:
  - DEV trades ≥ 40 on ≥ 25 dates;
  - DEV expectancy at 2× cost > 0;
  - one-sided day-clustered t-test, BH-FDR q < 0.10 over all cells of that market horizon.
- **VALID confirmation:** expectancy > 0 at both 1× and 2×, with ≥ 15 trades.
- The survivors are frozen and committed before OOS is computed. **OOS is run once.**

**OOS acceptance (MCXE-004 PROTOCOL §3–4, `register.classify`):**
- minimum OOS sample;
- expectancy > 0 at 1× and 2×;
- day-block / t conservative CI lower bound > 0.

A cell meeting all of these is classified **VALIDATED_CANDIDATE** only if both also hold:
- it beats a matched random-entry control (same instruments, period and execution);
- its logic was not selected using window data before.

Otherwise it is PAPER_ONLY. Nothing is promoted.

**Ablation (no selection):**
- Each filter is compared with its base (filter = none) on the same family, side and exit, over DEV + VALID.
- Reported: Δ expectancy, Δ win %, and trade retention (filtered trades / base trades).
- A filter "helps" only if Δ expectancy at 2× cost > 0 with a day-clustered paired CI above 0, and retention ≥ 30 %.

**S4 (live OI breakout) improvement study:**
- The S4 logic is copied into research. Production is untouched.
- The baseline is evaluated inside the futures window with daily bhavcopy OI.
- Variants, each against the identical baseline signal set:
  - ADX ≥ 20;
  - RSI < 75;
  - extension: close ≤ 20-day high + 1 ATR;
  - OI ≥ 4 %;
  - next-open entry-zone check.
- Variants are judged on DEV + VALID; OOS is shown once for the baseline and each variant, for information.

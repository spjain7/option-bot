# MCXE-004 next research priorities (in order; nothing below is started)

1. **Forward paper tracking of the two PAPER_ONLY rules** (stock 3h MACD-zero SELL, stock 3h EMA 9/21 SELL).
   - These are the only rules with an OOS CI above zero inside the window, but their selection overlapped it.
   - The live ledger already records their calls. Add their sent / rejected outcomes to the register weekly.
   - Pre-declared bar: ≥ 30 forward trades on ≥ 20 dates, expectancy at 2× cost > 0, block CI lower bound > 0.
2. **Fix data coverage** (needs owner approval: production change). 6-Nov: 22 of 60 scans RATE_LIMITED and 162 stock
   data failures. The OPS-RATE proposal (live-feed bars during NSE hours, history pre-fetched before 09:00) is the
   largest lever for "alerts not arriving".
3. **Attach window evidence to live calls** (needs owner approval: production change). Replace the multi-year backtest tier
   text with `register.alert_card` fields: validation status, OOS trades / dates / CI, data window.
4. **Research-parity ports for the BLOCKED live rules**: S4 OI breakout, S5 bearish engulfing, candle setups, stock 4h SELL.
   Without parity code they cannot be evaluated in the window; they are not failed, only untested.
5. **Pattern-as-overlay test** (MCXE-003 validation §E). Use the day-trend base rule inside the window, with paired
   comparisons on the same days. Expect INSUFFICIENT_DATA: OOS has only 48 trades on 20 dates.
6. **Retention of pipeline evidence** (production change, owner approval):
   - keep `delivery.json` per day instead of overwriting it;
   - export the daily funnel to a dated file, so rejections remain visible beyond 10 days.

Constraints carried forward:
- Only data inside the approved 1-year windows.
- Window results for rules selected on 2022-26 data are PAPER_ONLY at best.
- Nothing is promoted to production without forward evidence and owner approval.

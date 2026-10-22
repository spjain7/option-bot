# STOCK-SEARCH-001 (registered 22-Oct-2026, before running)
Goal: a rule that works on NSE stock futures (lot < 3000) after costs, chosen on the DESIGN period, confirmed on HOLD-OUT.
Data: Angel 1-hour stock-futures history (181 stocks, Jul-2022 → Oct-2026), daily candles built from it; NIFTY futures for
market regime / relative strength. Costs: brokerage + GST, STT, exchange, stamp, 0.03% slippage per side.
Design < 2024-07-01 · Hold-out ≥ 2024-07-01 (stocks were never used before in any experiment).
Candidates (textbook parameters, daily candles, next-open entries, ATR stops checked first, no trade across expiry):
 S1 rsi2_long        RSI(2) < 10, close > EMA200 → long; exit close > EMA5 or 10 days; stop 2.5 ATR
 S2 rsi2_both        S1 + mirror short (RSI(2) > 90, close < EMA200)
 S3 pullback_trend   close > EMA50 > EMA200, RSI(14) crosses up 40 → long (mirror short); exit close < EMA50; stop 2 ATR, target 3R
 S4 bb_long          close < lower Bollinger(20,2), close > EMA200 → long; exit close > SMA20; stop 2 ATR
 S5 high250_vol      close > 250-day high, volume > 1.5× avg → long; 2 ATR stop, 3 ATR trail
 S6 vb_market        live volume breakout + market filter: longs only if NIFTY > its EMA50, shorts only if below
 S7 vb_rs            S6 + relative strength: long only if the stock's 63-day return beats NIFTY's (short: lags it)
 S8 gap_go           gap up > 1% and close in the top 25% of the day's range → long next open (mirror short); stop 1.5 ATR, target 2R
 S9 nr7_trend        NR7 day in an EMA50 uptrend, break of its high → long (mirror short); stop 1.5 ATR, target 2R
 S10 momentum_top10  weekly portfolio: hold the 10 strongest stocks by 126-day return (above EMA200), equal weight
Shortlist (design): ≥ 100 trades, ≥ +0.10R, PF ≥ 1.20, bootstrap p5 > 0, > 0 at 2× costs.
PASS (hold-out, opened only for shortlisted): ≥ 100 trades, ≥ +0.05R, PF ≥ 1.10, > 0 at 2× costs.
S10 is judged on weekly portfolio return after costs vs an equal-weight all-stocks benchmark: PASS if the hold-out excess
return is > 0 and its Sharpe ratio beats the benchmark's.
Only PASS rules may be switched on for stock-futures alerts.

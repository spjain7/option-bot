# RSI-SELL-001 (registered 27-Oct-2026, before running) – option SELLING after hourly RSI extremes
User: "RSI above 80 hourly and below 25 hourly mostly win – add volume, OI and support/resistance confirmation".
Signal (closed 1-hour candle of the near-month future): RSI(14) > 80 → SELL CE ; RSI(14) < 25 → SELL PE.
One signal per instrument per day. Universes: INDEX (NIFTY, BANKNIFTY), MCX 7, STOCKS 181 (lot < 3000).
No option-price history exists in our data, so the test measures the UNDERLYING outcome that decides an option seller's
result: strike = signal close ± k × daily ATR(14) (k = 0.5, 1.0; CE above / PE below).
 hold H1 = to the next session close, H3 = 3 sessions, H5 = 5 sessions (≈ weekly expiry)
 WIN (expiry-style) = close at the end of the hold is on the safe side of the strike
 SAFE (strict)      = the strike is never touched during the hold (no stop-loss on the option)
Baseline = the same strike/hold measured on EVERY day at the same hour (no RSI condition) → shows whether RSI adds anything.
Filters (0–2 combined): vol (signal-candle volume > 1.5× – climax), oi (stocks/index: yesterday's OI pattern says the move
is weak: rally with OI falling = short covering for CE sells; fall with OI falling = long unwinding for PE sells),
sr (close within 0.5 daily ATR of the 20-day high for CE sells / 20-day low for PE sells = at resistance/support),
against (daily trend is against the RSI move: CE sell when yesterday's close < daily EMA50, PE sell when above).
Contract-switch / rollover days excluded. Design < 2024-07-01, hold-out after.
PASS (per universe, per rule): in BOTH periods n ≥ 60, WIN ≥ 80% and WIN ≥ baseline + 5 points.

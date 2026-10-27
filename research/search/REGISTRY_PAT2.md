# PAT-002 (registered 27-Oct-2026, before running) – patterns + volume + OI, ONE stop + ONE target, incl. weekly
User: find why patterns failed, add volume/OI, single target or SL, use support/resistance for SL/target, aim 80-90%;
also weekly / monthly positional setups for big targets.
Universes: MCX 7 + NIFTY/BANKNIFTY futures (3h, daily, weekly); STOCKS 181 futures (daily, weekly; stock costs; OI from
daily OI history). Weekly candles built from daily; trend filter on weekly = EMA50 (EMA200 needs 4 years of weeks).
Entries: breakout (20-candle close beyond high/low), flag, head & shoulders, double top/bottom, squeeze.
Filters: none / vol (signal volume > 1.5×) / trend (EMA200; weekly EMA50) / oi (stocks: signal-day OI ≥ +2% with price
in the trade direction = buildup) and pairs of them.
Exits (no trailing, conservative candle order, max hold 40 candles; weekly 26):
 SL  : A1.5 / A2 / A3 = ATR multiples, SW = structure (beyond the 10-candle swing low/high + 0.2 ATR)
 TGT : R0.5 / R1 / R2 / R3 / R5 multiples of the SL distance, SR = next resistance/support (60-candle extreme beyond
       entry, min 1R away; 2R if none)
Full costs; contract-switch / rollover handled as before. Design < 2024-07-01, hold-out after.
PASS: avg ₹/lot > 0 at 2× costs in BOTH periods, ≥ 40 trades per period (weekly ≥ 20), ≥ 60% of instruments positive
in the hold-out. Reported: win %, avg ₹/lot. "80-90%" is reported where it happens; it is not a pass condition.
Many combinations (~5 entries × 6 filters × 4 SL × 6 TGT × 3 TF) → a hold-out pass can still be luck; the best are
re-checked per year before any live use.

## RESULT (27-Oct-2026), avg ₹/lot at 2× costs design / hold-out, win % design / hold-out
MCX + index: 78 of 1,428 passed; STOCKS: 4 of 1,680 (weekly only, 0.5R targets, small samples) – stocks not used.
Chosen (live): 3h breakout+vol+EMA200 SL 2 ATR / T 2R: ₹1,407 / ₹10,605 · win 43% / 43% · 67% instruments
               daily same entry SL 1.5 ATR / T 3R: ₹18,291 / ₹39,092 · win 45% / 46% · 78% instruments
               weekly 20-week breakout SL 3 ATR / T 2R: ₹80,674 / ₹2,32,440 · win 50% / 51% · 20 / 41 trades (small)
Why patterns "failed": 3h flag / H&S are only marginally positive before Jul-2024 (₹500-2,400/lot – noise after costs);
most of their hold-out profit comes from the 2024-26 gold/silver trend. Volume / OI filters did not change that.
80-90% win rates appear only with 0.5R targets – and every one of those LOST money (e.g. daily breakout SL 1.5 ATR / T 0.5R:
77% / 70% wins, -₹10,185 per trade in the hold-out). No profitable 80-90% setup exists in this data.

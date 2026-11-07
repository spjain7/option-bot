# MCXE-010 audit: H1.12L + weighted indicators (research only; production untouched)

## Improvements made
1. **A fresh MCX data source was found (it corrects MCXE-009).**
   - The live loop **does** save candles: `scripts/market_loop.sh` exports 1-minute WebSocket bars (price, volume, **OI**) to branch `ws-bars` at the end of every job. MCXE-009 wrongly said the bot persists no candles.
   - MCX coverage is 30-Oct → 06-Nov for all 7 commodities. Full sessions exist on 4, 5 and 6 Nov (about 897 minutes each); on 2–3 Nov only from about 15:30, the known late loop start.
   - `ws_mcx.py` loads, de-duplicates and resamples these bars to 5 minutes and validates them against the Angel 5-minute store (`ws_validation.csv`):
     - timestamps are IST;
     - 87–96 % of 5-minute closes match exactly;
     - highs match only 64–94 %, because the websocket can miss some tick extremes.
2. **H1.12L forward tracking now runs** (`h112l_tracker.py --ws`; the default Angel-only replay is unchanged and still reproduces all 306 MCXE-006 trades).
   - Every forward row is tagged `data_source = ws (live bot WebSocket)`. This is a disclosed deviation from the protocol's Angel-only source.
   - **First forward result (4–6 Nov): 4 closed trades** (SILVER −1.01R, GOLD +0.21R, COPPER −1.03R, ALUMINIUM −1.07R): **−0.73R per trade, 1 of 4 won.** That is far too few to judge. Checkpoint 1 needs ≥ 30 trades on ≥ 20 dates.
3. **Live-alert execution was measured** (`exec_sim.py`, all 306 historical trades, 5-minute data):
   - Live entry (LTP about 2 min after the candle) costs **+0.02R** versus the research next-open fill. This is negligible.
   - Live stops are checked only every 15 minutes. **13 % of research-stopped trades survive** brief dips through the stop, so alert-based results average higher (+0.69R vs +0.47R at 2×) and vary by period (VALID +0.40 → +0.28R).
   - This is wick luck, not an edge. A trader with a real stop-loss order gets the research figures.
   - A first version of this simulation ignored the contract-roll exit, which inflated live results. Fixed, using the same roll cap as research.
4. **Filter trial-and-error** (`filters_h112l.py`, DEV + VALID only; VALID is not fresh, so these are hypotheses only):

   | Filter | DEV 2× | VALID 2× | Verdict |
   |---|---|---|---|
   | H1.12L baseline | +0.58R (157) | +0.40R (70) | — |
   | Equal-weight score ≥ 0.4 | +0.60R (136) | +0.56R (56) | Helps both, but the DEV gain is tiny. **Forward hypothesis only; not applied live.** |
   | Daily trend up | +0.69R | +0.28R | Flips between periods → rejected |
   | Indian hours / US hours | +0.45 / +0.81R | +0.57 / +0.10R | Flips between periods → rejected |
   | Equal score ≥ 0 | identical to baseline | — | All breakouts already score ≥ 0 |

5. **Test fix:** the shadow test's "no network code" check flagged the word "WebSocket" in a comment. It is narrowed to real socket use (`import socket` / `socket.`).

## Live H1.12L checks (no changes made)
- The rulebook needs at least 220 one-hour candles. The engine loads about 400 days of 1-hour history and removes the roll jump, so this is OK.
- Known live-vs-research differences, all disclosed in PR #50:
  - entry at the live price;
  - stops checked on 15-minute scans;
  - the research quirk (skipping BUYs while the untraded SELL leg was open) is not reproduced;
  - existing live calls take priority over H1.12L.

## Weighted indicators (MCXE-009) re-check
- There is no new standalone strategy. Its one usable output is the score ≥ 0.4 confirmation idea above.
- The stock data-driven score remains a one-month artifact (84 % of profit in March 2026).

## Remaining blockers
- Forward sample: 4 trades. About 6–8 more weeks of sessions are needed for checkpoint 1.
- WebSocket highs miss some extremes, so forward signals can differ slightly from Angel candles.
- Loop coverage gaps (2–3 Nov daytime) would also cost live alerts. Since 4 Nov, coverage is complete.

## Reproduce
```
python research/mcxe010/ws_mcx.py
python research/mcxe007/shadow/h112l_tracker.py --ws
python research/mcxe010/exec_sim.py
python research/mcxe010/filters_h112l.py
python research/mcxe007/tests/test_shadow_tracker.py
```

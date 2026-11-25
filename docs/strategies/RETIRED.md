# Retired strategies – do not re-propose (owner, 25-Nov-2026)

Owner's instruction: keep their calls in the record (ledger), but do not show them in scorecards / reports and do not
consider them again in strategy research or analysis. The list lives in code as `alerts/strategies.py: RETIRED`
(scorecard names) and `RETIRED_RULES` (rulebook ids); scorecards skip them automatically.

| Strategy | Live record before retirement |
|---|---|
| Stock daily hanging-man breakdown SELL (`STK_HANGMAN`) | 3 closed, 1 won, −0.5R |
| MCX 1-hour OI / volume breakout, experimental (`RB_MCX_1h_*_EXP`) | 9 closed, 2 won, −2.9R |
| Stock 4-hour breakdown SELL (`FH_STK_SELL`) | 7 closed, 0 won, −3.4R |
| Stock 3-hour MACD zero-cross SELL (`RB_STK_3h_MACD0_SELL`) | 5 closed, 0 won, −2.4R |
| Stock 3-hour EMA 9/21 SELL (`RB_STK_3h_EMA921_SELL`) | 4 closed, 1 won, −1.2R |
| MCX 3-hour EMA 13/48 BUY (`MCX_EMA1348`) | 1 closed, stop-loss |

Research rule: any new search must exclude these families / timeframes in these forms; a similar idea needs a clearly
different rule and the owner's go-ahead before it is tested.

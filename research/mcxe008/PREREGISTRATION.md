# MCXE-008 pre-registration (2026-11-07, before any MCXE-008 result)

**Scope:** new strategies only, for MCX daily, NSE stock futures and NSE index futures.
- PETRONET, GLENMARK, TITAN and S4 are established production strategies. They are **out of scope** and not re-tested.
- Research only; production untouched.

## Validation data
- **Fresh data only.** The approved windows' OOS periods were already read in MCXE-005, MCXE-006 and MCXE-007. They are not fresh, so **MCXE-008 never reads them**: OOS is masked in code.
- **Development:** DEV + VALID of the approved MCXE-004 windows.
- **Validation:** only on forward data after each window ends:

  | Market | Forward validation starts |
  |---|---|
  | NSE daily | 2026-11-09 |
  | NSE 1-hour | 2026-10-23 |
  | MCX | 2026-11-04 |

  It is run by `forward8.py` once the data stores are refreshed.
- **A candidate that passes DEV + VALID is "frozen for forward validation", not "qualified".**

## Small screen: 3 new hypotheses, not tested in MCXE-005, 006 or 007

| ID | Hypothesis | Market | Rule | Exit |
|---|---|---|---|---|
| N1 | Index futures trend intraday-to-positional, like the MCX 1-hour effect (H1.12) | Index futures 1h (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50; Angel stitched; window NSE_FUT_INTRADAY) | 1-hour close crosses the prior 20-bar high (BUY) / low (SELL) | 2-ATR stop, 4-ATR trail, 240-bar cap, exit before contract switch |
| N2 | Idiosyncratic breakouts continue once the market factor is removed (the hedge tightened CIs in MCXE-007) | Stock futures daily | Donchian-20 close breakout / breakdown with a beta-1 NIFTY hedge | X0 (2-ATR stop, 4-ATR trail, 40 days) |
| N3 | Breakaway gaps (opening beyond the 20-day level and holding through the close) start moves | MCX, stock futures, index futures daily | Open beyond the prior 20-day extreme by ≥ 0.25 ATR and close beyond the open → next open | X0 |

**Variants:** at most one one-change variant per hypothesis, and only if the baseline is close to the bar.

## Freeze bar (from MCXE-007)
- DEV and VALID each:
  - ≥ 20 trades on ≥ 15 dates (daily);
  - ≥ 30 trades on ≥ 20 dates (1-hour).
- 2× expectancy > 0 in both.
- DEV + VALID CI lower bound > 0.
- Expectancy without the top 5 trades ≥ 0.
- No instrument provides more than 50 % of net R.
- Beats the random-entry control (and the NIFTY same-date control for NSE).
- Long and short sides are judged separately.

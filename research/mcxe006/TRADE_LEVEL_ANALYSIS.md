# MCXE-006 trade-level analysis

**Sources**
- `results/trades_<id>.parquet` (DEV + VALID; git-ignored, reproducible with `lab.py`).
- `results/oos_trades_<id>.parquet`.
- `results/robustness_<id>.txt` (DEV + VALID).
- `results/trade_level_stats.txt`, `results/oos_results.json`.

## Where the profit comes from (frozen candidates)

| | H1.11 (4h, both sides) | H1.12L (1h, BUY) | H5.2L (1h RSI > 75, BUY) |
|---|---|---|---|
| Cost per trade (R) | 0.02 | 0.05 | 0.05 |
| Median hold (bars) | 10–17 | 15–20 | 11–26 |
| Median MFE, all trades (R) | 1.0–1.3 | 1.2–1.7 | 1.1–1.7 |
| Losers that first reached +1R | 24–31 % | 26–33 % | 25–34 % |
| Share of DEV + VALID net R from the best 5 trades | 63 % | 44 % | 61 % |
| DEV + VALID expectancy without the best 10 trades | +0.00R | +0.13R | −0.03R |
| DEV + VALID positive months | 6 / 9 | 8 / 9 | 7 / 9 |
| OOS by month (net R) | Aug +0.3, Sep +1.7, Oct +4.7 | Aug +32.5, Sep +0.7, Oct −4.9 | Aug +15.0, Sep −2.7, Oct −5.4 |
| OOS random-entry control (R per trade) | **+0.37** (beats the strategy) | +0.09 | +0.22 |

## Largest sources of loss and what was tried
1. **Initial-stop losses.** They are 47–55 % of OOS trades, at about −1.05R each including costs.
   - A tighter stop (more trades stopped) or a wider stop (3 ATR, H1.7) both lowered VALID.
   - The 2-ATR stop is a balance point, not an artefact.
2. **Give-back.** 25–34 % of losing trades first reached +1R.
   - Fixes tried: partial profit at 1R plus breakeven (H1.6), and a 2-ATR trail (H1.1).
   - Both raised the win rate but cut expectancy, because they also clipped the large winners that pay for the strategy. Not adopted.
3. **Counter-regime trades.**
   - H1.12L BUY trades in a "down" regime lost −0.85R in DEV + VALID.
   - The EMA alignment filter (H1.10) and ADX filter (H1.5) removed too many good trades and lowered VALID.
   - In OOS the "range" regime was the weak spot (−0.09R, 36 trades).
4. **Commodity dispersion.**
   - ALUMINIUM was negative in DEV, VALID and OOS for H1.12L, and NATURALGAS was mixed.
   - Dropping commodities after seeing these results would be selection on results, so it was not done. It is a pre-registered question for forward data.

## Other families: trade-level reasons for failure (DEV + VALID)
- **NSE cash ORB (H7):** 28,656 trades. Gross +0.015R vs cost 0.11R. 45 % stopped.
- **RSI(2) dip-buy (H4):** "signal" exits averaged +0.16R and stops −1.05R. One stop cancels about 6 winners.
- **Candle at support/resistance (H6):** structural stops are tight, so cost per trade is 0.04–0.08R. The DEV edge (+0.10R gross) became −0.2R in VALID.
- **Stock-futures trend (H3.5):** 1,500 trades. Gross −0.01R in DEV, −0.22R in VALID. The market was choppy, and breakouts failed on both sides.

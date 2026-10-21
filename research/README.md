# Full-universe research backtest (research / paper mode only)

Nothing here is used by the live bot. Live files (`runner.py`, `mcx_trade.py`, `config.py`, `bot.yml`, …) are unchanged.
Plan and pass/fail rules were fixed **before** results: [`CRITERIA.md`](CRITERIA.md). Script audit: [`AUDIT.md`](AUDIT.md).

## Run everything
```bash
pip install -r requirements.txt yfinance matplotlib
python -m research.adapters.nse_bhavcopy 2011-01-01      # REAL NSE index futures (≈25 min, one time)
python -m research.adapters.yahoo_proxy                  # PROXY data + USD/INR
# REAL MCX + index candles from Angel: GitHub → Actions → "Research data (manual, no alerts)" → Run workflow, then
git fetch origin research-data && git archive origin/research-data research/data/angel | tar -x
python -m research.tests.test_research                   # 16 integrity checks (look-ahead, gaps, rolls, costs, sizing)
python -m research.run_all                               # all groups → research/output/  (≈10 min)
python tests/simulate.py && python tests/sim_mcx_trade.py  # live-engine unit simulations (unchanged)
```

## Outputs (`research/output/`)
| File | Content |
|---|---|
| `PASS_FAIL.md`, `pass_fail.csv` | Grade of every group × strategy against the pre-registered criteria |
| `master_comparison.csv` | Every group × strategy × instrument × period (train / validation / OOS / full) × costs (before, 1×, 2×, 3×) |
| `trades/<group>/<strategy>/<instrument>.csv` | Trade logs: signal/entry/exit time, side, contract, entry/exit/stop price, R, rolls, costs, gross/net R, MAE/MFE, exit reason, ₹ per lot |
| `equity/daily/…`, `equity/hourly/…`, `equity/*.png` | Equity curves in R (per trade) and ₹ (portfolio) |
| `breakdowns/<group>_<strategy>.csv` | Long/short, instrument, yearly, monthly, ADX regime, volatility regime, 200-day trend, exit reason |
| `portfolio/…`, `portfolio_summary.csv` | Portfolio with ₹25 L capital, 2% risk/trade, max 6 positions, max 8% open risk |
| `sensitivity/…`, `walkforward/…` | Neighbour-parameter grid and anchored walk-forward picks |
| `daily_vs_hourly_comparable.csv` | Hourly A vs daily B/C on the same window and instruments |
| `unadjusted_series_bias_check.csv` | Same strategy on Angel's unadjusted vs our back-adjusted NIFTY/BANKNIFTY |
| `data_coverage.csv`, `run_config.json` | Data sources/grades/ranges; exact configuration, periods, costs, 843 variants run |

## Data actually available
- **NSE index futures – REAL**, contract-level daily OHLC/volume/OI from NSE bhavcopy: NIFTY & BANKNIFTY 2011→, FINNIFTY 2021→,
  MIDCPNIFTY 2022→ (thin: 155 untraded front-month days), NIFTYNXT50 2024→. Back-adjusted at our own roll dates.
- **MCX – REAL-UNADJ**, Angel One's vendor-stitched front-month series: daily 2006→ (Crude 2011→, Natural Gas 2016→),
  hourly 2022-07→. Real exchange prices, but **not back-adjusted** (roll jumps stay in). No MCX OI history (Angel does not serve it),
  so strategy F could not be tested on MCX. MCX's own bhavcopy blocks automated access.
- **PROXY**: Yahoo international futures (no zinc), and the NIFTY/BANKNIFTY cash index for hourly.
- No hourly data for FINNIFTY.

## Results (OOS, after costs) — see `output/PASS_FAIL.md`
- **No strategy reached PASS.**
- **A (live hourly MCX engine): FAIL everywhere** — MCX real −0.04 R/trade (531 trades), MCX proxy −0.02 R, index real −0.13 R,
  index proxy −0.07 R. It is slightly positive *before* costs on MCX; costs remove the edge. 0% of neighbour settings positive.
- **Index futures, daily (REAL, clean holdout 2021→): every strategy B–I FAILS.** C: −0.38 R/trade, PF 0.47 (99 trades);
  long-only I: −0.23 R. Validation 2017-20 was positive but both train and OOS were negative → no stable edge.
- **MCX daily: PAPER-CANDIDATE only** — C on proxy (+0.39 R, PF 1.53, 207 trades, boot p5 +0.017) and G on real-unadjusted
  (+1.12 R, PF 2.64, 79 trades, boot p5 +0.034). Caveats: all commodity periods were already seen; ~87% of C's real-data R comes
  from 5 long trades (Gold/Silver/Aluminium 2025-26 and 2007-11 rallies); **shorts lose in every period**; the unadjusted series
  inflates results (NIFTY check: C −0.15 R unadjusted vs −0.37 R adjusted); portfolio drawdowns at 2% risk/trade are 35-65%.

# MCXE-008 results: new-strategy screen (DEV + VALID only; used OOS never read; validation reserved for forward data)

**Outcome: no new strategy qualifies.**
- Nothing met the freeze bar, so nothing is frozen for forward validation.
- PETRONET, GLENMARK and TITAN (S4) were not touched or re-tested.
- Production is unchanged.

| ID | Hypothesis | Market | Side | DEV trades / 2× exp | VALID trades / 2× exp | DEV + VALID CI | Verdict |
|---|---|---|---|---|---|---|---|
| N1 | Index futures 1-hour Donchian-20 trend (MCX H1.12 effect in a new market) | NIFTY, BANKNIFTY, MIDCPNIFTY, NIFTYNXT50, 1h | BUY | 47 / −0.61R | 26 / −0.32R | [−0.84, +0.12] | Fail: gross already −0.42R; trends don't persist |
| N1 | | | SELL | 65 / −0.25R | 31 / −0.10R | [−0.53, +0.34] | Fail |
| N2 | Idiosyncratic breakout (beta-1 NIFTY hedge) | Stock futures daily | BUY | 507 / +0.07R | 322 / −0.20R | [−0.10, +0.11] | Fail in VALID |
| N2 | | | SELL | 486 / −0.14R | 271 / −0.17R | [−0.22, −0.01] | Fail |
| N3 | Breakaway gap beyond the 20-day level that holds | Stock futures daily | BUY | 41 / −0.03R | 35 / −0.08R | [−0.32, +0.26] | Fail |
| N3 | | | SELL | 80 / +0.37R | 32 / −0.41R | [−0.41, +0.74] | Regime flip |
| N3 | | MCX daily / index futures daily | both | 0–5 | 0–4 | — | Insufficient data |

**Costs:**
- Index futures: `research/instruments.cost_points` (fees + index slippage points), about 0.10R per trade on 1-hour stops.
- Stock futures: fees + 0.05 % per side, plus NIFTY hedge costs.
- MCX: MCXE-003 model.
- Every row is also shown at 2×.

**Data note:** the manifest lists a front-stitched FINNIFTY 1-hour file (`FINNIFTY27OCT26FUT_ONE_HOUR.csv`) that is not in the store. N1 therefore used 4 indices.

## Where this leaves the program
- Across MCXE-005 to MCXE-008, the only effect that held up across periods is MCX intraday-to-positional trend-following (MCXE-006 H1.12L).
- It is in research-only shadow tracking, which is blocked until MCX data after 2026-11-03 is available.
- Daily breakout and breakdown ideas for MCX, stock futures and index futures have been screened without a survivor inside the approved window.
- More screening on the same window would only add selection bias. **The next real test requires fresh data:**
  - NSE bhavcopy after 2026-11-06;
  - MCX after 2026-11-03.
- The research environment cannot download either. The network allowlist blocks NSE/MCX sites, and there are no broker credentials.

**Reproduce:** `python research/mcxe008/lab8.py run N1 N2 N3M N3S N3I` (register: `EXPERIMENT_REGISTER.csv`).

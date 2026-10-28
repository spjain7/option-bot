# Stock-futures data quality (STOCK-DQ-001, 28-Oct-2026)

These are data fixes only. The live Stock OI BUY / SELL rules (`stocks.CFG`) are unchanged: 20-day breakout, volume > 1.5×,
OI ≥ +2 %, EMA200, stop 2 ATR, trailing stop 3 ATR, next-open entry check, expiry exit. The bearish-engulfing SELL rule is
also unchanged.

| Check | What happens | Code |
|---|---|---|
| Corporate actions | Angel's continuous futures history is **not** adjusted. Verified splits and bonus issues are listed in `corporate_actions.json` (ratio, F&O ex-date, source link). A factor is applied only if the data shows the matching gap at the ex-date (within 8 %). If the data already looks adjusted, nothing is applied. Any other mismatch puts the stock on **hold**. | `dataquality.reconcile` |
| Demergers | No official futures price factor exists (NSE early-expired and re-listed the contracts). History before the ex-date is dropped, so the stock gives no signals until 205 post-event sessions exist. Factors are never estimated. | `reconcile` |
| Unexplained gap | A daily gap below ×0.72 or above ×1.35 with no verified event puts the stock on **hold**: signals are suppressed and the reason is logged (`[rejected] stock X: data hold – …`). Adding a verified entry (or `type: "market"` for a real price move) releases the hold. | `reconcile` |
| Open calls across a split / bonus | Entry, SL and target are rescaled once by the verified factor before any stop check. For a demerger, tracking stops with a message and no exit price is invented. | `stocks.rescale_for_corporate_actions` |
| OI validation (signal day) | Missing, non-numeric, non-finite, negative, zero-baseline or zero-today OI, or a corporate-action day, means the OI change **cannot confirm** a call. A **corrupt baseline** (yesterday's reading jumped ×3 or more and today is back within 10 % of the day before) is also rejected. | `dataquality.oi_check` |
| Genuine big OI changes | They are **not** rejected for their size. A change of +100 % or more, or −50 % or less, is only flagged. A difference from the live quote OI is also only flagged. | `oi_check` |
| Rollover window | Unchanged: no signal 3 sessions before to 2 sessions after expiry. | `stocks.in_rollover_window` |
| Logging | Blocked breakouts print `[rejected] stock X: breakout not confirmed – OI change not usable (<reason>)`. Holds are listed under `[stocks] data_holds`. | `run.py` |

## Shadow label: OI +2–4 % (research candidate E1; never changes a live call)
Every live OI-breakout BUY is written to `state.stk.shadow` with:
- signal candle and close, validated OI change and extension;
- the `band_2_4` label;
- planned entry, SL and risk, lot, and estimated round-trip cost (same model as the research);
- the first-scan entry LTP and time, and the cancel or exit price, time and reason;
- data flags, e.g. "no live quote OI to cross-check".

Baseline and label results come from the **same** signals. `shadow_summary` reports net R after costs for both. Prices
are scan LTPs, not broker fills. From 29-Oct-2026 this is the prospective record; thresholds are not tuned on it.

## Adding a corporate action
Add `{symbol, ex_date (F&O ex-date), type, ratio, price_factor (new/old price), source}` from the company or exchange
announcement. A demerger keeps `price_factor: null` unless the exchange publishes a futures price factor.

# MCXE-005 existing strategy analysis: the PETRONET, GLENMARK and TITAN trades

This is a read-only audit of `main` at bc3153e6. Nothing in production was changed.

## 1. The strategy that produced them

These three trades came from **S4, the stock-futures OI breakout** (`alerts/stocks.py`, ledger key `1dSTK`).

**Bars and BUY conditions**
- Daily candles are built from Angel 1-hour data.
- BUY needs all of the following:
  - close > 20-day high;
  - volume > 1.5 × the 20-day average;
  - price change > 0;
  - futures OI change ≥ +2 %;
  - close > EMA200.
- SELL is the exact mirror.

**Signal blocks**
- No signal from 3 sessions before expiry to 2 sessions after (the rollover window).

**Entry and activation**
- Entry = the signal close.
- At the next session the call becomes ACTIVE only if price is within 0.5 ATR past the entry and not 0.5 ATR against it. Otherwise it is cancelled (`validate_pending`).
- The check uses the first scan LTP after 09:16, not the official open.

**Exit**
- Stop at 2 ATR.
- 3-ATR trailing stop on daily closes.
- Exit on expiry day or after 40 sessions.

**Settings:** `CFG = dict(N=20, vol_x=1.5, oi_up=0.02, ema=200, stop_atr=2.0, trail_atr=3.0, max_days=40)`

## 2. The three trades

| | PETRONET | GLENMARK | TITAN |
|---|---|---|---|
| Signal | 2026-11-02 BUY | 2026-11-04 BUY | 2026-11-04 BUY |
| Entry / SL | 302.45 / 288.10 | 2508.7 / 2365.4 | 4744 / 4540.5 |
| OI change (production, Angel) | +2.42 % | +3.53 % | +5.49 % |
| Volume × 20-day average (bhavcopy) | 1.62 | 1.68 | 1.87 |
| Price change on signal day | +4.2 % | +4.6 % | +4.4 % |
| ADX / RSI at signal | 11.5 / 62 | 27.4 / 69 | 40.4 / 65 |
| Telegram | sent 2-Nov 17:02 IST | sent | sent |
| Outcome so far | **Cancelled** 4-Nov 15:49 IST at 311 ("opened 1.20 ATR past") | **ACTIVE**, fill 2510; 6-Nov close ≈ 2607 (+0.69R open) | **ACTIVE**, fill 4783.1; 6-Nov close ≈ 4992 (+1.0R open) |

**Why PETRONET was cancelled: an operational cause, not the rule**
- The 3-Nov official open was 304.9, or +0.36 ATR past entry. That is inside the 0.5-ATR zone, so the call should have activated.
- The scanner did not run during market hours on 2-Nov and 3-Nov. On 2-Nov the loop started at 16:25 IST; on 3-Nov it ran only at 16:15 and 22:19 IST.
- On 4-Nov the pending check kept being postponed with "live quote timestamp … in the future (max skew 60s)". By the time it ran, price was 1.20 ATR past entry, so the call was cancelled.
- A contradictory hanging-man SELL setup for PETRONET was also sent on 3-Nov.

**Data difference**
- Bhavcopy shows a PETRONET OI change of +1.88 %, below the 2 % rule. Production saw +2.42 % from Angel.
- So the PETRONET signal depends on the OI source. See DATA_QUALITY_AUDIT.md.

## 3. All recent forward S4 BUY signals (move measured from the official next open)

| Stock | Signal | Next open vs entry | Production status | Move to 6-Nov close |
|---|---|---|---|---|
| DIVISLAB | 30-Oct | +0.47 ATR | cancelled 4-Nov | +0.75R |
| ZYDUSLIFE | 30-Oct | +0.20 ATR | cancelled 4-Nov | −0.75R |
| PETRONET | 2-Nov | +0.36 ATR | cancelled 4-Nov | +0.85R |
| GLENMARK | 4-Nov | +0.32 ATR | active | +0.54R |
| TITAN | 4-Nov | +0.91 ATR (activated on the 09:26 LTP) | active | +0.74R |
| BAJFINANCE | 5-Nov | −0.58 ATR | cancelled (shadow / duplicate) | +0.58R |

- Three of the six cancellations were caused by scan timing or the clock-skew guard, not by the rule.
- The opposite also happens: TITAN opened outside the 0.5-ATR zone by the official open, but production activated it on a later LTP.
- So whether a call activates currently depends on when the scan happens to run.

**Live ledger, 28-Oct to 6-Nov**
- 24 calls in total.
- Closed calls with a real outcome: 6 (2 targets, 4 stops, 0R gross).
- 3 were withdrawn and 7 were cancelled on a gap.

## 4. How S4 performs inside the approved one-year window (research copy only; `s4_study.py`)

- **The exact rule (EMA200)** needs about 200 daily bars of warm-up, so inside the window it can only signal from about Sep-2026.
  - 27 signals, all in OOS.
  - 26 trades, win 50 %, expectancy −0.116R (2×: −0.143R), CI [−0.51, +0.28].
  - Not validated.
- **Research proxy (EMA50, otherwise identical)**, used because the exact rule has no DEV coverage:
  - DEV +0.72R (64 trades);
  - VALID −0.14R (81 trades);
  - OOS −0.11R (58 trades).
  - Strong in Nov-2025 to May-2026, negative after that.
- **Single-change variants:** +ADX ≥ 20, RSI < 75, extension ≤ 1 ATR, OI ≥ 4 %, entry-zone check off.
  - None is positive in both VALID and OOS at 2× cost with a CI above 0.
  - OI ≥ 4 % was closest (OOS +0.025R at 1×, −0.002R at 2×), which is not an improvement.
  - Turning the entry-zone check off made things slightly worse (OOS −0.147R), so the no-chase check is not the problem.

## 5. Conclusions

1. **S4 is preserved unchanged.** `tests/test_preservation.py` proves that production `evaluate` still emits BUY for PETRONET, GLENMARK and TITAN on the recorded bars, and that the S4 files on `main` are byte-identical.
2. **The rule's statistical edge is not established inside the one-year window.** The recent wins are consistent with a positive-drift period for breakouts. They are not proof of accuracy.
3. **The largest fixable issue is operational, not in the rule.**
   - The scanner was not running during market hours on 2-Nov and 3-Nov, and the clock-skew guard postponed checks on 4-Nov.
   - Activation is judged on whatever LTP the scan sees, not on the official open.
   - These are candidates for a reviewed production fix, which is **not** done here because production changes are prohibited by MCXE-005.

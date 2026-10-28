# OOS-VALIDATE-001 – independent validation of the live futures rules (28-Oct-2026)

Script `research/search/oos_validate.py` · all tables `results_oos/tables.md` · trades `results_oos/trades.csv.gz`.
Baseline = the live rules exactly (entries, ATR stops, R targets, live stop-width cap). No live setting was changed.

## Method
- Split: **train** < 1-Jul-2024 ≤ **validation** < 1-Jul-2025 ≤ **test** (to 20-Oct-2026). Stocks start Nov-2023 (short train).
- Next-bar-open entry; stop checked before target inside a bar; a gap through the stop fills at the open; costs incl.
  slippage at 1× and 2×; results in R (1R = stop distance).
- **Roll fix vs LIVE-AUDIT-001:** a trade open into a contract switch now exits at the old contract's last close (the old
  simulator used the new contract's close), and no entry is taken on a switch-day bar. Effect: S1 +0.123 → +0.144R,
  S2 +0.512 → +0.544R, S3 +0.245 → +0.204R per trade. The direction of the conclusions is unchanged.
- Uncertainty: 95 % bootstrap that resamples calendar months, because trades in the same month are correlated.
- One pre-registered parameter check: stop {1.5, 2, 2.5} ATR × target {1.5, 2, 3} R, picked on train only.

**Contamination (important):** the test period was already seen in aggregate (LIVE-AUDIT-001). The live exits of S1–S3
were chosen in earlier studies with 2024-26 visible. So the "test" period is **not untouched**. The only clean sample is
forward data from 29-Oct-2026.

## Results (live rules, 1× costs; per-trade mean R [95 % CI])

| Rule | Side | Train | Validation | Test |
|---|---|---|---|---|
| S1 3h breakout | BUY | +0.32 [+0.03, +0.56] n133 | +0.07 [−0.19, +0.33] n90 | +0.34 [+0.06, +0.66] n123 |
| | SELL | −0.14 [−0.41, +0.10] n97 | −0.10 [−0.80, +0.37] n58 | +0.16 [−0.36, +0.60] n60 |
| S2 daily breakout | BUY | +1.37 n19 | −0.10 n26 | +0.97 [+0.38, +1.43] n33 |
| | SELL | −0.31 n11 | +0.06 n7 | +0.53 n9 |
| S3 monthly breakout | BUY | +0.34 [+0.05, +0.67] n56 | +0.04 [−0.39, +0.43] n40 | +0.29 [−0.09, +0.65] n36 |
| | SELL | +0.23 n16 | −0.40 n5 | −0.19 n4 |
| S4 stock OI breakout | BUY | +0.14 [−0.09, +0.35] n185 | **−0.19** [−0.48, +0.01] n125 | **−0.17 [−0.34, −0.02]** n186 |
| | SELL | −0.11 n24 | +0.34 n41 | +0.19 [−0.14, +0.44] n84 |
| S5 stock bear engulf | SELL | +0.10 n50 | +0.02 n15 | +0.29 [+0.04, +0.51] n44 |

Win rates: mostly 35–60 % for the futures rules, with a few small cells up to 78 % (S2 SELL test, n9); S5 is 73 % in the test period (n44). **No rule reaches 80–90 %.**
Validation (Jul-24 → Jun-25) was flat or negative for **every** breakout rule. The edge depends on the period and is not
stable.

## Findings
1. **S1 3h:** BUY is positive in 2 of 3 periods. SELL is negative in train and validation and positive only in test
   (CI includes 0). SELL with NIFTY above EMA200 loses: −0.25R [−0.51, −0.02], n138. By instrument, BUY is strong on GOLD,
   ZINC, SILVER and COPPER and negative on NIFTY (n14). NATURALGAS gives no trades because every stop exceeds the 2.5 % cap.
2. **S2 daily:** strong in train and test, negative in validation. The samples are small (7–33 per cell), so the
   intervals are wide.
3. **S3 monthly:** BUY is positive in train and test, flat in validation. SELL has only 25 trades in total, too few to
   judge.
4. **S4 stock OI BUY fails out-of-sample:** −0.19R (validation) and −0.17R (test). The test interval excludes 0. 2026 is
   −0.31R (n96). The larger the OI jump, the worse the result (+2–4 %: +0.06R; >8 %: −0.18R). Market regime does not
   rescue it. S4 SELL is positive in validation and test, but its intervals include 0.
5. **Parameter check:** S2's train-best equals the live setting. For S1 (2.5 ATR) and S3 (3R), the train-best is a little
   better in validation and test, but the intervals overlap almost entirely. **No parameter change is supported.**
6. Many subgroups were examined, so a few intervals that exclude 0 are expected by chance. Single-cell results are leads,
   not proof.

## Changes that would need your approval (not made)
| # | Change | Evidence | Strength |
|---|---|---|---|
| 1 | Stop **stock OI BUY** calls (S4 BUY), or show them as "watch only" | negative in validation and test; test CI < 0 | moderate |
| 2 | Block **S1 SELL** when the instrument/market is above EMA200, or index/MCX SELL entirely | negative in 2 of 3 periods; one regime CI < 0 | weak–moderate |
| 3 | Drop **S3 SELL** | n = 25, negative recently | weak (too few trades) |
| 4 | S1 stop 2.5 ATR / S3 target 3R | train-selected, not confirmed beyond noise | not supported |
| 5 | Forward paper record of every call from 29-Oct-2026, judged after ≥ 30 trades per rule | the only clean test | recommended |

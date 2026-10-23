# BIG-MOVE-002 (registered 23-Oct-2026, before running) – big mover detected at ANY hour (user: moves start any time)
BIG-MOVE-001 result: 130 combos passed (cluster: first hour ≥ 3%, volume ≥ 2×, gap same way, RSI not extreme:
hold-out +0.22%/trade, 56% win, ~11 trades/month). Robustness check: profit came mostly from SELL trades and from
2024-H1 / 2026; 2024-H2 and 2025-H1 lost → treated as FRAGILE, not deployed yet.
This test: signal on ANY 1-hour candle that closes by 14:15 (no entries after 14:15). Condition: the move from the
day's open crosses M% (1.5/2/3) for the FIRST time that day on that candle, and that candle's volume ≥ V× normal (1.5/2/3).
Same filters as 001 plus "late" (signal after 11:15). Entry next candle open.
Exits: X1 day close · X2 stop = other end of the signal candle + day close · X3 X2 + trailing 1 ATR · X4 X2 + target 2R.
Same SHORTLIST/PASS rules as 001, plus a stability rule: PASS also needs ≥ 3 of the 5 hold-out half-years profitable.

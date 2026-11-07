"""MCXE-004 – register every live / shadow strategy and every requested market cell that could NOT be evaluated inside the
1-year window, with the exact reason (status BLOCKED or INSUFFICIENT_DATA; nothing is silently skipped).
python research/mcxe004/blocked_cells.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe004 import register as RG, window as W  # noqa: E402

CELLS = [
    # (script_id, strategy, market, instrument, timeframe, window key, status, reason)
    ("M-cashstock.run", "cash-mom-1.2 monthly relative-strength portfolio (LIVE, BUY-only)", "NSE_EQ", "liquid NSE cash", "monthly",
     "NSE_EQ", "BLOCKED", "the rule ranks stocks on 12-1 month returns and a 100-day market MA: its first signal needs 12 months "
     "of history, i.e. data older than the 1-year window -> cannot be evaluated without breaking the rule"),
    ("M-alerts.stocks", "S4 stock-futures OI breakout BUY / SELL (LIVE)", "NSE_FUT", "F&O stocks", "1d",
     "NSE_FUT", "BLOCKED", "no research-parity implementation of the live S4 rule exists in research code (it lives only in "
     "alerts/stocks.py); evaluating it needs a parity port first – NOT evaluated, not failed"),
    ("M-alerts.stocks", "S5 stock-futures bearish engulfing SELL (LIVE)", "NSE_FUT", "F&O stocks", "1d",
     "NSE_FUT", "BLOCKED", "same as S4: no research-parity code; NOT evaluated"),
    ("M-alerts.candle_setups", "candle setups: MCX daily hammer BUY / stock daily hanging-man SELL (LIVE)", "MCX+NSE_FUT", "MCX 7 + F&O stocks",
     "1d", "MCX", "BLOCKED", "no research-parity code for the live candle_setups module; NOT evaluated"),
    ("M-alerts.four_hour", "stock 4h SELL (Bollinger squeeze / MACD-zero, LIVE)", "NSE_FUT", "F&O stocks", "4h", "NSE_FUT_INTRADAY",
     "BLOCKED", "research code (stk_anchor.py) uses day-anchored 4h candles from the same Angel 1h files; not yet wired to the "
     "window harness – NOT evaluated"),
    ("M-alerts.engine", "index futures rules (NIFTY / BANKNIFTY daily, 3h; LIVE)", "INDEX", "NIFTY, BANKNIFTY", "3h/1d", "NSE_FUT",
     "BLOCKED", "index futures are outside the MCXE-004 market list (MCX, NSE cash, NSE stock futures) – listed for visibility"),
    ("M-runner", "option selling engine (LIVE)", "OPTIONS", "index / stock / MCX options", "intraday/positional", "NSE_FUT",
     "BLOCKED", "no historical option premiums inside the window -> no backtest possible; only the live record exists"),
    ("M-obuy.run", "option buying engine (OFF since 4-Nov via config.OBUY_ENABLED)", "OPTIONS", "stock options", "intraday", "NSE_FUT",
     "BLOCKED", "engine disabled in config; one month of real premiums (Sep-Oct 2026) only"),
    ("R-mcxe004", "NSE cash intraday – any live strategy", "NSE_EQ", "218 liquid stocks", "5m-60m", "NSE_EQ_INTRADAY",
     "BLOCKED", "no live or shadow strategy exists for NSE cash intraday (owner rule: cash is BUY-only; research found nothing) -> "
     "nothing to evaluate"),
    ("R-mcxe004", "NSE futures BTST / STBT – any live strategy", "NSE_FUT", "F&O stocks", "overnight", "NSE_FUT",
     "BLOCKED", "no live or shadow overnight (BTST/STBT) strategy exists -> nothing to evaluate"),
    ("R-mcxe004", "NSE cash BTST – any live strategy", "NSE_EQ", "liquid NSE cash", "overnight", "NSE_EQ",
     "BLOCKED", "no live or shadow BTST strategy exists -> nothing to evaluate; STBT in cash is not permitted (no overnight cash short)"),
]


def main():
    for sid, name, mk, inst, tf, wk, st, why in CELLS:
        w = W.get(wk)
        with RG.Execution(script_id=sid, strategy_name=name, market=mk, instrument=inst, timeframe=tf,
                          data_start_date=str(w["start"].date()), data_end_date=str(w["reference"].date())) as ex:
            ex.stage("eligibility check")
            ex.finish("BLOCKED" if st == "BLOCKED" else "INSUFFICIENT_DATA", validation_status=st, conclusion=why,
                      total_signals=None, executed_backtest_trades=None)
    print(len(CELLS), "blocked / not-evaluable cells registered")


if __name__ == "__main__":
    main()

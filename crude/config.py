"""Crude Oil PAPER engine settings. Independent of config.py (existing engines are not touched).

Everything here is a starting assumption chosen BEFORE looking at backtest results; it is not optimised.
"""
VERSION = "crude-paper 1.0.0"
MODE = "PAPER"                      # the only mode this package supports. There is no order code in crude/.
ENABLED = True                      # master switch for this engine only (scan mode does nothing when False)

SIGNAL_NAME = "CRUDEOIL"            # signals are computed on the liquid main contract
TRADE_NAME = "CRUDEOILM"            # paper fills + sizing on the mini contract (₹10/pt): 0.25% risk can't size a 100-bbl lot
RS_PER_POINT = {"CRUDEOIL": 100, "CRUDEOILM": 10}   # verified: lot 100 bbl / 10 bbl, price per bbl (cross-checked with master)
ROLL_TRADING_DAYS = 4               # switch to the next contract this many trading days before expiry
FLAT_BEFORE_EXPIRY_DAYS = 4         # positional trades are closed at the roll (never carried into expiry week)

CAPITAL = 500000.0                  # paper capital (₹)
RISK_PCT = 0.0025                   # 0.25% of capital per trade
DAILY_LOSS_PCT = 0.01               # per engine: no new entries that day once its realised+open loss reaches 1% of equity
MAX_OPEN = {"intraday": 1, "positional": 1}
# portfolio-level controls (both engines together). When a limit is breached NEW entries stop; open positions keep
# their own stop/target/exit rules (they are never force-closed by a limit, so a limit can't create extra slippage).
ACCOUNT_DAILY_LOSS_PCT = 0.015      # realised + open loss today, both engines
MAX_OPEN_RISK_PCT = 0.005           # sum of open initial risk across engines ≤ 0.5% of equity
DRAWDOWN_LOCK_PCT = 0.05            # equity (incl. open P&L) 5% below its peak -> entries locked until manually unlocked
                                    # (set state "dd_lock" to false on branch crude-state, see crude/RUNBOOK.md)
QUOTE_VS_CANDLE_MAX_ATR = 3.0       # live price further than this from the last closed candle -> data suspect, no entries
GAP_CHECK_BARS = 8                  # a missing 15-min candle inside the last 8 (same session) -> no entries
RUN_DELAY_WARN_MIN = 20             # scheduled run started this late -> warning (GitHub cron can be delayed)
MIN_RR = 1.5                        # reward:risk must be ≥ 1.5 to the nearest obstacle
COOLDOWN_BARS = {"intraday": 4, "positional": 2}   # no new entry this many signal bars after an exit (same engine)

# costs (MCX non-agri futures, per side unless noted) – conservative
BROKERAGE_PER_ORDER = 20.0
CTT_SELL = 0.0001                   # commodity transaction tax 0.01% on sell value
EXCH_TXN = 0.000026                 # MCX transaction charge (approx, both sides)
SEBI_FEE = 0.000001                 # ₹10 per crore
STAMP_BUY = 0.00002                 # 0.002% on buy value
GST = 0.18                          # on brokerage + exchange + SEBI
SLIPPAGE_TICKS = 2                  # per side, in ticks (₹1 tick) – market-order assumption
COST_STRESS = (1.0, 2.0, 3.0)       # backtest sensitivity multipliers

# sessions (IST). MCX crude closes 23:30 when US is on daylight time, 23:55 otherwise.
SESSION_OPEN = "09:00"
FIRST_ENTRY = "09:30"               # skip the first two 15-min candles
LAST_ENTRY_BEFORE_CLOSE_MIN = 60    # no new intraday entries in the last hour
SQUARE_OFF_BEFORE_CLOSE_MIN = 15    # intraday positions closed 15 min before the close
POSITIONAL_BLOCKS = ("09:00", "12:00", "15:00", "18:00", "21:00")   # 3-hour candle starts (last block ends at close)

# data quality
STALE_15M_MIN = 25                  # latest closed 15-min candle older than this (in session) -> stale, no entries
STALE_QUOTE_MIN = 5                 # live quote older than this -> stale
CLOSE_GRACE_SEC = 60                # a candle counts as closed only 60 s after its end time

INTRA = dict(                       # 15-min entry + 1-hour trend
    ema_fast=20, ema_slow=50, ema_long=200, ema_long_min_bars=250,
    adx_len=14, adx_min=20.0,
    rsi_len=14, rsi_block_buy_below=25.0, rsi_block_sell_above=75.0,     # entry restrictions only, never reversal signals
    atr_len=14, breakout_bars=8, breakout_buffer_atr=0.10, close_pos_min=0.65, body_min=0.5,
    max_bar_atr=2.5, max_chase_atr=0.5, pullback_lookback=6, pullback_touch_atr=0.25,
    vol_slots=10, vol_slots_min=5, vol_min_x_breakout=1.3, vol_min_x_pullback=1.0,
    atr_regime_max=2.5, atr_regime_len=200,
    sl_swing_bars=4, sl_buffer_atr=0.10, sl_min_atr=1.0, sl_max_atr=2.5,
    target_r=2.0, breakeven_at_r=1.0, obstacle_bars_1h=20,
)
POS = dict(                         # completed 3-hour candles
    ema_fast=20, ema_slow=50, ema_long=200, ema_long_min_bars=220,
    adx_len=14, adx_min=20.0,
    rsi_len=14, rsi_block_buy_below=25.0, rsi_block_sell_above=75.0,
    atr_len=14, breakout_bars=5, breakout_buffer_atr=0.10, close_pos_min=0.6,
    max_bar_atr=3.0, max_chase_atr=0.75, pullback_lookback=4, pullback_touch_atr=0.3,
    vol_slots=10, vol_slots_min=5, vol_min_x=1.1, pivot=2,
    atr_regime_max=2.5, atr_regime_len=100,
    sl_buffer_atr=0.25, sl_min_atr=1.5, sl_max_atr=3.5,
    target_r=2.5, trail_after_r=1.0, trail_atr=3.0, exit_below_ema="ema_slow", max_hold_sessions=15,
    obstacle_bars=40,
)

# OI integrity. Angel serves NO historical OI for MCX (getOIData -> AB1012, verified 21-Oct-2026).
# Current OI comes from the live FULL quote (opnInterest). OI change is computed ONLY between this engine's own
# recorded snapshots of the SAME contract taken 10–40 min apart. Missing OI is never treated as zero.
OI_POLICY = "fallback"              # "fallback": evaluate without the OI filter, tag the signal oi=UNAVAILABLE
                                    # "require":  block entries whenever OI change is unavailable
OI_SNAPSHOT_GAP_MIN = (10, 40)
OI_MIN_CHANGE_PCT = 0.2             # |ΔOI| below this = "flat" (no classification)
OI_BLOCKS = {"BUY": ("Short buildup", "Long unwinding"), "SELL": ("Long buildup", "Short covering")}
MIN_DAY_VOLUME = {"signal": 500, "trade": 20}   # today's traded lots (quote tradeVolume) needed before an entry
VOLUME_POLICY = "block"             # volume missing -> block entries (volume confirmation is required)

TELEGRAM = dict(startup=True, eod=True, errors=True, signals=True, heartbeat=False)

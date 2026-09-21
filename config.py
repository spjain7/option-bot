"""OPTION-SELLING BOT + RSI ALERTS - all settings. Edit here only."""

# ═════════════ MASTER SWITCHES (kill switch) ═════════════
OPTION_ENGINE_ENABLED = True     # Engine A: option-selling calls + trade management
RSI_ENGINE_ENABLED    = True     # Engine B: independent 1-hour RSI extreme alerts
SELL_STYLE            = "NAKED"  # "NAKED"  = single CE or PE sell only (your choice)
                                 # "HEDGED" = spreads/iron condor (low margin, capped loss)
ALLOW_STRANGLE        = False    # NAKED + sideways market: False = no call; True = sell CE + PE together

# ═════════════ STRIKE CHOICE (NAKED) ═════════════
# Sell the NEAREST strike (most premium/decay) that is still at least SAFE_EM_DISTANCE x expected move away
# (keeps gamma risk out of HIGH) and whose delta is inside the band.
DELTA_BAND            = {"intraday": (0.18, 0.35), "weekly": (0.15, 0.30), "monthly": (0.15, 0.30)}
SAFE_EM_DISTANCE      = 0.6

# ═════════════ SUPPORT / RESISTANCE ═════════════
WALL_EM_RANGE         = 1.5      # look for OI support/resistance within 1.5 expected moves of price
WALL_MIN_SHARE        = 0.6      # a strike counts as a wall if its OI >= 60% of the biggest nearby OI

# ═════════════ ⚡ OI / VOLUME ACTIVITY ALERTS (futures) ═════════════
FLOW_ENABLED          = True
FLOW_VOL_SPIKE_X      = 2.0      # last-hour volume >= 2x the day's normal hourly pace
FLOW_MIN_OI_CHG       = {"index": 1.0, "stock": 2.0, "mcx": 1.5}   # % OI change in ~1 hour
FLOW_MIN_PX_CHG       = {"index": 0.25, "stock": 0.5, "mcx": 0.4}  # % price change in ~1 hour
FLOW_COOLDOWN_MIN     = 120      # same instrument not re-alerted within 2 hours
FLOW_MAX_PER_MSG      = 8
FLOW_STRIKE_IDEAS     = 3        # add a "best strike to sell" idea for the top N buildups

# ═════════════ 🚨 BIG-MOVE EARLY ALERTS (cannot predict – catches a big move as it starts) ═════════════
BIGMOVE_ENABLED       = True
FAST_MOVE_PCT         = {"index": 0.4, "stock": 1.2, "mcx": 0.8}   # % move within ~15 min
BREAKOUT_VOL_X        = 2.0      # new day high/low counts only with volume >= 2x normal pace + rising OI
BIGMOVE_COOLDOWN_MIN  = 60

# ═════════════ WHEN IS A CALL "CONFIDENT"? ═════════════
MIN_CONFIDENCE        = 70       # 0-100 score; below this -> no call
CONFIRM_CHECKS        = 2        # intraday: same direction on this many hourly checks in a row
MIN_PREMIUM_RS_PER_LOT = 1500    # skip if selling brings in less than this per lot
MIN_RR                = 1.0      # reward must be >= risk (target profit >= stop-loss loss)
SPOT_STOP_FRACTION    = 0.5      # also exit if price covers half the distance to your sold strike

# ═════════════ WHAT TO TRADE ═════════════
INTRADAY_UNDERLYINGS = ["NIFTY", "BANKNIFTY", "SENSEX"]   # hourly calls, nearest expiry
WEEKLY_UNDERLYINGS   = ["NIFTY", "SENSEX"]                # weekly-expiry positional
MONTHLY_UNDERLYINGS  = ["BANKNIFTY", "NIFTY"]             # monthly-expiry positional (index)
MONTHLY_STOCKS       = "AUTO"    # "AUTO" = scan ALL F&O stock futures, analyse the strongest AUTO_STOCK_PICKS
AUTO_STOCK_PICKS     = 15        #          (or give a list like ["RELIANCE", "SBIN"])
INTRADAY_STOCKS      = ["RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "INFY", "TCS", "AXISBANK",
                        "BHARTIARTL", "LT", "TATAMOTORS", "KOTAKBANK", "ITC", "BAJFINANCE", "MARUTI",
                        "SUNPHARMA", "HINDALCO", "TATASTEEL", "ADANIENT", "M&M", "HCLTECH"]  # hourly stock-option calls

# Angel "NSE" tokens of the spot indices (used for candles / spot price)
INDEX_TOKENS = {"NIFTY": "99926000", "BANKNIFTY": "99926009",
                "FINNIFTY": "99926037", "MIDCPNIFTY": "99926074", "SENSEX": "99919000"}
BSE_INDICES  = {"SENSEX"}        # spot on BSE, options/futures on BFO
VIX_TOKEN = "99926017"

# ═════════════ STRIKE SELECTION (by DELTA) ═════════════
# short = the option you SELL, hedge = the far OTM option you BUY (cuts margin ~70-80%)
DELTA = {
    "intraday":        {"short": 0.25, "hedge": 0.08, "condor_short": 0.20},
    "intraday_expiry": {"short": 0.15, "hedge": 0.05, "condor_short": 0.12},   # expiry day: high GAMMA
    "weekly":          {"short": 0.20, "hedge": 0.06, "condor_short": 0.16},
    "monthly":         {"short": 0.20, "hedge": 0.07, "condor_short": 0.16},
}
MIN_CREDIT_TO_WIDTH = 0.10      # skip if credit < 10% of spread width (poor reward)
MAX_BID_ASK_PCT     = 8.0       # skip strikes with bid-ask spread > 8% of price (illiquid)

# ═════════════ EXITS / MANAGEMENT ═════════════
RULES = {
    # target_pct: book profit when premium has fallen X%  | sl_pct: stop-loss when premium has risen Y% (NAKED)
    # sl_mult / adjust_delta: used only in HEDGED mode
    "intraday": {"target_pct": 35, "sl_pct": 35, "sl_mult": 2.0, "adjust_delta": 0.40},
    "weekly":   {"target_pct": 50, "sl_pct": 50, "sl_mult": 2.0, "adjust_delta": 0.35},
    "monthly":  {"target_pct": 50, "sl_pct": 50, "sl_mult": 2.0, "adjust_delta": 0.35},
}
INTRADAY_EXIT_TIME   = "15:10"
WEEKLY_EXIT_TIME     = "14:45"   # on expiry day (avoid expiry-day gamma)
MONTHLY_EXIT_DTE     = 3         # close monthly trades 3 days before expiry

# ═════════════ ENTRY WINDOWS / FILTERS ═════════════
INTRADAY_FIRST_SCAN  = "10:15"   # after first 1-hour candle closes
INTRADAY_LAST_ENTRY  = "14:20"
POSITIONAL_WINDOW    = ("14:40", "15:20")   # weekly/monthly entries late in the day
WEEKLY_MAX_DTE       = 7         # open weekly trade when expiry is <= 7 days away (and > 0)
MONTHLY_DTE_RANGE    = (15, 45)  # open monthly trade when 15-45 days to expiry
VIX_SPIKE_BLOCK_PCT  = 8.0       # no new shorts if India VIX up > 8% today (vega risk)
VIX_LOW_PCTILE       = 15        # VIX in bottom 15% of year -> no iron condors (cheap premium)
STOCK_MIN_IV_HV      = 1.10      # sell stock options only if IV >= 1.1 x 20-day realised vol
PCR_BULL, PCR_BEAR   = 1.2, 0.8
CHAIN_RANGE_PCT      = {"intraday": 0.06, "weekly": 0.06, "monthly": 0.12, "stock": 0.20}  # strikes loaded around spot
RISK_FREE            = 0.065

# ═════════════ VOLATILITY / GAMMA / LIQUIDITY ═════════════
# IV vs 20-day realised volatility (RV).  IV/RV <0.9 CHEAP (no selling) | <1.1 NORMAL | <1.5 EXPENSIVE | else EXTREME
IV_RV_CHEAP          = 0.90
GAMMA_BLOCK          = "HIGH"    # block trades at/above this gamma-risk level (naked selling: keep HIGH)
MIN_SHORT_OI         = 500       # min open interest (contracts) at the strike you sell
ADX_RANGE_BELOW      = 18        # ADX below this = RANGE market (trend ignored)

# ═════════════ EVENT RISK (add dates yourself: RBI, Fed, Budget, CPI, election results...) ═════════════
# No NEW trades on these dates; no new weekly/monthly trades the day before either.
EVENT_DATES = {
    # "2026-10-01": "RBI policy",
    # "2026-10-28": "US Fed (FOMC)",
}

# ═════════════ RISK LIMITS ═════════════
CAPITAL_RS           = 500000    # your trading capital
MAX_RISK_PER_TRADE   = 0.02      # 2% of capital max loss per trade -> suggested lots
MAX_OPEN_POSITIONS   = 10        # no new calls when this many are open (NSE + MCX together)
MAX_DAILY_LOSS_RS    = 15000     # no new calls today after this closed loss (per-lot basis)
COST_PER_ORDER_RS    = 40        # brokerage + STT + exchange + GST per order (approx.)
# Naked-sell margin estimate (% of contract value). Real margin is shown by Angel One before you sell.
MARGIN_PCT           = {"index": 0.12, "stock": 0.20, "mcx": 0.12}
MAX_CAPITAL_USE      = 0.50      # never suggest lots needing more than 50% of capital as margin

# ═════════════ MCX OPTION SELLING (commodity options on futures) ═════════════
MCX_OPTIONS_ENABLED  = True
MCX_UNDERLYINGS      = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "GOLDM", "SILVERM"]
MCX_FIRST_SCAN       = "10:00"   # after first 1-hour candle (09:00-10:00)
MCX_LAST_ENTRY       = "22:30"
MCX_INTRADAY_EXIT    = "23:00"
MCX_POSITIONAL_WINDOW = ("22:30", "23:15")
MCX_MIN_DTE          = 2         # skip option expiries closer than this
MCX_MONTHLY_DTE      = (7, 40)   # positional MCX trade when option expiry is 7-40 days away
MCX_MIN_SHORT_OI     = 50        # MCX strikes have lower OI than NSE
MCX_CHAIN_RANGE_PCT  = {"intraday": 0.25, "monthly": 0.30}   # commodities are volatile: load wide
# Rupees gained/lost per 1 point move, per lot (exchange contract size). Check with your broker.
MCX_RS_PER_POINT     = {"CRUDEOIL": 100, "CRUDEOILM": 10, "NATURALGAS": 1250, "NATGASMINI": 250,
                        "GOLD": 100, "GOLDM": 10, "SILVER": 30, "SILVERM": 5,
                        "COPPER": 2500, "ZINC": 5000, "ALUMINIUM": 5000}

# ═════════════ ENGINE B: RSI EXTREME ALERTS (independent - never affects option calls) ═════════════
RSI_PERIOD           = 14
RSI_OVERSOLD         = 20
RSI_OVERBOUGHT       = 80
RSI_ALERT_MODE       = "entry_and_continuation"   # "entry" | "every_hour" | "entry_and_continuation"
RSI_NSE              = ["NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX"]             # spot indices
RSI_MCX              = ["GOLD", "GOLDM", "SILVER", "SILVERM", "COPPER", "CRUDEOIL",
                        "NATURALGAS", "NATGASMINI", "ALUMINIUM", "ZINC"]         # near-month futures
RSI_SHOW_HISTORY     = True      # add past statistics after similar RSI extremes (info only)

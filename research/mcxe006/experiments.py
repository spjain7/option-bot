"""MCXE-006 experiment declarations. Each entry changes ONE component relative to its parent (see PREREGISTRATION.md).
Exit keys: tgt1R/pfrac/be (partial at tgt1R R, move stop to breakeven), tgtR (final target), trail (ATR), maxbars,
squareoff (minutes after midnight), overnight ('open'/'close')."""
EXPS = {}


def E(id, parent, fam, hyp, universe, tf, horizon, fn, params=None, exit=None, change="", **kw):
    EXPS[id] = dict(parent=parent, fam=fam, hyp=hyp, universe=universe, tf=tf, horizon=horizon, fn=fn, params=params or {},
                    exit=exit or {}, change=change, **kw)


# ── H1 MCX trend portfolio ──
H1 = "Commodity prices trend; a two-sided breakout portfolio with a wide trailing stop captures trends and cuts losers"
E("H1.0", "", "H1", H1, "MCX", 240, "positional", "donchian", dict(n=20, k=2.0), dict(trail=3.0, maxbars=60), "baseline 4h Donchian-20, 2ATR stop, 3ATR trail")
E("H1.0d", "", "H1", H1, "MCX", 1440, "positional", "donchian", dict(n=20, k=2.0), dict(trail=3.0, maxbars=40), "baseline daily")
E("H1.0h", "", "H1", H1, "MCX", 60, "positional", "donchian", dict(n=20, k=2.0), dict(trail=3.0, maxbars=120), "baseline 1h")

# ── H2 MCX intraday, cost-aware ──
H2 = "Intraday MCX moves have a small gross edge; structural (range / daily-ATR) stops make cost per R small enough"
E("H2.0", "", "H2", H2, "MCX", 15, "intraday", "orb", dict(mins=60, open_min=540, stop="other"), dict(squareoff=23 * 60), "baseline ORB-60 15m, stop other side, session exit")
E("H2.0p", "", "H2", H2, "MCX", 15, "intraday", "pdhl", dict(k=0.5, open_min=540), dict(squareoff=23 * 60), "baseline prev-day high/low breakout, 0.5 dATR stop")
E("H2.0v", "", "H2", H2, "MCX", 15, "intraday", "vwap_pullback", dict(k=0.5), dict(squareoff=23 * 60), "baseline VWAP pullback with daily trend")

# ── H3 NSE stock futures positional ──
H3 = "Stock trends continue after pullbacks; trade only with the market's side (breadth)"
E("H3.0", "", "H3", H3, "NSE_FUT_D", 1440, "positional", "ema_pullback", dict(fast=20, slow=50, k=2.0), dict(trail=3.0, maxbars=20), "baseline EMA20/50 pullback, 2ATR stop, 3ATR trail")
E("H3.0b", "", "H3", H3, "NSE_FUT_D", 1440, "positional", "bo_vol_oi", dict(n=20, vol_x=1.5, oi_min=0.0, k=2.0), dict(trail=3.0, maxbars=20), "baseline breakout+volume+OI build-up")
E("H3.0m", "", "H3", H3, "NSE_FUT_D", 1440, "positional", "macd_trend_pullback", dict(k=2.0), dict(trail=3.0, maxbars=20), "baseline MACD-hist turn in trend")

# ── H4 NSE cash daily pullback in uptrend ──
H4 = "Short-term oversold dips inside uptrends revert (liquidity-driven selling)"
E("H4.0", "", "H4", H4, "NSE_EQ_D", 1440, "positional", "rsi2_pullback", dict(th=10, trend_n=50, exit_ema=5, k=2.5), dict(maxbars=10), "baseline RSI2<10 above EMA50, exit close>EMA5 / 10d")

# ── H5 RSI reversal ──
H5 = "Extreme RSI readings mean-revert once momentum fades (cross back inside the band)"
E("H5.0", "", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(hi=75, lo=25), dict(tgtR=1.5, maxbars=24), "baseline MCX 1h RSI 75/25 cross-back, 1.5ATR stop, 1.5R target")
E("H5.0f", "", "H5", H5, "NSE_FUT_D", 1440, "positional", "rsi_rev", dict(hi=75, lo=25), dict(tgtR=1.5, maxbars=10), "baseline stock fut daily RSI 75/25")
E("H5.0e", "", "H5", H5, "NSE_EQ_D", 1440, "positional", "rsi_rev", dict(hi=75, lo=25), dict(tgtR=1.5, maxbars=10), "baseline cash daily RSI 75/25", side_only=1)

# ── H6 candle at support/resistance ──
H6 = "Rejection candles at tested support / resistance mark exhausted moves; structural stop beyond the wick"
E("H6.0", "", "H6", H6, "MCX", 240, "positional", "candle_sr", dict(near=0.5, n=20), dict(tgtR=2.0, maxbars=30), "baseline MCX 4h hammer/engulf at 20-bar S/R")
E("H6.0f", "", "H6", H6, "NSE_FUT_D", 1440, "positional", "candle_sr", dict(near=0.5, n=20), dict(tgtR=2.0, maxbars=10), "baseline stock fut daily")

# ── H7 NSE cash intraday ORB ──
H7 = "Opening-range breakouts in liquid stocks continue intraday; range stop keeps cost per R low"
E("H7.0", "", "H7", H7, "NSE_EQ_I", 15, "intraday", "orb", dict(mins=30, open_min=555, stop="other", last_entry=13 * 60), dict(squareoff=15 * 60 + 15), "baseline ORB-30 15m")

# ── H8 overnight ──
H8 = "Strong closes on volume carry over to the next open (BTST / STBT)"
E("H8.0", "", "H8", H8, "NSE_FUT_D", 1440, "overnight", "close_strength", dict(top=0.1, vol_x=1.5), dict(overnight="open"), "baseline stock fut close in top/bottom 10% + vol")
E("H8.0m", "", "H8", H8, "MCX", 1440, "overnight", "close_strength", dict(top=0.1, vol_x=1.5), dict(overnight="open"), "baseline MCX daily")

# H1 iterations (parent H1.0 unless stated)
P1 = dict(n=20, k=2.0); X1 = dict(trail=3.0, maxbars=60)
E("H1.1", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", P1, dict(X1, trail=2.0), "trail 3 -> 2 ATR (lock gains sooner)")
E("H1.2", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", P1, dict(X1, trail=4.0), "trail 3 -> 4 ATR (more room)")
E("H1.3", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", P1, dict(X1, maxbars=120), "time cap 60 -> 120 bars (let winners run)")
E("H1.4", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", dict(P1, n=40), X1, "breakout 20 -> 40 bars (fewer, bigger trends)")
E("H1.5", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", dict(P1, adx_min=20), X1, "ADX >= 20 trend-strength filter")
E("H1.6", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", P1, dict(X1, tgt1R=1.0, pfrac=0.5, be=True), "partial 50% at 1R + breakeven")
E("H1.7", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", dict(P1, k=3.0), X1, "initial stop 2 -> 3 ATR")
E("H1.8", "H1.0", "H1", H1, "MCX", 240, "positional", "ema_pullback", dict(fast=20, slow=50, k=2.0), X1, "entry: breakout -> EMA20 pullback continuation")
E("H1.9", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", dict(P1, regime_vol=(0.8, 3.0)), X1, "volatility regime: skip when ATR < 0.8x its 100-bar median")
E("H1.10", "H1.0", "H1", H1, "MCX", 240, "positional", "donchian", dict(P1, trend=100), X1, "trend alignment: EMA50 vs EMA100 must agree")
E("H1.11", "H1.2", "H1", H1, "MCX", 240, "positional", "donchian", P1, dict(trail=4.0, maxbars=120), "H1.2 + time cap 120 bars")
E("H1.12", "H1.0h", "H1", H1, "MCX", 60, "positional", "donchian", dict(n=20, k=2.0), dict(trail=4.0, maxbars=240), "1h: trail 4 ATR, cap 240 bars (same exit idea as H1.11)")
E("H1.13", "H1.0h", "H1", H1, "MCX", 60, "positional", "donchian", dict(n=40, k=2.0), dict(trail=3.0, maxbars=120), "1h: breakout 20 -> 40 bars (filters 1h noise)")

# H2 iterations
E("H2.1", "H2.0p", "H2", H2, "MCX", 15, "intraday", "pdhl", dict(k=0.5, open_min=540, dtrend=True), dict(squareoff=23 * 60), "only with the daily trend (EMA20/50 of prior sessions)")
E("H2.2", "H2.0", "H2", H2, "MCX", 15, "intraday", "orb", dict(mins=60, open_min=540, stop="other", dtrend_f=True), dict(squareoff=23 * 60), "ORB only with the daily trend")
E("H2.3", "H2.0p", "H2", H2, "MCX", 15, "intraday", "pdhl", dict(k=1.0, open_min=540), dict(squareoff=23 * 60), "stop 0.5 -> 1.0 daily ATR (cost per R halves)")
E("H2.4", "H2.0", "H2", H2, "MCX", 15, "intraday", "orb", dict(mins=480, open_min=540, stop="other", max_w=1.5, last_entry=21 * 60), dict(squareoff=23 * 60), "range = Indian hours 09:00-17:00, breakout in the US session")
E("H2.5", "H2.0", "H2", H2, "MCX", 15, "intraday", "orb", dict(mins=60, open_min=540, stop="other", last_entry=11 * 60), dict(squareoff=23 * 60), "ORB entries only until 11:00")
E("H2.6", "H2.1", "H2", H2, "MCX", 15, "intraday", "pdhl", dict(k=0.5, open_min=540, dtrend=True, last_entry=11 * 60), dict(squareoff=23 * 60), "H2.1 + entries only until 11:00")
E("H2.7", "H2.1", "H2", H2, "MCX", 15, "intraday", "pdhl", dict(k=0.5, open_min=540, dtrend=True), dict(squareoff=23 * 60, tgt1R=1.0, pfrac=0.5, be=True), "H2.1 + partial 50% at 1R, breakeven")
E("H2.8", "H2.5", "H2", H2, "MCX", 30, "intraday", "orb", dict(mins=60, open_min=540, stop="other", last_entry=11 * 60), dict(squareoff=23 * 60), "H2.5 on 30m bars (fewer false breaks)")

# H3 iterations
E("H3.1", "H3.0", "H3", H3, "NSE_FUT_D", 1440, "positional", "ema_pullback", dict(fast=20, slow=50, k=2.0, breadth="align"), dict(trail=3.0, maxbars=20), "market breadth decides the side")
E("H3.2", "H3.0b", "H3", H3, "NSE_FUT_D", 1440, "positional", "bo_vol_oi", dict(n=20, vol_x=1.5, oi_min=0.0, k=2.0, breadth="align"), dict(trail=3.0, maxbars=20), "breakout+vol+OI with market breadth side")
E("H3.3", "H3.0m", "H3", H3, "NSE_FUT_D", 1440, "positional", "macd_trend_pullback", dict(k=2.0, breadth="align"), dict(trail=3.0, maxbars=20), "MACD pullback with market breadth side")
E("H3.4", "H3.0", "H3", H3, "NSE_FUT_D", 1440, "positional", "ema_pullback", dict(fast=20, slow=50, k=2.0), dict(trail=4.0, maxbars=40), "exits: trail 4 ATR, cap 40 days (trend exits from H1)")
E("H3.5", "", "H3", H3, "NSE_FUT_D", 1440, "positional", "donchian", dict(n=20, k=2.0), dict(trail=4.0, maxbars=40), "port of H1.11 trend portfolio to stock futures (baseline)")
E("H3.6", "H3.5", "H3", H3, "NSE_FUT_D", 1440, "positional", "donchian", dict(n=20, k=2.0, breadth="align"), dict(trail=4.0, maxbars=40), "H3.5 + market breadth side")

# H4 iterations
P4 = dict(th=10, trend_n=50, exit_ema=5, k=2.5)
E("H4.1", "H4.0", "H4", H4, "NSE_EQ_D", 1440, "positional", "rsi2_pullback", dict(P4, breadth="align"), dict(maxbars=10), "buy dips only when market breadth > 50%")
E("H4.2", "H4.0", "H4", H4, "NSE_EQ_D", 1440, "positional", "rsi2_pullback", dict(P4, k=4.0), dict(maxbars=10), "stop 2.5 -> 4 ATR (catastrophe stop only)")
E("H4.3", "H4.0", "H4", H4, "NSE_EQ_D", 1440, "positional", "rsi2_pullback", dict(P4, th=5), dict(maxbars=10), "deeper oversold RSI2 < 5")
E("H4.4", "H4.0", "H4", H4, "NSE_EQ_D", 1440, "positional", "rsi2_pullback", dict(P4, breadth=(0.6, 0.0)), dict(maxbars=10), "buy dips only when breadth > 60% (strong market)")
E("H4.5", "", "H4", H4, "NSE_FUT_D", 1440, "positional", "rsi2_pullback", dict(P4, both=True), dict(maxbars=10), "baseline port to stock futures, both sides (lower costs, can short)")
E("H4.6", "H4.5", "H4", H4, "NSE_FUT_D", 1440, "positional", "rsi2_pullback", dict(P4, both=True, breadth="align"), dict(maxbars=10), "futures + breadth side")

# H5 iterations (MCX 1h parent H5.0)
P5 = dict(hi=75, lo=25); X5 = dict(tgtR=1.5, maxbars=24)
E("H5.1", "H5.0", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(P5, trend="with"), X5, "trend-aware: buy oversold only in uptrend (close>EMA100), sell overbought only in downtrend")
E("H5.2", "H5.0", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(P5, mode="momentum", k=2.0), dict(trail=4.0, maxbars=120), "RSI staying extreme = momentum: buy RSI crossing above 75, trend exits")
E("H5.3", "H5.0", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(P5, candle=True), X5, "reversal-candle confirmation (close beyond prior bar extreme)")
E("H5.4", "H5.0", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(hi=80, lo=20), X5, "bands 75/25 -> 80/20")
E("H5.5", "H5.0", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(P5, adx_max=20), X5, "range regime only (ADX < 20)")
E("H5.6", "H5.0", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(P5, exit_mid=True), dict(maxbars=24), "exit at RSI 50 instead of 1.5R target")
E("H5.7", "", "H5", H5, "MCX", 240, "positional", "rsi_div", dict(k=1.5), X5, "baseline RSI divergence MCX 4h")
E("H5.8", "H5.2", "H5", H5, "MCX", 240, "positional", "rsi_rev", dict(P5, mode="momentum", k=2.0), dict(trail=4.0, maxbars=120), "momentum RSI on 4h")

# H6 iterations
E("H6.1", "H6.0", "H6", H6, "MCX", 240, "positional", "candle_sr", dict(near=0.5, n=20, confirm=True), dict(tgtR=2.0, maxbars=30), "confirmation bar beyond the pattern extreme")
E("H6.2", "H6.0", "H6", H6, "MCX", 240, "positional", "candle_sr", dict(near=0.5, n=20, trend=100), dict(tgtR=2.0, maxbars=30), "only with the trend (support in uptrend / resistance in downtrend)")
E("H6.3", "", "H6", H6, "MCX", 240, "positional", "retest", dict(n=20, k=1.5, within=5), dict(trail=4.0, maxbars=120), "baseline breakout + retest, trend exits")
E("H6.4", "H6.0f", "H6", H6, "NSE_FUT_D", 1440, "positional", "candle_sr", dict(near=0.5, n=20, confirm=True), dict(tgtR=2.0, maxbars=10), "stock fut: confirmation bar")
E("H6.5", "H6.0f", "H6", H6, "NSE_FUT_D", 1440, "positional", "candle_sr", dict(near=0.5, n=20, breadth="align"), dict(tgtR=2.0, maxbars=10), "stock fut: market breadth side")
E("H6.6", "H6.0", "H6", H6, "MCX", 240, "positional", "candle_sr", dict(near=0.5, n=20), dict(trail=4.0, maxbars=120), "exit: 2R target -> 4ATR trail (let reversals become trends)")

# H9 hybrids / follow-ups
H9 = "Combine only complementary evidence: trend breakout + momentum, session breakout + trend + breadth"
E("H9.1", "H1.11", "H9", H9, "MCX", 240, "positional", "donchian", dict(n=20, k=2.0, rsi_conf=60), dict(trail=4.0, maxbars=120), "H1.11 + RSI14 > 60 momentum confirmation (< 40 for SELL)")
E("H9.2", "H1.12", "H9", H9, "MCX", 60, "positional", "donchian", dict(n=20, k=2.0, rsi_conf=60), dict(trail=4.0, maxbars=240), "H1.12 + RSI14 momentum confirmation")
E("H7.1", "H7.0", "H7", H7, "NSE_EQ_I", 15, "intraday", "orb", dict(mins=30, open_min=555, stop="other", last_entry=13 * 60, dtrend_f=True, breadth="align"), dict(squareoff=15 * 60 + 15), "ORB with daily trend + market breadth")
E("H7.2", "H7.0", "H7", H7, "NSE_EQ_I", 15, "intraday", "orb", dict(mins=60, open_min=555, stop="other", last_entry=13 * 60), dict(squareoff=15 * 60 + 15), "opening range 30 -> 60 minutes (wider stop, lower cost/R)")
E("H7.3", "", "H7", H7, "NSE_FUT_I", 60, "intraday", "pdhl", dict(k=0.5, open_min=555, last_entry=14 * 60, dtrend=True), dict(squareoff=15 * 60 + 15), "baseline stock fut 1h prev-day high/low breakout with daily trend")
E("H8.1", "H8.0m", "H8", H8, "MCX", 1440, "overnight", "close_strength", dict(top=0.15, vol_x=0, trend=True), dict(overnight="open"), "MCX: no volume filter, close strength with trend (more trades)")
E("H8.2", "H8.0", "H8", H8, "NSE_FUT_D", 1440, "overnight", "close_strength", dict(top=0.1, vol_x=1.5, breadth="align"), dict(overnight="open"), "stock fut BTST/STBT with market breadth side")
E("H8.3", "H8.0", "H8", H8, "NSE_FUT_D", 1440, "overnight", "close_strength", dict(top=0.1, vol_x=1.5, trend=True), dict(overnight="open"), "stock fut BTST/STBT only with the stock's trend")
E("H1.12L", "H1.12", "H1", H1, "MCX", 60, "positional", "donchian", dict(n=20, k=2.0), dict(trail=4.0, maxbars=240), "H1.12 BUY side only (SELL side < 0 in DEV)", side_only=1)
E("H5.2L", "H5.2", "H5", H5, "MCX", 60, "positional", "rsi_rev", dict(hi=75, lo=25, mode="momentum", k=2.0), dict(trail=4.0, maxbars=120), "H5.2 BUY side only (SELL side < 0 in DEV)", side_only=1)

# H10 cross-sectional, market-neutral (stock futures)
H10 = "Relative strength persists across stocks (momentum) / short-term extremes revert (reversal); long-short removes market direction"
E("H10.0", "", "H10", H10, "NSE_FUT_D", 1440, "positional", "xs_rank", dict(lookback=20, topn=10, mode="momentum"), dict(maxbars=5), "baseline weekly: long top-10 / short bottom-10 by 20d return, hold 5 days, 3ATR stop")
E("H10.1", "", "H10", H10, "NSE_FUT_D", 1440, "positional", "xs_rank", dict(lookback=5, topn=10, mode="reversal"), dict(maxbars=5), "baseline weekly short-term reversal: long 5d losers / short 5d winners")
E("H10.2", "H10.0", "H10", H10, "NSE_FUT_D", 1440, "positional", "xs_rank", dict(lookback=60, topn=10, mode="momentum"), dict(maxbars=5), "momentum lookback 20 -> 60 days")
E("H10.3", "H10.1", "H10", H10, "NSE_FUT_D", 1440, "positional", "xs_rank", dict(lookback=20, topn=10, mode="reversal"), dict(maxbars=5), "reversal lookback 5 -> 20 days")

"""MCXE-007 experiment declarations (pre-registered families, PREREGISTRATION.md). Each child changes ONE component vs
its parent. Every experiment runs BUY (/L) and SELL (/S) separately. Markets: MCX, STK (stock futures), IDX (index futures)."""
EXPS = {}
X0 = dict(k=2.0, trail=4.0, maxbars=40)        # MCXE-006 exit: 2 ATR stop, 4 ATR trail, 40 sessions
X1 = dict(k=2.0, tgtR=2.0, maxbars=10)         # fixed 2R target
X3 = dict(k=2.0, maxbars=5)                    # time stop 5 sessions
X4 = dict(k=2.0, tgt1R=1.5, pfrac=0.5, trail=4.0, maxbars=40)   # partial 50% at 1.5R


def E(id, parent, fam, hyp, market, fn, params=None, exit=None, change="", **kw):
    EXPS[id] = dict(parent=parent, fam=fam, hyp=hyp, market=market, fn=fn, params=params or {}, exit=exit or X0, change=change, **kw)


HA = "A: a close beyond the prior N-day extreme starts a move that persists (breakout / breakdown)"
for mk in ("MCX", "STK", "IDX"):
    p = mk[0]
    E(f"{p}A20", "", "A", HA, mk, "dc", dict(n=20), X0, "baseline: close-confirmed Donchian-20, next open, 2ATR stop, 4ATR trail, 40d")
    for n in (5, 10, 30, 50):
        E(f"{p}A{n}", f"{p}A20", "A", HA, mk, "dc", dict(n=n), X0, f"lookback 20 -> {n} days")
    E(f"{p}A20b", f"{p}A20", "A", HA, mk, "dc", dict(n=20, mode="breach"), X0, "intraday breach (stop order at the 20d level, next session) instead of close + next open")
    E(f"{p}A20u", f"{p}A20", "A", HA, mk, "dc", dict(n=20, buf=0.25), X0, "breakout buffer 0.25 ATR beyond the level")
    E(f"{p}A20g", f"{p}A20", "A", HA, mk, "dc", dict(n=20, chase=1.0), X0, "gap rule: cancel if the next open is > 1 ATR beyond the level (no chasing)")

# ── Stage 2 (parent = the market's A20 baseline unless stated) ──
HB = "B: breakouts in the direction of an established trend / market / relative strength continue more often"
HC = "C: a break out of volatility contraction (NR7 / NR4 / inside day / ATR squeeze) releases stored energy"
HD = "D: breakouts confirmed by participation (volume) and positioning (OI build-up vs covering) are more reliable"
HE = "E: breakouts that are retested hold; breakouts that fail trap traders and reverse"
HG = "G: exit structure (target / time / partial / swing stop) changes expectancy more than entry tweaks"
X2p = dict(swing=5)
for mk in ("MCX", "STK", "IDX"):
    p = mk[0]
    for fl in [["ema"], ["adx"], ["hhhl"]] + ([["mkt"], ["rs"]] if mk == "STK" else []) + ([["mkt"]] if mk == "IDX" else []):
        E(f"{p}B_{'_'.join(fl)}", f"{p}A20", "B", HB, mk, "dc", dict(n=20, filt=fl), X0, f"+ filter {fl}")
    for pat in ("nr7", "nr4", "inside", "atrc"):
        E(f"{p}C_{pat}", "", "C", HC, mk, "compress_brk", dict(pat=pat), X0, f"baseline: {pat} bar -> stop order beyond its range next session")
    E(f"{p}C_nr7s", f"{p}C_nr7", "C", HC, mk, "compress_brk", dict(pat="nr7", struct_stop=True), X0, "stop at the NR7 bar's opposite extreme (structural) instead of 2 ATR")
    E(f"{p}C_brk_nr7prev", f"{p}A20", "C", HC, mk, "dc", dict(n=20, filt=["nr7_prev"]), X0, "Donchian-20 only if an NR7 occurred in the 3 bars before")
    E(f"{p}D_vol", f"{p}A20", "D", HD, mk, "dc", dict(n=20, filt=["vol"]), X0, "+ volume > 1.5x 20d average")
    if mk != "MCX":
        E(f"{p}D_vol_oiup", f"{p}D_vol", "D", HD, mk, "dc", dict(n=20, filt=["vol", "oi_up"]), X0, "+ OI build-up (exchange OI of the same contract up)")
        E(f"{p}D_vol_oidn", f"{p}D_vol", "D", HD, mk, "dc", dict(n=20, filt=["vol", "oi_dn"]), X0, "+ OI down (covering / unwinding) instead")
    E(f"{p}E_retest", "", "E", HE, mk, "retest", dict(n=20, within=5), X0, "baseline: breakout, retest within 5 sessions, close back beyond -> next open")
    E(f"{p}E_failed", "", "E", HE, mk, "failed", dict(n=20, within=3), X0, "baseline: failed breakdown -> BUY / failed breakout -> SELL")
    E(f"{p}E_failed_t", f"{p}E_failed", "E", HE, mk, "failed", dict(n=20, within=3), X1, "failed-breakout exit: 2R target, 10 sessions (mean-reversion target)")
    E(f"{p}G_X1", f"{p}A20", "G", HG, mk, "dc", dict(n=20), X1, "exit: 2R target / 10 sessions instead of trail")
    E(f"{p}G_X3", f"{p}A20", "G", HG, mk, "dc", dict(n=20), X3, "exit: time stop 5 sessions")
    E(f"{p}G_X4", f"{p}A20", "G", HG, mk, "dc", dict(n=20), X4, "exit: partial 50% at 1.5R, rest 4ATR trail")
    E(f"{p}G_sw", f"{p}A20", "G", HG, mk, "dc", dict(n=20, swing=5), X0, "stop: swing low/high of last 5 sessions instead of 2 ATR")

# ── Stage 3: one-change iterations on stage-2 leads ──
E("SE_failed_oidn", "SE_failed", "E", HE, "STK", "failed", dict(n=20, within=3, filt=["oi_dn"]), X0, "reclaim day with OI falling (trapped side covering = fuel)")
E("SE_failed_oiup", "SE_failed", "E", HE, "STK", "failed", dict(n=20, within=3, filt=["oi_up"]), X0, "reclaim day with OI rising (new positions) instead")
E("SE_failed_mkt", "SE_failed", "E", HE, "STK", "failed", dict(n=20, within=3, filt=["mkt"]), X0, "only with the market trend (NIFTY EMA20/50)")
E("SE_failed_vol", "SE_failed", "E", HE, "STK", "failed", dict(n=20, within=3, filt=["vol"]), X0, "reclaim on volume > 1.5x")
E("SE_failed10", "SE_failed", "E", HE, "STK", "failed", dict(n=10, within=3), X0, "level: 20-day -> 10-day extreme (more events)")
E("SE_failed_w5", "SE_failed", "E", HE, "STK", "failed", dict(n=20, within=5), X0, "reclaim window 3 -> 5 sessions")
E("SE_failed_X3", "SE_failed", "E", HE, "STK", "failed", dict(n=20, within=3), X3, "exit: 5-session time stop (reversal edge is short-lived)")
E("SD_oidn", "SA20", "D", HD, "STK", "dc", dict(n=20, filt=["oi_dn"]), X0, "breakout/breakdown with OI falling (no volume filter; more trades)")
E("SD_oiup", "SA20", "D", HD, "STK", "dc", dict(n=20, filt=["oi_up"]), X0, "breakout/breakdown with OI rising")
E("SD_vol_oidn_X1", "SD_vol_oidn", "D", HD, "STK", "dc", dict(n=20, filt=["vol", "oi_dn"]), X1, "exit 2R target / 10 sessions")
E("MC_nr7s_ema", "MC_nr7s", "C", HC, "MCX", "compress_brk", dict(pat="nr7", struct_stop=True, filt=["ema"]), X0, "+ EMA20/50 trend alignment")
E("MC_nr4s", "MC_nr7s", "C", HC, "MCX", "compress_brk", dict(pat="nr4", struct_stop=True), X0, "NR7 -> NR4 (more events) with structural stop")
E("MC_insides", "MC_nr7s", "C", HC, "MCX", "compress_brk", dict(pat="inside", struct_stop=True), X0, "inside day with structural stop")
E("IC_nr4s", "IC_nr7s", "C", HC, "IDX", "compress_brk", dict(pat="nr4", struct_stop=True), X0, "NR4 with structural stop (more events)")
E("SC_nr7_X3", "SC_nr7", "C", HC, "STK", "compress_brk", dict(pat="nr7"), X3, "exit: 5-session time stop")
HH = "E-hedged: the failed-breakdown edge is stock-specific (beats random longs by ~0.3R); a beta-1 NIFTY hedge removes the market drift"
E("SE_failed_h", "SE_failed", "E", HH, "STK", "failed", dict(n=20, within=3), X0, "beta-1 NIFTY futures hedge (pair: stock vs index)", hedge=True)
E("SE_failed_oiup_h", "SE_failed_oiup", "E", HH, "STK", "failed", dict(n=20, within=3, filt=["oi_up"]), X0, "beta-1 NIFTY hedge", hedge=True)
E("SE_failed_X1h", "SE_failed_h", "E", HH, "STK", "failed", dict(n=20, within=3), X1, "hedged + 2R target / 10 sessions", hedge=True)
E("SE_failed_w5h", "SE_failed_h", "E", HH, "STK", "failed", dict(n=20, within=5), X0, "hedged + reclaim window 3 -> 5", hedge=True, side=1)
E("SE_failed_volh", "SE_failed_h", "E", HH, "STK", "failed", dict(n=20, within=3, filt=["vol"]), X0, "hedged + reclaim on volume > 1.5x", hedge=True, side=1)

"""
OPTION-SELLING SIGNAL BOT  (runs in the cloud every 15 min via GitHub Actions)

  INTRADAY  (hourly)  : 1-hour trend + futures OI buildup + PCR  -> hedged credit spread / iron condor
  WEEKLY    (daily)   : daily trend + OI + PCR + VIX             -> weekly-expiry spread / condor
  MONTHLY   (daily)   : same, monthly expiry, index + stocks (stocks only when IV > realised vol)
  MANAGE    (each run): target / stop-loss / delta-adjust / time-exit alerts for every open call
  REPORT    (15:35)   : market view + open positions + P&L (weekly summary on Friday)

python runner.py auto      # what GitHub runs - decides by clock what to do
python runner.py test      # login + send test message
python runner.py report    # force daily report now
python runner.py mcx       # MCX market view now (+ MCX scan if market open)
"""
import sys, traceback
import pandas as pd

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

import config as C
import market as M
import strategy as S
import notify
import rsi_alert                      # Engine B - separate module, shares only data + Telegram
from angel import Angel, load_master, now_ist
from positions import Store, check, _hm


def at(s):
    return now_ist().normalize() + _hm(s)


def rs(x):
    return f"₹{x:,.0f}"


# ─────────────── plain-language explanations ───────────────
def k_(x):
    return int(x) if float(x).is_integer() else x


def simple_why(td, bu, ch):
    bits = []
    if td:
        bits.append({"UPTREND": "price is trending UP", "DOWNTREND": "price is trending DOWN",
                     "RANGE": "price is moving sideways", "MIXED": "trend is unclear"}[td["regime"]])
    if bu:
        bits.append({"Long buildup": "fresh BUYING in futures", "Short buildup": "fresh SELLING in futures",
                     "Short covering": "sellers are exiting (weak rise)",
                     "Long unwinding": "buyers are exiting (weak fall)"}[bu["label"]])
    if ch and ch.get("pcr"):
        p = ch["pcr"]
        bits.append("many put sellers = support below" if p >= C.PCR_BULL else
                    "many call sellers = resistance above" if p <= C.PCR_BEAR else "option sellers balanced")
    if ch and ch.get("iv_label") in ("EXPENSIVE", "EXTREMELY EXPENSIVE"):
        bits.append("option premiums are rich (good for selling)")
    return ", ".join(bits)


def plain_entry(t, ch, why):
    sells = [l for l in t["legs"] if l["side"] == "SELL"]
    buys = [l for l in t["legs"] if l["side"] == "BUY"]
    lot, name = t["lot"], t["name"]
    if t["bias"] == "BULLISH":
        view = f"{name} will NOT fall below {k_(sells[0]['K'])}"
    elif t["bias"] == "BEARISH":
        view = f"{name} will NOT rise above {k_(sells[0]['K'])}"
    else:
        lo = min(l["K"] for l in sells); hi = max(l["K"] for l in sells)
        view = f"{name} will stay between {k_(lo)} and {k_(hi)}"
    L = ["📖 *In simple words*",
         f"• The bot expects {view} (now {t['spot_at_entry']:,.1f}) till expiry {pd.Timestamp(t['expiry']):%d %b}.",
         f"• You receive about {rs(t['credit'] * lot)} per lot today by selling the option(s)."]
    if buys:
        L.append(f"• The option you BUY is insurance: worst-case loss is capped at {rs(t['max_loss'] * lot)} per lot.")
    else:
        L.append("• ⚠️ No insurance leg (naked): loss is NOT capped – the stop-loss is a must.")
    L += [f"• Plan: take profit at +{rs(t['reward_rs'])}, cut loss at -{rs(t['risk_rs'])} – whichever comes first.",
          f"• Why: {why}." if why else "",
          f"• Chance this ends in profit ≈ {t['pop']}% (estimate – losses happen)."]
    return [x for x in L if x]


EXPLAIN = {
    "TARGET": "Most of the premium is already earned. Close the trade and lock the profit – "
              "holding longer adds risk for little extra money.",
    "SL": "The loss limit is reached. Close ALL legs now – do not wait for the market to come back.",
    "TIME": "Exit by time to avoid late-day / expiry-day sudden moves. Close ALL legs now, profit or loss.",
    "ADJUST": "Price is getting close to the strike you sold, so risk is rising fast. "
              "Either close this trade now, or shift the sold option further away (roll).",
}


# ─────────────── message formats ───────────────
def fmt_entry(t, ch, view, why=""):
    icon = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡"}[t["bias"]]
    ex = "MCX" if t.get("exch") == "MCX" else "NSE"
    L = [f"{icon} *SELL CALL #{t['id']}* – {t['name']} {t['strategy']} ({ex})",
         f"_{t['mode'].upper()} | Expiry {pd.Timestamp(t['expiry']):%d %b} ({t['dte']}d)_", ""]
    for l in t["legs"]:
        L.append(f"{'SELL' if l['side']=='SELL' else 'BUY '} {int(l['K']) if l['K'].is_integer() else l['K']} {l['typ']} "
                 f"@ *{l['entry']}*  (Δ {l['delta']:+.2f}, IV {l['iv']})")
    g = t["pos_greeks"]
    L += ["",
          f"Net credit: *{t['credit']}* pts = {rs(t['credit']*t['lot'])}/lot (costs ≈ {rs(t['costs_rs'])})",
          (f"Max loss: {rs(t['max_loss']*t['lot'])}/lot | Return on risk {t['rom_pct']}%" if t["max_loss"]
           else "Max loss: *UNLIMITED* (naked) – margin per broker"),
          f"Risk to SL {rs(t['risk_rs'])} | Reward to target {rs(t['reward_rs'])} | R:R 1:{t['rr']}",
          f"Breakeven: {', '.join(map(str, t['breakevens']))} | Prob. of profit ≈ {t['pop']}% (from delta, estimate)",
          f"Expected move ±{ch['exp_move']} | Short strike {t['strike_em']}× EM away | Gamma risk: *{t['gamma_risk']}*",
          f"IV {ch['atm_iv']} vs RV {ch['rv']:.1f} → *{ch['iv_label']}*" + (f" | Skew {ch['skew']:+} (puts richer)" if (ch['skew'] or 0) > 0
                                                                           else f" | Skew {ch['skew']:+} (calls richer)" if ch['skew'] else ""),
          f"Position Greeks/lot: Δ {g['delta']:+.1f}  Γ {g['gamma']:+.3f}  Θ {rs(g['theta'])}/day  V {g['vega']:+.1f}",
          f"Suggested lots: {t['lots']}",
          "",
          f"🎯 Book profit when {'premium' if not t['max_loss'] else 'spread'} ≤ *{t['target_val']}*",
          f"🛑 Stop-loss when {'premium' if not t['max_loss'] else 'spread'} ≥ *{t['sl_val']}*",
          f"⚖️ Adjust if short-leg |Δ| ≥ {t['adjust_delta']}",
          f"❌ Invalid if price closes beyond {', '.join(str(k_(l['K'])) for l in t['legs'] if l['side']=='SELL')} (sold strike)",
          "", *plain_entry(t, ch, why),
          "", "_Details:_ " + view,
          "_Estimates, not certainty. " + ("Place hedge (BUY) first, then SELL._" if t["max_loss"] else "Keep SL order at broker._")]
    return "\n".join(L)


def view_text(bias, score, trend_d, bu, ch, vix, ivr):
    parts = [f"{bias} (score {score:+.1f})"]
    if trend_d:
        parts.append(f"{trend_d['regime']} (ADX {trend_d['adx']}) price {trend_d['close']} vs EMA {trend_d['ema_fast']}/{trend_d['ema_slow']}")
    if bu:
        parts.append(f"Fut {bu['label']} (Px {bu['px_chg']:+}%, OI {bu['oi_chg']:+}%)")
    if ch:
        parts.append(f"PCR {ch['pcr']} | Put wall {ch['put_wall']:.0f} / Call wall {ch['call_wall']:.0f} | ATM IV {ch['atm_iv']}")
    if vix:
        parts.append(f"VIX {vix['vix']} ({vix['chg']:+}%, {vix['pctile']} pctile)")
    if ivr is not None:
        parts.append(f"IV Rank {ivr}")
    return " | ".join(parts)


# ─────────────── core engine ───────────────
class Bot:
    def __init__(self, api, master, store):
        self.api, self.master, self.st = api, master, store
        self._vix = None

    def vix(self):
        if self._vix is None:
            self._vix = M.vix_info(self.api)
        return self._vix

    def spot(self, name, exch="NFO", fut_token=None):
        if exch == "MCX":                                          # MCX options are on the future
            tok, seg = str(fut_token), "MCX"
        else:
            tok, seg = M.spot_token(self.master, name), "NSE"
        q = self.api.quotes({seg: [tok]}).get(str(tok), {}) if tok else {}
        self._fresh = True
        t = pd.to_datetime(q.get("exchFeedTime"), errors="coerce", dayfirst=True)
        live = (at("09:20"), at("15:30")) if exch == "NFO" else (at("09:05"), at("23:25"))
        if pd.notna(t) and live[0] <= now_ist() <= live[1] and now_ist() - t > pd.Timedelta(minutes=10):
            self._fresh = False                                    # stale quote -> no new signal
        return float(q.get("ltp") or 0), tok

    # ---------- risk gates (no-trade engine) ----------
    def blocked(self, mode):
        now = now_ist()
        today, tmrw = f"{now:%Y-%m-%d}", f"{now + pd.Timedelta(days=1):%Y-%m-%d}"
        if not C.OPTION_ENGINE_ENABLED:
            return "option engine disabled"
        if today in C.EVENT_DATES:
            return f"event day: {C.EVENT_DATES[today]}"
        if mode != "intraday" and tmrw in C.EVENT_DATES:
            return f"event tomorrow: {C.EVENT_DATES[tmrw]}"
        if len(self.st.s["positions"]) >= C.MAX_OPEN_POSITIONS:
            return "max open positions reached"
        lost = sum(c["pnl_rs_per_lot"] for c in self.st.s["closed"] if c["closed"].startswith(today))
        if lost <= -C.MAX_DAILY_LOSS_RS:
            return "daily loss limit hit"
        return None

    def candles(self, tok, interval, days, seg="NSE"):
        n = now_ist()
        d = self.api.candles(seg, tok, interval, n - pd.Timedelta(days=days), n)
        if d is None or d.empty:
            return None
        step = pd.Timedelta(hours=1) if interval == "ONE_HOUR" else pd.Timedelta(days=1)
        if interval == "ONE_HOUR":
            d = d[d["time"] + step <= n]          # closed candles only (daily: today's candle = close so far)
        return d.reset_index(drop=True)

    def market_open_today(self):
        tok = C.INDEX_TOKENS["NIFTY"]
        d = self.api.candles("NSE", tok, "FIFTEEN_MINUTE", now_ist() - pd.Timedelta(days=1), now_ist())
        return d is not None and not d.empty and d["time"].iloc[-1].normalize() == now_ist().normalize()

    # ---------- open a trade ----------
    def view(self, name, expiry, trend_interval, exch="NFO", stock=False, mode="intraday"):
        """Collect everything the option engine needs for one underlying (no RSI here)."""
        fut = M.near_future(self.master, name, "MCX", on_or_after=expiry) if exch == "MCX" else None
        if exch == "MCX" and fut is None:
            return None
        spot, tok = self.spot(name, exch, fut["token"] if fut else None)
        if not spot or not self._fresh:
            print(f"{name}: NO TRADE - missing/stale price data"); return None
        seg = "MCX" if exch == "MCX" else "NSE"
        is_hourly = trend_interval == "ONE_HOUR"
        cd = self.candles(tok, trend_interval, 25 if is_hourly else 200, seg)
        trend, td = M.trend_score(cd, 9, 21) if is_hourly else M.trend_score(cd, 20, 50)
        bu = M.futures_buildup(self.api, self.master, name, exch, fut)
        rng = C.MCX_CHAIN_RANGE_PCT.get(mode, 0.1) if exch == "MCX" else C.CHAIN_RANGE_PCT["stock" if stock else mode]
        ch = M.build_chain(self.api, self.master, name, expiry, spot, rng, exch)
        if not ch:
            print(f"{name}: no option chain"); return None
        ch["dte"] = M.dte(expiry)
        rv = M.hv20(cd if not is_hourly else self.candles(tok, "ONE_DAY", 60, seg))
        ch["iv_label"], ch["iv_rv"] = M.iv_label(ch["atm_iv"], rv)
        ch["rv"] = rv or 0.0
        bias, score = M.combine_bias(trend, bu, ch["pcr"])
        return {"spot": spot, "tok": tok, "fut": fut, "td": td, "bu": bu, "ch": ch, "rv": rv,
                "bias": bias, "score": score}

    def try_open(self, name, mode, expiry, trend_interval, stock=False, exch="NFO"):
        why = self.blocked(mode)
        if why:
            print(f"{name} {mode}: NO TRADE - {why}"); return
        v = self.view(name, expiry, trend_interval, exch, stock, mode)
        if not v:
            return
        spot, td, bu, ch, rv, bias, score = v["spot"], v["td"], v["bu"], v["ch"], v["rv"], v["bias"], v["score"]
        ivl, ivx = ch["iv_label"], ch["iv_rv"]
        if ivl == "CHEAP":
            print(f"{name}: NO TRADE - options CHEAP (IV {ch['atm_iv']} vs RV {rv:.1f})"); return
        vix = None if (stock or exch == "MCX") else self.vix()
        ivr = self.st.iv_rank(name, ch["atm_iv"])

        allow_condor = True
        if vix:
            if vix["chg"] > C.VIX_SPIKE_BLOCK_PCT:
                print(f"{name}: VIX spiking {vix['chg']}% - no new shorts"); return
            allow_condor = vix["pctile"] >= C.VIX_LOW_PCTILE
        if stock:
            if not ivx or ivx < C.STOCK_MIN_IV_HV:
                print(f"{name}: IV {ch['atm_iv']} not rich vs RV {rv}"); return
            if bias == "NEUTRAL":
                return                                   # stocks: directional spreads only

        m = mode
        if mode == "intraday" and M.dte(expiry) == 0:
            m = "intraday_expiry"
        t = S.build_trade(ch, bias, m, allow_condor)
        if not t:
            print(f"{name} {mode}: {bias} - no trade meets rules"); return
        order = ["LOW", "MEDIUM", "HIGH", "EXTREME"]
        if t["gamma_risk"] in order and order.index(t["gamma_risk"]) >= order.index(C.GAMMA_BLOCK):
            print(f"{name}: NO TRADE - gamma risk {t['gamma_risk']}"); return
        t.update({"name": name, "mode": mode, "expiry": str(pd.Timestamp(expiry).date()),
                  "dte": M.dte(expiry), "spot_at_entry": spot, "exch": exch,
                  "fut_token": str(v["fut"]["token"]) if v["fut"] else None,
                  "exit_time": C.MCX_INTRADAY_EXIT if exch == "MCX" else C.INTRADAY_EXIT_TIME})
        self.st.add(t)
        notify.send(fmt_entry(t, ch, view_text(bias, score, td, bu, ch, vix, ivr), simple_why(td, bu, ch)))

    # ---------- scans ----------
    def intraday_scan(self):
        now = now_ist()
        if not (at(C.INTRADAY_FIRST_SCAN) <= now <= at(C.INTRADAY_LAST_ENTRY)):
            return
        slot = now.normalize() + pd.Timedelta(hours=9, minutes=15) + \
            pd.Timedelta(hours=int((now - now.normalize() - pd.Timedelta(hours=9, minutes=15)) / pd.Timedelta(hours=1)))
        for name in C.INTRADAY_UNDERLYINGS:
            key = f"hourly|{name}|{slot:%Y-%m-%d %H:%M}"
            if self.st.done(key) or self.st.open_positions("intraday", name):
                continue
            self.st.mark(key)
            exps = M.expiries(self.master, name)
            if exps:
                self.try_open(name, "intraday", exps[0], "ONE_HOUR")

    def positional_scan(self):
        now = now_ist()
        if not (at(C.POSITIONAL_WINDOW[0]) <= now <= at(C.POSITIONAL_WINDOW[1])):
            return
        key = f"positional|{now:%Y-%m-%d}"
        if self.st.done(key):
            return
        self.st.mark(key)
        for name in C.WEEKLY_UNDERLYINGS:
            if self.st.open_positions("weekly", name):
                continue
            exps = [e for e in M.expiries(self.master, name) if 0 < M.dte(e) <= C.WEEKLY_MAX_DTE]
            if exps:
                self.try_open(name, "weekly", exps[0], "ONE_DAY")
        for name in C.MONTHLY_UNDERLYINGS + C.MONTHLY_STOCKS:
            if self.st.open_positions("monthly", name):
                continue
            lo, hi = C.MONTHLY_DTE_RANGE
            exps = [e for e in M.monthly_expiries(M.expiries(self.master, name)) if lo <= M.dte(e) <= hi]
            if exps:
                try:
                    self.try_open(name, "monthly", exps[0], "ONE_DAY", stock=name not in C.INDEX_TOKENS)
                except Exception as e:
                    print(name, "error", e)

    # ---------- MCX ----------
    def mcx_expiry(self, name, lo=None, hi=None):
        exps = [e for e in M.expiries(self.master, name, "MCX") if M.dte(e) >= C.MCX_MIN_DTE]
        if lo is not None:
            exps = [e for e in exps if lo <= M.dte(e) <= hi]
        return exps[0] if exps else None

    def mcx_open_today(self):
        for n in C.MCX_UNDERLYINGS:
            f = M.near_future(self.master, n, "MCX")
            if f is None:
                continue
            d = self.api.candles("MCX", f["token"], "FIFTEEN_MINUTE", now_ist() - pd.Timedelta(days=1), now_ist())
            return d is not None and not d.empty and d["time"].iloc[-1].normalize() == now_ist().normalize()
        return False

    def mcx_intraday_scan(self, force=False):
        now = now_ist()
        if not force and not (at(C.MCX_FIRST_SCAN) <= now <= at(C.MCX_LAST_ENTRY)):
            return
        slot = now.floor("h")
        for name in C.MCX_UNDERLYINGS:
            key = f"mcx_hourly|{name}|{slot:%Y-%m-%d %H:%M}"
            if self.st.done(key) or self.st.open_positions("intraday", name):
                continue
            self.st.mark(key)
            exp = self.mcx_expiry(name)
            if exp is not None:
                try:
                    self.try_open(name, "intraday", exp, "ONE_HOUR", exch="MCX")
                except Exception as e:
                    print(name, "MCX error", e)

    def mcx_positional_scan(self):
        now = now_ist()
        if not (at(C.MCX_POSITIONAL_WINDOW[0]) <= now <= at(C.MCX_POSITIONAL_WINDOW[1])):
            return
        key = f"mcx_positional|{now:%Y-%m-%d}"
        if self.st.done(key):
            return
        self.st.mark(key)
        for name in C.MCX_UNDERLYINGS:
            if self.st.open_positions("monthly", name):
                continue
            exp = self.mcx_expiry(name, *C.MCX_MONTHLY_DTE)
            if exp is not None:
                try:
                    self.try_open(name, "monthly", exp, "ONE_DAY", exch="MCX")
                except Exception as e:
                    print(name, "MCX error", e)

    def mcx_snapshot(self):
        """On-demand MCX market view in simple words (no trade, no RSI)."""
        L = [f"🛢️ *MCX MARKET VIEW* – {now_ist():%d %b %H:%M}", ""]
        for name in C.MCX_UNDERLYINGS:
            exp = self.mcx_expiry(name)
            if exp is None:
                L.append(f"*{name}*: no option contract found"); continue
            try:
                v = self.view(name, exp, "ONE_HOUR", "MCX")
            except Exception as e:
                v = None; print(name, e)
            if not v:
                L.append(f"*{name}*: data not available now\n"); continue
            ch, td, bu = v["ch"], v["td"], v["bu"]
            move = {"BULLISH": "leaning UP ⬆️", "BEARISH": "leaning DOWN ⬇️", "NEUTRAL": "sideways ↔️"}[v["bias"]]
            idea = {"BULLISH": "put-side selling favoured", "BEARISH": "call-side selling favoured",
                    "NEUTRAL": "both-side (range) selling favoured"}[v["bias"]]
            if ch["iv_label"] == "CHEAP":
                idea = "premiums are cheap – better to avoid selling now"
            L += [f"*{name}* {v['spot']:,.1f} (fut, option expiry {pd.Timestamp(exp):%d %b}) → {move}",
                  f" Trend: {td['regime'] if td else '-'} | Futures: {bu['label'] if bu else 'n/a'} | PCR {ch['pcr']}",
                  f" Support {ch['put_wall']:.0f} / Resistance {ch['call_wall']:.0f} | "
                  f"IV {ch['atm_iv']} vs RV {ch['rv']:.1f} ({ch['iv_label']}) | Expected move ±{ch['exp_move']}",
                  f" 📖 {simple_why(td, bu, ch).capitalize()}. → {idea}.", ""]
        L.append("_View only. A SELL CALL comes only when all rules pass._")
        notify.send("\n".join(L))

    # ---------- manage open trades ----------
    def monitor(self):
        pos = list(self.st.s["positions"])
        if not pos:
            return
        by_ex = {}
        for p in pos:
            by_ex.setdefault(p.get("exch", "NFO"), set()).update(l["token"] for l in p["legs"])
        qs = self.api.quotes({ex: sorted(t) for ex, t in by_ex.items()})
        spots = {}
        now = now_ist()
        for p in pos:
            ex = p.get("exch", "NFO")
            if ex == "MCX" and not (at("09:00") <= now <= at("23:30")):
                continue
            if ex == "NFO" and not (at("09:15") <= now <= at("15:45")):
                continue
            key = (p["name"], ex, p.get("fut_token"))
            if key not in spots:
                spots[key] = self.spot(p["name"], ex, p.get("fut_token"))[0]
            if not spots[key]:
                continue
            T = M.time_to_expiry(p["expiry"], ex)
            action, value, info = check(p, qs, spots[key], T, now)
            if not action:
                continue
            pnl = info["pnl"] * p["lot"]
            head = f"#{p['id']} {p['name']} {p['strategy']} ({p['mode']})"
            if action == "ADJUST":
                p["flags"].append("adjust")
                notify.send(f"⚖️ *ADJUST* {head}\n📖 {EXPLAIN['ADJUST']}\n\n"
                            f"Sold-option delta now {info['short_deltas']} (limit {p['adjust_delta']}) | "
                            f"Value {info['value']} vs credit {p['credit']} | P&L now {rs(pnl)}/lot")
                continue
            msg = {"TARGET": "✅ *BOOK PROFIT*", "SL": "🛑 *STOP-LOSS HIT – EXIT*", "TIME": "⏰ *TIME EXIT*"}[action]
            self.st.close(p, value, action)
            notify.send(f"{msg} {head}\n📖 {EXPLAIN[action]}\n\n"
                        f"P&L: *{info['pnl']:+} pts = {rs(pnl)}/lot* (exit value ≈ {info['value']}, credit {p['credit']})\n"
                        f"How: first BUY back the option you sold, then SELL the insurance option you bought.")

    # ---------- report ----------
    def report(self, force=False):
        now = now_ist()
        key = f"report|{now:%Y-%m-%d}"
        if (self.st.done(key) and not force) or (not force and not (at("15:32") <= now <= at("18:00"))):
            return
        self.st.mark(key)
        L = [f"📋 *DAILY OPTION-SELLING REPORT* – {now:%d %b %Y}", ""]
        v = self.vix()
        calm = "calm market (cheaper premiums)" if v["pctile"] < 30 else "nervous market (richer premiums, bigger moves)" if v["pctile"] > 70 else "normal volatility"
        L.append(f"India VIX {v['vix']} ({v['chg']:+}%) – {v['pctile']} percentile of 1 year → {calm}")
        for name in dict.fromkeys(C.INTRADAY_UNDERLYINGS + C.WEEKLY_UNDERLYINGS):
            spot, tok = self.spot(name)
            exps = M.expiries(self.master, name)
            if not spot or not exps:
                continue
            ch = M.build_chain(self.api, self.master, name, exps[0], spot)
            if not ch:
                continue
            self.st.record_iv(name, ch["atm_iv"])
            trend, td = M.trend_score(self.candles(tok, "ONE_DAY", 200), 20, 50)
            bu = M.futures_buildup(self.api, self.master, name)
            bias, sc = M.combine_bias(trend, bu, ch["pcr"])
            move = {"BULLISH": "leaning UP ⬆️", "BEARISH": "leaning DOWN ⬇️", "NEUTRAL": "sideways ↔️"}[bias]
            L.append(f"\n*{name}* {spot:,.1f} → {move}\n PCR {ch['pcr']} | Support {ch['put_wall']:.0f} | "
                     f"Resistance {ch['call_wall']:.0f}\n ATM IV {ch['atm_iv']} | IV Rank "
                     f"{self.st.iv_rank(name, ch['atm_iv']) or 'building'} | {bu['label'] if bu else ''}\n"
                     f" 📖 {simple_why(td, bu, ch).capitalize()}.")
        op = self.st.s["positions"]
        L.append(f"\n*Open calls: {len(op)}*")
        for p in op:
            L.append(f" #{p['id']} {p['name']} {p['strategy']} exp {pd.Timestamp(p['expiry']):%d%b} credit {p['credit']}")
        today = [c for c in self.st.s["closed"] if c["closed"].startswith(f"{now:%Y-%m-%d}")]
        if today:
            L.append(f"\n*Closed today:* {rs(sum(c['pnl_rs_per_lot'] for c in today))}/lot "
                     f"({sum(c['pnl_pts'] > 0 for c in today)}W / {sum(c['pnl_pts'] <= 0 for c in today)}L)")
        if now.weekday() == 4:
            wk = [c for c in self.st.s["closed"] if pd.Timestamp(c["closed"]) >= now.normalize() - pd.Timedelta(days=6)]
            allc = self.st.s["closed"]
            if allc:
                L.append("\n📖 _Profit factor above 1.2 and positive expectancy over 20+ calls = strategy is working._")
                wins = sum(c["pnl_pts"] > 0 for c in allc)
                pn = [c["pnl_rs_per_lot"] for c in allc]
                w = [x for x in pn if x > 0]; l_ = [x for x in pn if x <= 0]
                streak = mx = 0
                for x in pn:
                    streak = streak + 1 if x <= 0 else 0; mx = max(mx, streak)
                pf = f"{sum(w)/abs(sum(l_)):.2f}" if l_ and sum(l_) else "∞"
                L.append(f"\n📈 *Week:* {rs(sum(c['pnl_rs_per_lot'] for c in wk))}/lot on {len(wk)} trades"
                         f"\n*All-time:* {rs(sum(pn))}/lot | Win rate {wins/len(allc)*100:.0f}% ({len(allc)} trades)"
                         f"\nAvg win {rs(sum(w)/len(w) if w else 0)} | Avg loss {rs(sum(l_)/len(l_) if l_ else 0)} | "
                         f"Profit factor {pf}\nExpectancy {rs(sum(pn)/len(pn))}/trade | Max losing streak {mx}")
        notify.send("\n".join(L))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    now = now_ist()
    if mode == "auto" and (now.weekday() >= 5 or not (at("09:00") <= now <= at("23:59"))):
        print("Outside market hours - nothing to do."); return
    store = None
    try:
        api = Angel()
        if mode == "test":
            master = load_master()
            b = Bot(api, master, Store())
            s, _ = b.spot("NIFTY")
            ex = M.expiries(master, "NIFTY")[0]
            ch = M.build_chain(api, master, "NIFTY", ex, s)
            notify.send(f"✅ Option-selling bot connected!\nNIFTY {s} | Expiry {pd.Timestamp(ex):%d %b}\n"
                        f"PCR {ch['pcr'] if ch else '-'} | ATM IV {ch['atm_iv'] if ch else '-'} | VIX {b.vix()['vix']}")
            return
        master = load_master()

        # ENGINE B - RSI alerts: fully independent, its failure never touches Engine A (and vice versa)
        if C.RSI_ENGINE_ENABLED and mode == "auto":
            try:
                rsi_alert.run(api, master)
            except Exception as e:
                traceback.print_exc()
                notify.send(f"⚠️ RSI engine error: {type(e).__name__}: {str(e)[:200]}")

        # ENGINE A - option selling (NSE + MCX)
        store = Store()
        bot = Bot(api, master, store)
        if mode == "report":
            bot.report(force=True)
            return
        mcx_on = C.MCX_OPTIONS_ENABLED and at("09:00") <= now <= at("23:59") and bot.mcx_open_today()
        if mode == "mcx":
            bot.mcx_snapshot()
            if mcx_on:
                bot.mcx_intraday_scan(force=True)
            return
        nse_on = at("09:15") <= now <= at("18:00") and bot.market_open_today()
        if nse_on or mcx_on:
            bot.monitor()                     # exits / adjust alerts for every open call
        if nse_on and now <= at("15:31"):
            bot.intraday_scan()
            bot.positional_scan()
        if mcx_on:
            bot.mcx_intraday_scan()
            bot.mcx_positional_scan()
        if nse_on:
            bot.report()
    except Exception as e:
        traceback.print_exc()
        notify.send(f"⚠️ Bot error ({now:%H:%M}): {type(e).__name__}: {str(e)[:300]}")
        raise
    finally:
        if store:
            store.save()


if __name__ == "__main__":
    main()

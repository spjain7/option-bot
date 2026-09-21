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


# ─────────────── message formats ───────────────
def fmt_entry(t, ch, view):
    icon = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡"}[t["bias"]]
    L = [f"{icon} *SELL CALL #{t['id']}* – {t['name']} {t['strategy']}",
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
          f"❌ Invalid if spot closes beyond {', '.join(str(int(l['K'])) for l in t['legs'] if l['side']=='SELL')} (short strike)",
          "", "*Why:* " + view,
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

    def spot(self, name):
        tok = M.spot_token(self.master, name)
        q = self.api.quotes({"NSE": [tok]}).get(str(tok), {}) if tok else {}
        self._fresh = True
        t = pd.to_datetime(q.get("exchFeedTime"), errors="coerce", dayfirst=True)
        if pd.notna(t) and at("09:20") <= now_ist() <= at("15:30") and now_ist() - t > pd.Timedelta(minutes=10):
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

    def candles(self, tok, interval, days):
        n = now_ist()
        d = self.api.candles("NSE", tok, interval, n - pd.Timedelta(days=days), n)
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
    def try_open(self, name, mode, expiry, trend_interval, stock=False):
        why = self.blocked(mode)
        if why:
            print(f"{name} {mode}: NO TRADE - {why}"); return
        spot, tok = self.spot(name)
        if not spot or not self._fresh:
            print(f"{name}: NO TRADE - missing/stale spot data"); return
        is_hourly = trend_interval == "ONE_HOUR"
        cd = self.candles(tok, trend_interval, 25 if is_hourly else 200)
        trend, td = M.trend_score(cd, 9, 21) if is_hourly else M.trend_score(cd, 20, 50)
        bu = M.futures_buildup(self.api, self.master, name)
        ch = M.build_chain(self.api, self.master, name, expiry, spot,
                           C.CHAIN_RANGE_PCT["stock" if stock else mode])
        if not ch:
            print(f"{name}: no chain"); return
        ch["dte"] = M.dte(expiry)
        rv = M.hv20(cd if not is_hourly else self.candles(tok, "ONE_DAY", 60))
        ivl, ivx = M.iv_label(ch["atm_iv"], rv)
        if ivl == "CHEAP":
            print(f"{name}: NO TRADE - options CHEAP (IV {ch['atm_iv']} vs RV {rv:.1f})"); return
        ch["iv_label"], ch["iv_rv"], ch["rv"] = ivl, ivx, rv
        bias, score = M.combine_bias(trend, bu, ch["pcr"])
        vix = None if stock else self.vix()
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
                  "dte": M.dte(expiry), "spot_at_entry": spot})
        self.st.add(t)
        notify.send(fmt_entry(t, ch, view_text(bias, score, td, bu, ch, vix, ivr)))

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

    # ---------- manage open trades ----------
    def monitor(self):
        pos = list(self.st.s["positions"])
        if not pos:
            return
        toks = sorted({l["token"] for p in pos for l in p["legs"]})
        qs = self.api.quotes({"NFO": toks})
        spots = {}
        now = now_ist()
        for p in pos:
            if p["name"] not in spots:
                spots[p["name"]] = self.spot(p["name"])[0]
            T = M.time_to_expiry(p["expiry"])
            action, value, info = check(p, qs, spots[p["name"]], T, now)
            if not action:
                continue
            pnl = info["pnl"] * p["lot"]
            head = f"#{p['id']} {p['name']} {p['strategy']} ({p['mode']})"
            if action == "ADJUST":
                p["flags"].append("adjust")
                notify.send(f"⚖️ *ADJUST* {head}\nShort leg delta now {info['short_deltas']} "
                            f"(limit {p['adjust_delta']}).\nSpread {info['value']} vs credit {p['credit']} | "
                            f"P&L {rs(pnl)}/lot\n👉 Either EXIT the threatened side, or ROLL it further OTM "
                            f"(buy back the short, sell a new ~0.20Δ strike). Keep the untested side.")
                continue
            msg = {"TARGET": "✅ *BOOK PROFIT*", "SL": "🛑 *STOP-LOSS HIT – EXIT*", "TIME": "⏰ *TIME EXIT*"}[action]
            self.st.close(p, value, action)
            notify.send(f"{msg} {head}\nExit spread ≈ {info['value']} (credit {p['credit']})\n"
                        f"P&L: *{info['pnl']:+} pts = {rs(pnl)}/lot*\nClose ALL legs: SELL-leg first buy back, then sell hedge.")

    # ---------- report ----------
    def report(self, force=False):
        now = now_ist()
        key = f"report|{now:%Y-%m-%d}"
        if (self.st.done(key) and not force) or (not force and not (at("15:32") <= now <= at("18:00"))):
            return
        self.st.mark(key)
        L = [f"📋 *DAILY OPTION-SELLING REPORT* – {now:%d %b %Y}", ""]
        v = self.vix()
        L.append(f"India VIX {v['vix']} ({v['chg']:+}%) – {v['pctile']} percentile of 1 year")
        for name in dict.fromkeys(C.INTRADAY_UNDERLYINGS + C.WEEKLY_UNDERLYINGS):
            spot, tok = self.spot(name)
            exps = M.expiries(self.master, name)
            if not spot or not exps:
                continue
            ch = M.build_chain(self.api, self.master, name, exps[0], spot)
            if not ch:
                continue
            self.st.record_iv(name, ch["atm_iv"])
            trend, _ = M.trend_score(self.candles(tok, "ONE_DAY", 200), 20, 50)
            bu = M.futures_buildup(self.api, self.master, name)
            bias, sc = M.combine_bias(trend, bu, ch["pcr"])
            L.append(f"\n*{name}* {spot:,.1f} → {bias}\n PCR {ch['pcr']} | Support {ch['put_wall']:.0f} | "
                     f"Resistance {ch['call_wall']:.0f}\n ATM IV {ch['atm_iv']} | IV Rank "
                     f"{self.st.iv_rank(name, ch['atm_iv']) or 'building'} | {bu['label'] if bu else ''}")
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

        # ENGINE A - option selling (NSE hours only)
        store = Store()
        bot = Bot(api, master, store)
        if mode == "report":
            bot.report(force=True)
        elif at("09:15") <= now <= at("18:00"):
            if not bot.market_open_today():
                print("Market holiday / not open."); return
            bot.monitor()                     # also after close: forces any leftover intraday time-exit
            if now <= at("15:31"):
                bot.intraday_scan()
                bot.positional_scan()
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

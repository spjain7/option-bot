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
python runner.py mcx       # MCX market view now (view only)
python runner.py view      # NIFTY / BANKNIFTY / SENSEX view now (view only)
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
import flow                           # OI / volume activity alerts (part of Engine A, no RSI)
from guards import bounce               # never sell INTO a fresh bounce / drop
from angel import Angel, load_master, now_ist
from positions import Store, check, _hm, range_check


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
    till = (f"for the rest of today (intraday – exit by {t.get('exit_time', C.INTRADAY_EXIT_TIME)})"
            if t["mode"] == "intraday" else f"till expiry {pd.Timestamp(t['expiry']):%d %b}")
    L = ["📖 *In simple words*",
         f"• The bot expects {view} (now {t['spot_at_entry']:,.1f}) {till}.",
         f"• You receive about {rs(t['credit'] * lot)} per lot today by selling the option(s)."]
    if buys:
        L.append(f"• The option you BUY is insurance: worst-case loss is capped at {rs(t['max_loss'] * lot)} per lot.")
    else:
        L.append("• ⚠️ No insurance leg (naked): loss is NOT capped – the stop-loss is a must.")
    L += [f"• Plan: take profit at +{rs(t['reward_rs'])}, cut loss at -{rs(t['risk_rs'])} – whichever comes first "
          f"(sellers win small & often; the stop keeps losses limited).",
          f"• Why: {why}." if why else "",
          f"• Chance this ends in profit ≈ {t['pop']}% (estimate – losses happen)."]
    return [x for x in L if x]


def rsi_exhaustion(cd, bu):
    """User rule (27-Oct-2026): hourly RSI > 80 / < 25 + futures OI positioning decides the option-SELL side.
      RSI > 80 + SHORT COVERING (price up, OI down – rally from shorts exiting)  -> SELL CE (rally likely to fade)
      RSI > 80 + LONG BUILDUP  (fresh longs, strong trend)                       -> no CE sell
      RSI < 25 + LONG UNWINDING (price down, OI down – fall from longs exiting)  -> SELL PE
      RSI < 25 + SHORT BUILDUP (fresh shorts)                                    -> no PE sell
    Volume: the signal candle's volume vs the 20-candle average is shown (climax > 1.5×).
    Backtest note (research/search/REGISTRY_RSISELL.md): OTM sells after RSI extremes win ~85-91%, about the same as on
    ordinary days – the OI positioning part could not be backtested (no intraday OI history)."""
    if cd is None or len(cd) < 30 or not bu:
        return None
    r = float(market_rsi(cd["close"]).iloc[-1])
    v = cd["volume"].astype(float) if "volume" in cd else None
    vx = float(v.iloc[-1] / v.iloc[-21:-1].mean()) if v is not None and v.iloc[-21:-1].mean() > 0 else None
    vtxt = f", volume {vx:.1f}×" if vx else ""
    lab = bu.get("label")
    if r >= C.RSI_SELL_HIGH:
        if lab == "Short covering":
            return dict(action="sell", bias="BEARISH", why=f"RSI(1h) {r:.0f} > {C.RSI_SELL_HIGH} + SHORT COVERING (price {bu['px_chg']:+.2f}%, "
                        f"OI {bu['oi_chg']:+.2f}%{vtxt}) – rally from shorts exiting, likely to fade → SELL CE")
        if lab == "Long buildup":
            return dict(action="block", bias_blocked="BEARISH", why=f"RSI {r:.0f} but LONG BUILDUP – strong up-trend, no CE sell")
    if r <= C.RSI_SELL_LOW:
        if lab == "Long unwinding":
            return dict(action="sell", bias="BULLISH", why=f"RSI(1h) {r:.0f} < {C.RSI_SELL_LOW} + LONG UNWINDING (price {bu['px_chg']:+.2f}%, "
                        f"OI {bu['oi_chg']:+.2f}%{vtxt}) – fall from longs exiting, likely to bounce → SELL PE")
        if lab == "Short buildup":
            return dict(action="block", bias_blocked="BULLISH", why=f"RSI {r:.0f} but SHORT BUILDUP – strong down-trend, no PE sell")
    return None


def market_rsi(close, n=14):
    d = close.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    rs = up.ewm(alpha=1 / n, adjust=False).mean() / dn.ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + rs)


def confidence(t, td, bu, ch):
    """0-100: how many independent things agree with this sell. No RSI here."""
    bias, pts, why = t["bias"], 0, []
    up = bias == "BULLISH"
    if td and td["regime"] == ("UPTREND" if up else "DOWNTREND"):
        pts += 25; why.append(f"Trend is {'UP' if up else 'DOWN'} on the chart")
        if td["adx"] >= 25:
            pts += 5; why[-1] += " (strong)"
    elif td and bias == "NEUTRAL" and td["regime"] == "RANGE":
        pts += 25; why.append("Price is moving sideways")
    if bu is None:
        pts += 10
    elif bu["label"] == ("Long buildup" if up else "Short buildup"):
        pts += 20; why.append(f"Fresh {'buying' if up else 'selling'} in futures (OI {bu['oi_chg']:+}%)")
    elif bu["label"] == ("Short covering" if up else "Long unwinding"):
        pts += 8
    p = ch.get("pcr")
    if p is not None:
        if (up and p >= C.PCR_BULL) or (not up and bias == "BEARISH" and p <= C.PCR_BEAR):
            pts += 15; why.append(f"Option writers agree (PCR {p})")
        elif C.PCR_BEAR < p < C.PCR_BULL:
            pts += 7
    x = ch.get("iv_rv") or 0
    if x >= 1.5:
        pts += 20; why.append(f"Premium is very rich (IV {ch['atm_iv']} vs normal {ch['rv']:.0f})")
    elif x >= 1.1:
        pts += 15; why.append(f"Premium is rich (IV {ch['atm_iv']} vs normal {ch['rv']:.0f})")
    elif x >= 0.9:
        pts += 5
    leg = [l for l in t["legs"] if l["side"] == "SELL"][0]
    wall = ch.get("call_wall") if leg["typ"] == "CE" else ch.get("put_wall")
    if wall and ((leg["typ"] == "CE" and leg["K"] >= wall) or (leg["typ"] == "PE" and leg["K"] <= wall)):
        pts += 10; why.append(f"Strike is beyond the big {'resistance' if leg['typ']=='CE' else 'support'} at {k_(wall)}")
    pts += {"LOW": 5, "MEDIUM": 3}.get(t["gamma_risk"], 0)
    return min(pts, 100), why


def sr_text(ch):
    """Nearest support BELOW and resistance ABOVE the current price:
    option-OI walls + pivot levels from yesterday (S2, S1, P, R1, R2, prev-day high/low)."""
    px = ch.get("spot") or ch.get("F")                    # judge levels against the CMP shown to you
    sup = [(ch["put_wall"], f"{k_(ch['put_wall'])} (OI)")] if ch.get("put_wall") and ch["put_wall"] < px else []
    res = [(ch["call_wall"], f"{k_(ch['call_wall'])} (OI)")] if ch.get("call_wall") and ch["call_wall"] > px else []
    pv = ch.get("pivots") or {}
    names = {"S3": "S3", "S2": "S2", "S1": "S1", "P": "Pivot", "R1": "R1", "R2": "R2", "R3": "R3",
             "PDH": "Prev high", "PDL": "Prev low"}
    below = sorted(((v, k) for k, v in pv.items() if v < px), reverse=True)
    above = sorted((v, k) for k, v in pv.items() if v > px)
    if below:
        sup.append((below[0][0], f"{below[0][0]:,.0f} ({names[below[0][1]]})"))
    if above:
        res.append((above[0][0], f"{above[0][0]:,.0f} ({names[above[0][1]]})"))
    sup = [t for _, t in sorted(sup, reverse=True)]          # nearest first
    res = [t for _, t in sorted(res)]
    return f"Support {' · '.join(sup) or '-'} | Resistance {' · '.join(res) or '-'}"


def flip_confirmed(bias, came_from, bu):
    """28-Oct: a direction that just appeared after a sideways reading must be backed by real futures positioning
    (Long buildup for bullish / Short buildup for bearish, OI change >= FLIP_MIN_OI_PCT). -> (ok, reason)"""
    if bias == "NEUTRAL" or came_from != "NEUTRAL":
        return True, ""
    need = {"BULLISH": "Long buildup", "BEARISH": "Short buildup"}[bias]
    lim = getattr(C, "FLIP_MIN_OI_PCT", 1.0)
    if bu and bu.get("label") == need and abs(bu.get("oi_chg") or 0) >= lim:
        return True, ""
    got = f"{bu.get('label')} (OI {bu.get('oi_chg', 0):+.2f}%)" if bu else "no OI data"
    return False, f"{bias.lower()} flip from sideways not backed by futures positioning – need {need} with OI ≥ {lim}%, have {got}"


def near_level(ch, spot, bias):
    """28-Oct: never sell a PE just under resistance (price likely to turn down) or a CE just above support."""
    if bias not in ("BULLISH", "BEARISH") or not spot:
        return None
    buf = getattr(C, "SR_BUFFER_PCT", 0.3) / 100
    pv = ch.get("pivots") or {}
    lv = [v for v in list(pv.values()) + [ch.get("call_wall"), ch.get("put_wall")] if v]
    if bias == "BULLISH":
        res = [v for v in lv if spot < v <= spot * (1 + buf)]
        if res:
            return f"bullish but price {spot:,.1f} is right under resistance {min(res):,.1f} – no PE sell there"
    else:
        sup = [v for v in lv if spot * (1 - buf) <= v < spot]
        if sup:
            return f"bearish but price {spot:,.1f} is right above support {max(sup):,.1f} – no CE sell there"
    return None


def exit_by(t):
    if t["mode"] == "intraday":
        return f"{t.get('exit_time')} today"
    if t["mode"] == "weekly":
        return f"{pd.Timestamp(t['expiry']):%d %b} {C.WEEKLY_EXIT_TIME}"
    return f"{pd.Timestamp(t['expiry']) - pd.Timedelta(days=C.MONTHLY_EXIT_DTE):%d %b}"


def fmt_naked(t, conf, why, ch=None, status=None):
    """Option SELL call: message 1 = the call, message 2 = WHY (returned joined by a split marker)."""
    l = [x for x in t["legs"] if x["side"] == "SELL"][0]
    ex = {"MCX": "MCX", "BFO": "BSE"}.get(t.get("exch"), "NSE")
    kind = "Intraday" if t["mode"] == "intraday" else "Positional"
    direction = "above" if l["typ"] == "CE" else "below"
    call = [f"{'🔴' if l['typ'] == 'CE' else '🟢'} SELL  {t['name']} {k_(l['K'])} {l['typ']}  ·  {kind}",
            "━━━━━━━━━━━━━━",
            f"Entry   : ₹{l['entry']}",
            f"SL      : ₹{t['sl_val']}  (or {t['name']} {direction} {t['spot_stop']:,.1f})",
            f"Target  : ₹{t['target_val']}",
            f"Lot     : {t['lot']}  ·  exp {pd.Timestamp(t['expiry']):%d-%b}  ·  {ex}",
            f"Exit by : {exit_by(t)}"]
    W = [f"📌 WHY – {t['name']} {k_(l['K'])} {l['typ']} SELL", "━━━━━━━━━━━━━━",
         f"• Chart   : {'1-hour' if t['mode'] == 'intraday' else 'Daily'} candles · {t['name']} {t['spot_at_entry']:,.1f} · "
         f"view {t.get('bias', '').lower()}"]
    for w in (why or [])[:5]:
        W.append(f"• {w}")
    if status and (status.get("day") or status.get("hour")):
        W.append(f"• OI      : today {status.get('day') or 'building'}" + (f" · last 1h {status['hour']}" if status.get("hour") else ""))
    if ch:
        W.append(f"• Levels  : {sr_text(ch)}")
    W.append(f"• Odds    : confidence {conf}/100 · chance of profit ≈ {t['pop']}%")
    W.append(f"• Margin  : ≈ {rs(t['margin_rs'])}/lot (Angel One shows exact)")
    W.append("Not investment advice.")
    return "\n".join(call) + "\n<<SPLIT>>\n" + "\n".join(W)


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
    ex = {"MCX": "MCX", "BFO": "BSE"}.get(t.get("exch"), "NSE")
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
        self.notes = []                 # (name, reason) for the hourly "why no call" summary

    def why(self, name, reason):
        print(f"{name}: {reason}")
        self.notes.append((name, reason))

    def send_scan_summary(self):
        """One short message per hourly scan: which scripts were checked and why no call was sent."""
        if not self.notes or not C.SCAN_SUMMARY:
            return
        hk = f"summary|{now_ist():%Y-%m-%d %H}"
        if self.st.done(hk):                     # at most one summary per hour
            return
        self.st.mark(hk)
        seen, rows = set(), []
        for n, r in self.notes:
            if n not in seen:
                seen.add(n); rows.append((n, r))
        idx = [f"• *{n}*: {r}" for n, r in rows if n in C.INDEX_TOKENS or n in C.MCX_UNDERLYINGS]
        stocks = [(n, r) for n, r in rows if n not in C.INDEX_TOKENS and n not in C.MCX_UNDERLYINGS]
        L = [f"🔎 *Scan {now_ist():%H:%M}* – why no new SELL call", ""] + idx
        if stocks:
            waiting = [n for n, r in stocks if "waiting" in r]
            close = [f"{n} ({r.split('confidence ')[1].split('/')[0]})" for n, r in stocks if "confidence" in r]
            L.append(f"• *Stocks checked*: {len(stocks)}"
                     + (f" | waiting confirmation: {', '.join(waiting[:8])}" if waiting else "")
                     + (f" | low confidence: {', '.join(close[:6])}" if close else ""))
        L += ["", "_A call is sent only when every rule passes – no call is also a decision._"]
        notify.send("\n".join(L))

    def vix(self):
        if self._vix is None:
            self._vix = M.vix_info(self.api)
        return self._vix

    def spot(self, name, exch="NFO", fut_token=None):
        if exch == "MCX":                                          # MCX options are on the future
            tok, seg = str(fut_token), "MCX"
        else:
            tok, seg = M.spot_token(self.master, name), M.spot_seg(name)
        q = self.api.quotes({seg: [tok]}).get(str(tok), {}) if tok else {}
        self._fresh = True
        t = pd.to_datetime(q.get("exchFeedTime"), errors="coerce", dayfirst=True)
        live = (at("09:05"), at("23:25")) if exch == "MCX" else (at("09:20"), at("15:30"))
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
            self.why(name, "price data missing/stale"); return None
        seg = "MCX" if exch == "MCX" else M.spot_seg(name)
        is_hourly = trend_interval == "ONE_HOUR"
        cd = self.candles(tok, trend_interval, 25 if is_hourly else 200, seg)
        trend, td = M.trend_score(cd, 9, 21) if is_hourly else M.trend_score(cd, 20, 50)
        bu = M.futures_buildup(self.api, self.master, name, exch, fut)
        f_row = fut or M.near_future(self.master, name, exch)
        fut_tok = str(f_row["token"]) if f_row is not None else None
        if bu is None and fut_tok:                      # e.g. MCX: build OI status from our own snapshots
            bu = flow.buildup_dict(self.st.s, fut_tok)
        rng = C.MCX_CHAIN_RANGE_PCT.get(mode, 0.1) if exch == "MCX" else C.CHAIN_RANGE_PCT["stock" if stock else mode]
        ch = M.build_chain(self.api, self.master, name, expiry, spot, rng, exch)
        if not ch:
            self.why(name, "no option chain"); return None
        ch["dte"] = M.dte(expiry)
        daily = cd if not is_hourly else self.candles(tok, "ONE_DAY", 60, seg)
        if daily is None or len(daily) == 0:            # API rate-limit / no data: skip, don't crash the scan
            self.why(name, "daily candles missing"); return None
        rv = M.hv20(daily)
        ch["iv_label"], ch["iv_rv"] = M.iv_label(ch["atm_iv"], rv)
        ch["rv"] = rv or 0.0
        ch["pivots"] = M.pivots(daily)
        bias, score = M.combine_bias(trend, bu, ch["pcr"])
        return {"spot": spot, "tok": tok, "fut": fut, "td": td, "bu": bu, "ch": ch, "rv": rv, "cd": cd if is_hourly else None,
                "bias": bias, "score": score, "fut_tok": fut_tok,
                "status": flow.status(self.st.s, fut_tok) if fut_tok else {"day": None, "hour": None}}

    def try_open(self, name, mode, expiry, trend_interval, stock=False, exch="NFO", fast=None):
        why = self.blocked(mode)
        today = f"{now_ist():%Y-%m-%d}"
        n_today = sum(1 for p in self.st.s["positions"] + self.st.s["closed"]
                      if p["name"] == name and p["mode"] == mode and p.get("opened", "").startswith(today))
        if not why and mode == "intraday" and n_today >= C.MAX_CALLS_PER_NAME_DAY:
            why = f"already {n_today} calls today"
        if why:
            self.why(name, why); return
        if mode == "intraday" and exch != "MCX" and M.dte(expiry) > getattr(C, "INTRADAY_MAX_DTE", 99):
            self.why(name, f"nearest expiry {M.dte(expiry)} days away – too little time decay for a same-day sell "
                           "(longer expiries are handled by the positional scan)"); return
        v = self.view(name, expiry, trend_interval, exch, stock, mode)
        if not v:
            return
        spot, td, bu, ch, rv, bias, score = v["spot"], v["td"], v["bu"], v["ch"], v["rv"], v["bias"], v["score"]
        rsi_rule = rsi_exhaustion(v.get("cd"), bu) if getattr(C, "RSI_SELL_ENABLED", False) else None
        if rsi_rule and rsi_rule["action"] == "block" and bias == rsi_rule["bias_blocked"]:
            self.why(name, rsi_rule["why"]); return
        if rsi_rule and rsi_rule["action"] == "sell":
            bias = rsi_rule["bias"]
        # confirmation: intraday direction must repeat on consecutive hourly checks
        hist = self.st.s.setdefault("bias_hist", {})
        hk, now = f"{exch}|{name}|{mode}", now_ist()
        prev = hist.get(hk)
        recent = prev and now - pd.Timestamp(prev["t"]) <= pd.Timedelta(minutes=C.CONFIRM_WINDOW_MIN)
        n = prev["n"] + 1 if recent and prev["bias"] == bias else 1
        came_from = (prev.get("from", "NEUTRAL") if recent and prev["bias"] == bias else
                     prev["bias"] if recent else "NEUTRAL")
        hist[hk] = {"bias": bias, "t": str(now), "n": n, "from": came_from}
        flip_ok, flip_why = flip_confirmed(bias, came_from, bu)
        if fast and fast == bias:                        # ⚡ futures buildup already confirms this direction
            n = max(n, C.CONFIRM_CHECKS)
        if rsi_rule and rsi_rule["action"] == "sell":     # RSI exhaustion + OI positioning: shoot the call now
            n = max(n, C.CONFIRM_CHECKS)
        if mode == "intraday" and n < C.CONFIRM_CHECKS:
            self.why(name, f"{bias.lower()} – waiting confirmation on next scan" if bias != "NEUTRAL"
                     else "sideways – no side to sell"); return
        if mode == "intraday" and getattr(C, "FLIP_CHECK", True) and not (rsi_rule and rsi_rule["action"] == "sell") and not flip_ok:
            self.why(name, flip_why); return
        near = near_level(ch, spot, bias)
        if near:
            self.why(name, near); return
        if getattr(C, "BOUNCE_FILTER", False) and bias in ("BULLISH", "BEARISH"):
            try:
                seg = "MCX" if exch == "MCX" else M.spot_seg(name)
                d15 = self.api.candles(seg, v["tok"], "FIFTEEN_MINUTE", now.normalize(), now)
                if d15 is not None and not d15.empty:
                    d15 = d15[d15["time"].dt.normalize() == now.normalize()]
                stop = bounce.check(d15, spot, bias, C.BOUNCE_ATR_X)
            except Exception as e_:
                stop = None; print(name, "bounce check error", e_)
            if stop:
                self.why(name, stop); return
        ivl, ivx = ch["iv_label"], ch["iv_rv"]
        if ivl == "CHEAP":
            self.why(name, "premium cheap (IV below normal)"); return
        vix = None if (stock or exch == "MCX") else self.vix()
        ivr = self.st.iv_rank(name, ch["atm_iv"])

        allow_condor = True
        if vix:
            if vix["chg"] > C.VIX_SPIKE_BLOCK_PCT:
                self.why(name, f"VIX jumping {vix['chg']}% – no new sells"); return
            allow_condor = vix["pctile"] >= C.VIX_LOW_PCTILE
        if stock:
            if not ivx or ivx < C.STOCK_MIN_IV_HV:
                self.why(name, "stock premium not rich enough"); return
            if bias == "NEUTRAL":
                return                                   # stocks: directional spreads only

        m = mode
        if mode == "intraday" and M.dte(expiry) == 0:
            m = "intraday_expiry"
        t = S.build_trade(ch, bias, m, allow_condor)
        if not t:
            self.why(name, "sideways – no side to sell" if bias == "NEUTRAL" else
                     f"{bias.lower()} but no strike passes (premium < ₹{C.MIN_PREMIUM_RS_PER_LOT}/lot, liquidity or R:R)"); return
        order = ["LOW", "MEDIUM", "HIGH", "EXTREME"]
        if t["gamma_risk"] in order and order.index(t["gamma_risk"]) >= order.index(C.GAMMA_BLOCK):
            self.why(name, f"gamma risk {t['gamma_risk']} (too close to expiry)"); return
        conf, reasons = confidence(t, td, bu, ch)
        if rsi_rule and rsi_rule["action"] == "sell":
            reasons = [rsi_rule["why"]] + list(reasons)
            conf = max(conf, C.MIN_CONFIDENCE)
        if C.SELL_STYLE == "NAKED" and conf < C.MIN_CONFIDENCE:
            self.why(name, f"{bias.lower()} but confidence {conf}/100 (need {C.MIN_CONFIDENCE})"); return
        try:                                              # option-premium levels on the exchange tick (28-Oct audit)
            from alerts.tradeplan import tick_round
            lt = self.master[self.master["token"].astype(str) == str(t["legs"][0]["token"])]
            tk = float(lt["tick"].iloc[0]) if len(lt) and "tick" in lt and lt["tick"].iloc[0] == lt["tick"].iloc[0] else 0.05
            t["sl_val"] = tick_round(t["sl_val"], tk)
            t["target_val"] = tick_round(t["target_val"], tk)
            gain_, loss_ = t["credit"] - t["target_val"], t["sl_val"] - t["credit"]
            naked_ = len(t["legs"]) == 1                  # the reward/risk rule applies to naked sells (as in strategy.py)
            if not (t["target_val"] < t["credit"] < t["sl_val"]) or (naked_ and gain_ < C.MIN_RR * loss_ - tk - 1e-9):
                self.why(name, "levels invalid after tick rounding"); return
        except Exception as e_:
            print(name, "tick rounding skipped:", e_)
        t.update({"name": name, "mode": mode, "expiry": str(pd.Timestamp(expiry).date()), "confidence": conf,
                  "dte": M.dte(expiry), "spot_at_entry": spot, "exch": exch,
                  "fut_token": str(v["fut"]["token"]) if v["fut"] else None,
                  "exit_time": C.MCX_INTRADAY_EXIT if exch == "MCX" else C.INTRADAY_EXIT_TIME})
        self.st.add(t)
        if len(t["legs"]) == 1:
            for part in fmt_naked(t, conf, reasons, ch, v.get("status")).split("\n<<SPLIT>>\n"):
                notify.send(part)
        else:
            notify.send(fmt_entry(t, ch, view_text(bias, score, td, bu, ch, vix, ivr), simple_why(td, bu, ch)))

    # ---------- scans ----------
    def intraday_scan(self):
        now = now_ist()
        if not (at(C.INTRADAY_FIRST_SCAN) <= now <= at(C.INTRADAY_LAST_ENTRY)):
            return
        slot = now.floor("15min") if C.CALL_MODE == "ACTIVE" else now.normalize() + pd.Timedelta(hours=9, minutes=15) + \
            pd.Timedelta(hours=int((now - now.normalize() - pd.Timedelta(hours=9, minutes=15)) / pd.Timedelta(hours=1)))
        for name in C.INTRADAY_UNDERLYINGS + C.INTRADAY_STOCKS:
            key = f"hourly|{name}|{slot:%Y-%m-%d %H:%M}"
            if self.st.done(key) or self.st.open_positions("intraday", name):
                continue
            self.st.mark(key)
            stock = name not in C.INDEX_TOKENS
            ex = M.deriv_exch(name)
            exps = [e for e in M.expiries(self.master, name, ex) if not stock or M.dte(e) >= 2]
            if exps:
                try:
                    self.try_open(name, "intraday", exps[0], "ONE_HOUR", stock=stock, exch=ex)
                except Exception as e:
                    print(name, "error", e)

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
            ex = M.deriv_exch(name)
            exps = [e for e in M.expiries(self.master, name, ex) if 0 < M.dte(e) <= C.WEEKLY_MAX_DTE]
            if exps:
                self.try_open(name, "weekly", exps[0], "ONE_DAY", exch=ex)
        stocks = flow.stock_picks(self) if C.MONTHLY_STOCKS == "AUTO" else C.MONTHLY_STOCKS
        for name in C.MONTHLY_UNDERLYINGS + list(stocks):
            if self.st.open_positions("monthly", name):
                continue
            lo, hi = C.MONTHLY_DTE_RANGE
            ex = M.deriv_exch(name)
            exps = [e for e in M.monthly_expiries(M.expiries(self.master, name, ex)) if lo <= M.dte(e) <= hi]
            if exps:
                try:
                    self.try_open(name, "monthly", exps[0], "ONE_DAY", stock=name not in C.INDEX_TOKENS, exch=ex)
                except Exception as e:
                    print(name, "error", e)

    # ---------- ⚡ fast track: strong futures buildup -> evaluate a sell call right away ----------
    def fast_track(self, events):
        if not C.FLOW_FAST_TRACK:
            return
        now = now_ist()
        for e in events:
            if not e.get("bias") or self.st.open_positions("intraday", e["name"]):
                continue
            ex = e["exch"]
            if ex == "MCX":
                if not (at(C.MCX_FIRST_SCAN) <= now <= at(C.MCX_LAST_ENTRY)):
                    continue
                exp = self.mcx_expiry(e["name"])
            else:
                if not (at(C.INTRADAY_FIRST_SCAN) <= now <= at(C.INTRADAY_LAST_ENTRY)):
                    continue
                if e["name"] not in C.INDEX_TOKENS and e["name"] not in C.INTRADAY_STOCKS and \
                        e["name"] not in flow.stock_picks(self):
                    continue                                   # only liquid / strongest stocks
                stock = e["name"] not in C.INDEX_TOKENS
                exps = [x for x in M.expiries(self.master, e["name"], ex) if not stock or M.dte(x) >= 2]
                exp = exps[0] if exps else None
            if exp is None:
                continue
            try:
                self.try_open(e["name"], "intraday", exp, "ONE_HOUR", stock=e["name"] not in C.INDEX_TOKENS and ex != "MCX",
                              exch=ex, fast=e["bias"])
            except Exception as err:
                print(e["name"], "fast-track error", err)

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
        slot = now.floor("15min") if C.CALL_MODE == "ACTIVE" else now.floor("h")
        for name in C.MCX_UNDERLYINGS:
            key = f"mcx_hourly|{name}|{slot:%Y-%m-%d %H:%M}"
            if self.st.done(key) or self.st.open_positions("intraday", name):
                continue
            self.st.mark(key)
            exp = self.mcx_expiry(name)                  # 28-Oct: MCX intraday sells on 8+ day expiries were the best live segment
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

    def snapshot(self, items, title):
        """On-demand market view in simple words (no trade, no RSI)."""
        L = [f"{title} – {now_ist():%d %b %H:%M}", ""]
        for name, exch, exp in items:
            if exp is None:
                L.append(f"*{name}*: no option contract found\n"); continue
            try:
                v = self.view(name, exp, "ONE_HOUR", exch)
            except Exception as e:
                v = None; print(name, e)
            if not v:
                L.append(f"*{name}*: data not available now\n"); continue
            ch, stt = v["ch"], v["status"]
            arrow = {"BULLISH": "⬆️ up", "BEARISH": "⬇️ down", "NEUTRAL": "↔️ sideways"}[v["bias"]]
            idea = {"BULLISH": "PE-sell side", "BEARISH": "CE-sell side", "NEUTRAL": "no clear side"}[v["bias"]]
            if ch["iv_label"] == "CHEAP":
                idea = "premium cheap – avoid"
            fut_lbl = f" ({pd.Timestamp(v['fut']['expiry_dt']):%b} fut)" if v.get("fut") else ""
            L.append(f"*{name}*{fut_lbl} {v['spot']:,.1f} {arrow} | premium {ch['iv_label'].lower()} → {idea}")
            L.append(f"   OI today: {stt['day'] or 'building (needs a few runs)'}"
                     + (f" · last 1h: {stt['hour']}" if stt["hour"] else ""))
            L.append(f"   📍 {sr_text(ch)}\n")
        L.append("_View only – a SELL call comes only after confirmation and confidence ≥ "
                 f"{C.MIN_CONFIDENCE}/100._")
        notify.send("\n".join(L))

    def mcx_snapshot(self):
        self.snapshot([(n, "MCX", self.mcx_expiry(n)) for n in C.MCX_UNDERLYINGS], "🛢️ *MCX VIEW*")

    def index_snapshot(self):
        items = []
        for n in C.INTRADAY_UNDERLYINGS:
            ex = M.deriv_exch(n)
            exps = M.expiries(self.master, n, ex)
            items.append((n, ex, exps[0] if exps else None))
        self.snapshot(items, "📈 *INDEX VIEW*")

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
            if ex in ("NFO", "BFO") and not (at("09:15") <= now <= at("15:45")):
                continue
            key = (p["name"], ex, p.get("fut_token"))
            if key not in spots:
                spots[key] = self.spot(p["name"], ex, p.get("fut_token"))[0]
            if not spots[key]:
                continue
            T = M.time_to_expiry(p["expiry"], ex)
            action, value, info = check(p, qs, spots[key], T, now)
            touched = None
            if len(p["legs"]) == 1 and p["legs"][0]["side"] == "SELL" and action not in ("SL", "SPOT"):
                # SL / target touched between two scans (1-minute highs / lows since the last check)
                since = p.get("checked") or p["opened"]
                try:
                    bars = self.api.candles(ex, p["legs"][0]["token"], "ONE_MINUTE", pd.Timestamp(since) - pd.Timedelta(minutes=2), now)
                except Exception:
                    bars = None
                ra, rv, rt = range_check(p, bars, since)
                if ra and (ra == "SL" or action is None or action == "ADJUST"):
                    action, value, touched = ra, rv, rt
                    info = dict(info or {}, value=rv, pnl=round(p["credit"] - rv, 2))
                if bars is not None and len(bars):
                    p["checked"] = str(pd.Timestamp(bars["time"].iloc[-1]) - pd.Timedelta(minutes=1))   # last bar was still forming
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
            self.st.close(p, value, action)
            costs = C.COST_PER_ORDER_RS * len(p["legs"]) * 2
            net = pnl - costs
            today = [c for c in self.st.s["closed"] if c["closed"].startswith(f"{now:%Y-%m-%d}")]
            day_net = sum(c["pnl_rs_per_lot"] - C.COST_PER_ORDER_RS * len(c["legs"]) * 2 for c in today)
            wins = sum(c["pnl_pts"] > 0 for c in today)
            tally = (f"\n📊 *Trade closed: {'+' if net >= 0 else ''}{rs(net)} per lot* (after ≈{rs(costs)} costs)"
                     f"\nToday: {'+' if day_net >= 0 else ''}{rs(day_net)}/lot from {len(today)} closed calls "
                     f"({wins} profit, {len(today) - wins} loss)")
            if len(p["legs"]) == 1:
                l = p["legs"][0]
                what = f"{p['name']} {k_(l['K'])} {l['typ']} #{p['id']}"
                head = {"TARGET": "✅ *BOOK PROFIT*", "SL": "🛑 *STOP-LOSS HIT*",
                        "SPOT": f"🛑 *PRICE STOP* – {p['name']} crossed {p['spot_stop']:,.1f}",
                        "TIME": "⏰ *TIME EXIT*"}[action]
                when = (f"\n⏱ Level ₹{info['value']} was touched at {touched:%H:%M} (between scans) – booked at that level; "
                        "if still open, exit now at market." if touched is not None else "")
                notify.send(f"{head}\n{what}\nBuy back now at ≈ ₹{info['value']} (sold at ₹{p['credit']})" + when
                            + ("\n_Don't wait for recovery._" if action in ("SL", "SPOT") else "") + tally)
            else:
                msg = {"TARGET": "✅ *BOOK PROFIT*", "SL": "🛑 *STOP-LOSS HIT – EXIT*", "TIME": "⏰ *TIME EXIT*",
                       "SPOT": "🛑 *PRICE STOP*"}[action]
                notify.send(f"{msg} {head}\n📖 {EXPLAIN.get(action, '')}\n\n"
                            f"Exit value ≈ {info['value']} (credit {p['credit']})" + tally)

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
            ex = M.deriv_exch(name)
            exps = M.expiries(self.master, name, ex)
            if not spot or not exps:
                continue
            ch = M.build_chain(self.api, self.master, name, exps[0], spot, 0.06, ex)
            if not ch:
                continue
            self.st.record_iv(name, ch["atm_iv"])
            trend, td = M.trend_score(self.candles(tok, "ONE_DAY", 200, M.spot_seg(name)), 20, 50)
            bu = M.futures_buildup(self.api, self.master, name, ex)
            bias, sc = M.combine_bias(trend, bu, ch["pcr"])
            move = {"BULLISH": "leaning UP ⬆️", "BEARISH": "leaning DOWN ⬇️", "NEUTRAL": "sideways ↔️"}[bias]
            daily = self.candles(tok, "ONE_DAY", 60, M.spot_seg(name))
            ch["pivots"] = M.pivots(daily)
            f_row = M.near_future(self.master, name, ex)
            stt = flow.status(self.st.s, f_row["token"]) if f_row is not None else {"day": None}
            L.append(f"\n*{name}* {spot:,.1f} → {move}\n 📍 {sr_text(ch)}\n PCR {ch['pcr']} | "
                     f"OI today: {stt.get('day') or '-'}\n ATM IV {ch['atm_iv']} | IV Rank "
                     f"{self.st.iv_rank(name, ch['atm_iv']) or 'building'} | {bu['label'] if bu else ''}\n"
                     f" 📖 {simple_why(td, bu, ch).capitalize()}.")
        pml = flow.premove.summary_line(self.st.s) if getattr(C, "PREMOVE_ENABLED", False) else None
        if pml:
            L.append("\n" + pml)
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
    if mode == "chatid":                  # Telegram check: lists chats that messaged the bot + sends a test
        notify.telegram_check(); return
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
        notify.resend_pending()                      # option-sell messages that failed (e.g. Telegram 429) in an earlier run

        # ENGINE A - option selling (NSE + MCX)
        store = Store()
        bot = Bot(api, master, store)
        if mode == "report":
            bot.report(force=True)
            return
        mcx_on = C.MCX_OPTIONS_ENABLED and at("09:00") <= now <= at("23:59") and bot.mcx_open_today()
        if mode in ("mcx", "view"):          # view only - never an instant call
            if C.FLOW_ENABLED:
                flow.run(bot, mode == "view", mode == "mcx")      # fresh OI snapshot first
            bot.mcx_snapshot() if mode == "mcx" else bot.index_snapshot()
            return
        nse_on = at("09:15") <= now <= at("18:00") and bot.market_open_today()
        if nse_on or mcx_on:
            bot.monitor()                     # exits / adjust alerts for every open call
            if C.FLOW_ENABLED:
                try:
                    flow.run(bot, nse_on, mcx_on)
                    bot.fast_track(getattr(bot, "flow_events", []))
                except Exception as e:
                    traceback.print_exc(); print("flow error", e)
        if nse_on and now <= at("15:31"):
            bot.intraday_scan()
            bot.positional_scan()
        if mcx_on:
            bot.mcx_intraday_scan()
            bot.mcx_positional_scan()
        bot.send_scan_summary()
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

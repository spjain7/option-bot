"""Telegram / GitHub-summary texts for the Crude Oil PAPER engine. Plain text (no Markdown parsing surprises)."""
import pandas as pd
from crude import config as K, data as D

FOOT = "PAPER ONLY – simulated trade, no real order. Rules are unvalidated; not investment advice."


def _t(s, fmt="%d-%b %H:%M"):
    return "—" if not s else pd.Timestamp(s).strftime(fmt)


def _n(x, d=0):
    return "—" if x is None else f"{x:,.{d}f}"


def state_summary(state, rec):
    opens = [p for e in state["engines"].values() for p in e["open"]]
    ltp = None
    return dict(open=[dict(engine=p["engine"], side=p["side"], lots=p["lots"], contract=p["contract"], entry=p["entry"],
                           stop=p["stop"], target=p["target"]) for p in opens],
                realized_today=round(sum(state["day"]["realized"].values()), 2), realized_total=state["realized"],
                equity=round(state["capital"] + state["realized"], 2),
                counts=dict(generated=state["day"]["generated"], blocked=state["day"]["blocked"], ignored=state["day"]["ignored"]))


def _dec_line(name, d):
    if not d:
        return f"{name}: not evaluated"
    head = f"{name}: {d.get('decision')}" + (f" {d.get('side')}" if d.get("side") else "")
    if not d.get("new_candle", True):
        head += " (no new candle since last scan)"
    why = d.get("ignored") or "; ".join((d.get("blocks") or [])[:2]) or "; ".join((d.get("reasons") or [])[:2])
    return head + (f" – {why}" if why else "")


def health(rec, title="HEALTH CHECK"):
    d, c, s = rec["data"], rec.get("contract") or {}, rec.get("state_summary") or {}
    run = rec.get("run") or {}
    sig, tr = c.get("signal") or {}, c.get("trade") or {}
    now = pd.Timestamp(rec["time"])
    api_ok = all(str(v).startswith("ok") for v in rec["api"].values()) and bool(rec["api"])
    dec = rec.get("decisions", {})
    m_i, m_p = (dec.get("intraday") or {}).get("metrics", {}), (dec.get("positional") or {}).get("metrics", {})
    oi = d.get("oi_change") or {}
    L = [f"🛢 CRUDE OIL ENGINE – {title}",
         f"Run: {now:%d-%b-%Y %H:%M:%S} IST · {rec['version']} · {run.get('event', 'manual')} #{run.get('number', '-')}"
         + (f" · started {run['delay_min']:.0f} min after its slot" if run.get("delay_min") is not None else "")
         + (f" · previous run: {run['previous_run'].get('conclusion')}" if run.get("previous_run") else ""),
         "Mode: PAPER (no real orders – there is no order code in this engine)",
         f"Session: {rec['session']} (today closes {D.session_close(now):%H:%M})",
         f"Contract: {sig.get('symbol', '—')} exp {sig.get('expiry', '—')} ({sig.get('days_left', '—')} trading days)"
         + (" [roll window: next month]" if c.get("rolled") else ""),
         f"Paper fills: {tr.get('symbol', '—')} (₹{_n(tr.get('lotsize'))}/pt per lot, tick ₹{tr.get('tick', '—')})",
         f"API: {'✅ all calls ok' if api_ok else '❌ ' + '; '.join(f'{k}: {v}' for k, v in rec['api'].items() if not str(v).startswith('ok'))}",
         f"Last closed candles: 15m {_t(d.get('last_closed_15m'))} · 1h {_t(d.get('last_closed_1h'))} · 3h {_t(d.get('last_closed_3h'))}",
         f"Freshness: 15m candle age {_n(d.get('age_15m_min'), 0)} min · quote age {_n(None if d.get('quote_age_min') is None else max(0.0, d['quote_age_min']), 1)} min"
         + (" ✅" if not rec.get("stale") else " ⚠️ STALE"),
         f"Volume: {d.get('volume', '—')} (today {_n(d.get('day_volume'))} lots) · OI now: {_n(d.get('oi_current'))}",
         f"OI change: {oi.get('label', 'UNAVAILABLE')}" + (f" ({oi.get('d_oi_pct'):+.2f}% in {oi.get('gap_min'):.0f} min)" if oi.get("status") == "OK" else f" – {oi.get('reason', '')}")
         + f" · OI policy: {K.OI_POLICY} · OI history: unavailable (AB1012)",
         f"Roll continuity: {d.get('roll', '—')}",
         f"Data checks: missing 15m today {(d.get('quality') or {}).get('missing_15m_today', 0)} · quote vs candle "
         f"{_n((d.get('quality') or {}).get('quote_vs_candle_atr'), 1)} ATR · "
         + ("; ".join((d.get('quality') or {}).get('blocks', [])) or "timestamps/duplicates OK"),
         f"Risk: drawdown {_n(d.get('drawdown_pct'), 2)}% (lock at −{K.DRAWDOWN_LOCK_PCT:.0%}) · open risk ₹{_n(d.get('open_risk_rs'))}"
         f" (cap {K.MAX_OPEN_RISK_PCT:.1%}) · account daily loss cap {K.ACCOUNT_DAILY_LOSS_PCT:.1%}",
         f"Trend: 1h {m_i.get('trend_1h', '—')} (ADX {_n(m_i.get('adx_1h'), 1)}) · 3h {m_p.get('trend_3h', '—')} (ADX {_n(m_p.get('adx_3h'), 1)})",
         f"RSI(14): 15m {_n(m_i.get('rsi'), 1)} · 3h {_n(m_p.get('rsi'), 1)}  (BUY blocked < 25, SELL blocked > 75)",
         _dec_line("Intraday", dec.get("intraday")),
         _dec_line("Positional", dec.get("positional")),
         f"Today: signals {s.get('counts', {}).get('generated', 0)} · blocked {s.get('counts', {}).get('blocked', 0)} · ignored {s.get('counts', {}).get('ignored', 0)}"]
    if s.get("open"):
        for p in s["open"]:
            L.append(f"Open: {p['engine']} {p['side']} {p['lots']} lot {p['contract']} @ {p['entry']} SL {p['stop']} T {p['target']}")
    else:
        L.append("Open paper positions: none")
    L.append(f"Day P&L: realised ₹{_n(s.get('realized_today'))} · incl. open ₹{_n(d.get('daily_pnl'))} · paper equity ₹{_n(s.get('equity'))}")
    if rec.get("warnings"):
        L.append("Warnings: " + " | ".join(rec["warnings"]))
    le = rec.get("last_error")
    L.append("Errors this run: " + ("; ".join(rec["errors"]) if rec["errors"] else "none")
             + (f" · last recorded error: {_t(le['time'])} {le['error'][:120]}" if le else ""))
    return "\n".join(L)


def entry_msg(p, dec, cs, state):
    sgn = 1 if p["side"] == "BUY" else -1
    ob = dec["plan"].get("obstacle")
    return "\n".join([
        f"🛢 PAPER TRADE – CRUDE {p['engine'].upper()} {p['side']}",
        f"Contract: {p['contract']} (signals on {cs['signal']['symbol']}, exp {p['expiry']})",
        f"Why: " + " · ".join(dec["reasons"]),
        f"OI: {dec.get('oi')}",
        f"Paper fill: {p['entry']:,.0f} (live price {p['ltp_at_entry']:,.0f} + {K.SLIPPAGE_TICKS} ticks slippage)",
        f"Stop: {p['stop']:,.0f} ({p['risk_pts']:.0f} pts = {p['risk_pts'] / p['atr']:.1f} ATR) · Target: {p['target']:,.0f} ({dec['plan']['target_r']}R)",
        "Nearest obstacle: " + ("none (beyond recent range)" if ob is None else f"{ob:,.0f} = {dec['plan']['rr_to_obstacle']:.1f}R"),
        f"Qty: {p['lots']} lot(s) = {p['units']:.0f} bbl · risk ≈ ₹{p['risk_pts'] * p['units']:,.0f} "
        f"({p['risk_pts'] * p['units'] / (state['capital'] + state['realized']):.2%} of paper equity)",
        "Exit plan: " + ("breakeven after +1R, square-off 15 min before close" if p["engine"] == "intraday"
                         else f"trail {K.POS['trail_atr']}×ATR after +1R, exit on 3h close beyond EMA{K.POS['ema_slow']}, flat {K.FLAT_BEFORE_EXPIRY_DAYS} trading days before expiry"),
        FOOT])


def exit_msg(t, state):
    icon = "✅" if t["pnl"] > 0 else "❌"
    return "\n".join([
        f"{icon} PAPER EXIT – CRUDE {t['engine'].upper()} {t['side']} {t['contract']}",
        f"Entry {t['entry']:,.0f} → exit {t['exit']:,.0f} ({t['exit_reason']})",
        f"P&L: ₹{t['pnl']:,.0f} after ₹{t['charges']:,.0f} charges ({t['r']:+.2f}R) · paper equity ₹{state['capital'] + state['realized']:,.0f}",
        FOOT])


def eod(state, rec):
    day = state["day"]
    tr = day["trades"]
    L = [f"🛢 CRUDE PAPER – END OF DAY {pd.Timestamp(day['date']):%d-%b-%Y}",
         f"Signals: {day['generated']} generated · {day['blocked']} blocked · {day['ignored']} ignored",
         f"Closed trades today: {len(tr)}" + (": " + ", ".join(f"{t['engine']} {t['side']} ₹{t['pnl']:,.0f} ({t['reason']})" for t in tr) if tr else ""),
         f"Realised today: intraday ₹{day['realized']['intraday']:,.0f} · positional ₹{day['realized']['positional']:,.0f}",
         f"Open overnight: " + (", ".join(f"{p['engine']} {p['side']} {p['lots']} lot {p['contract']} SL {p['stop']}" for e in state["engines"].values() for p in e["open"]) or "none"),
         f"Paper equity: ₹{state['capital'] + state['realized']:,.0f} (start ₹{state['capital']:,.0f})"]
    for e in ("intraday", "positional"):
        c = state["engines"][e]["closed"]
        if c:
            w = sum(1 for t in c if t["pnl"] > 0)
            L.append(f"{e.title()} all-time: {len(c)} trades · win {w / len(c):.0%} · net ₹{sum(t['pnl'] for t in c):,.0f} · avg {sum(t['r'] for t in c) / len(c):+.2f}R")
    sh = [t.get("shadow") for e in state["engines"].values() for t in e["closed"] if t.get("exit_time", "")[:10] == day["date"] and t.get("shadow")]
    if sh:
        es = [x["entry_slip_pts"] for x in sh]; xs = [x["exit_slip_pts"] for x in sh if x["exit_slip_pts"] is not None]
        L.append(f"Shadow fills: entry vs signal {sum(es) / len(es):+.1f} pts avg" + (f" · exit vs level {sum(xs) / len(xs):+.1f} pts avg" if xs else ""))
    L.append("Errors today: " + (", ".join(a.replace("err:", "") for a in day["alerted"]) or "none"))
    L.append(FOOT)
    return "\n".join(L)


def error_msg(now, title, detail):
    return f"⚠️ CRUDE ENGINE – {title}\n{pd.Timestamp(now):%d-%b-%Y %H:%M} IST\n{detail[:600]}\nMode: PAPER (no orders)"


def markdown(rec, code):
    """GitHub job summary: separates 'workflow ran' from 'bot received fresh data'."""
    fresh = rec["session"] == "OPEN" and not rec.get("stale") and rec["data"].get("age_15m_min") is not None
    status = "❌ FAILED" if code else ("✅ fresh market data" if fresh else "⚪ ran – market closed or no fresh data")
    return f"## Crude Oil PAPER engine – {status}\n\n```\n{health(rec)}\n```\n"

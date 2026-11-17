"""Call ledger + end-of-day call report (one table image per segment: MCX, and Index + Stock).
30-Oct (owner): every OPEN call of any day + every call CLOSED today, with the high / low reached after the call, the current
price (or exit), best / worst ₹ per lot and P&L per lot.

Ledger rows (state["ledger"]) are written when a call is sent and closed when it exits. Option-SELL calls are read from
the option-selling engine's state file (state/state.json of the main branch). The report is sent once after the NSE
close (Index + Stock) and once after the MCX close. ALERTS ONLY – no orders.
"""
import json
import os
from pathlib import Path
import pandas as pd

MCX_RS_PER_POINT = {"CRUDEOIL": 100, "NATURALGAS": 1250, "GOLD": 100, "SILVER": 30, "COPPER": 2500, "ZINC": 5000, "ALUMINIUM": 5000}
OPT_STATE_CANDIDATES = [os.getenv("OPT_STATE_FILE", ""), "/tmp/opt/state/state.json",
                        str(Path(__file__).resolve().parents[1] / "state" / "state.json")]
CALL_TYPE = {"3h": "Positional", "1d": "Positional", "1w": "Positional (weekly)", "1m": "Positional (monthly)"}


def mult_for(name, ex, lot):
    """₹ per 1 point per lot."""
    if ex == "MCX":
        return MCX_RS_PER_POINT.get(name, 1)
    return int(lot or 1)


def add(state, **row):
    row.setdefault("status", "OPEN")
    row.setdefault("date", str(pd.Timestamp(row.get("time")).date()))
    state.setdefault("ledger", []).append(row)
    state["ledger"] = state["ledger"][-500:]
    return row


def track_excursions(state, token, bars, measure):
    """MFE / MAE for every OPEN futures ledger row of this contract, from completed candles after the call time.
    Prices (best_px / worst_px) and R multiples of the initial risk; `measure` says which bars were used (e.g.
    '15-min candle highs/lows'). Rows are updated in place; closed rows keep their last values. Live ledger only –
    paper trades are tracked separately in state['paper']."""
    if bars is None or len(bars) == 0:
        return 0
    n = 0
    tok = str(token)
    for r in state.get("ledger", []):
        if r.get("status") != "OPEN" or str(r.get("mark_key")) != tok or r.get("cat") != "FUTURES":
            continue
        try:
            e, sl = float(r["entry"]), float(r["sl"])
            t0 = pd.Timestamp(r["time"])
        except (TypeError, ValueError, KeyError):
            continue
        s = 1 if r.get("side") == "BUY" else -1
        risk = s * (e - sl)
        after = bars[bars["time"] >= t0.floor("min")]
        if risk <= 0 or after.empty:
            continue
        hi, lo = float(after["high"].max()), float(after["low"].min())
        best = max(hi, r.get("best_px", hi)) if s > 0 else min(lo, r.get("best_px", lo))
        worst = min(lo, r.get("worst_px", lo)) if s > 0 else max(hi, r.get("worst_px", hi))
        r.update(best_px=best, worst_px=worst, mfe_R=round(s * (best - e) / risk, 3), mae_R=round(s * (worst - e) / risk, 3),
                 excursion_measure=r.get("excursion_measure") or measure, excursion_upd=str(after["time"].iloc[-1]))
        if r.get("target") not in (None, ""):
            r["t1_hit"] = bool(r.get("t1_hit")) or s * (best - float(r["target"])) >= 0
        r["stop_touched"] = bool(r.get("stop_touched")) or s * (worst - sl) <= 0
        n += 1
    return n


def heal(state):
    """17-Nov: every open (non-shadow, non-pending) 2h / 3h / 4h / rulebook futures call must have a report-ledger row. Rows
    missing because of the describe() crash (6-Nov to 17-Nov) are re-created from the call record. Returns rows added."""
    have = {r.get("key") for r in state.get("ledger", [])}
    n = 0
    try:
        from alerts import rulebook as RB
        rules = RB.RULES
    except Exception:
        rules = {}
    for r in (state.get("fourh") or {}).get("open", []):
        if r.get("shadow") or r.get("pending") or not r.get("key") or r["key"] in have:
            continue
        rule = rules.get(r.get("rule"), {})
        add(state, key=r["key"], mark_key=str(r.get("token")), seg="MCX" if r.get("ex") == "MCX" else "NSE",
            cat="FUTURES (EXPERIMENTAL)" if rule.get("experimental") else "FUTURES", name=r["name"], symbol=r.get("contract") or r["name"],
            type=f"{str(r.get('tfl', '')).capitalize()} {rule.get('fam', '')}".strip(), side=r["side"], entry=r["entry"],
            sl=r.get("stop"), target=r.get("target"), tick=r.get("tick"), lot=r.get("mult") if r.get("ex") != "MCX" else None,
            mult=r.get("mult"), time=r.get("opened"), healed=True)
        n += 1
    return n


def pnl_rs(r, mark=None):
    px = r.get("exit") if r["status"] == "CLOSED" else mark
    if px is None:
        return None
    s = 1 if r["side"] in ("BUY",) else -1
    return round(s * (float(px) - float(r["entry"])) * float(r.get("mult") or 1))


def _ltp(q):
    if q is None:
        return None
    if isinstance(q, dict):
        v = float(q.get("ltp") or 0)
        return v if v > 0 else None
    return float(q) if q else None


def track(state, quotes, now):
    """Every scan: high / low of the price since the call for every OPEN ledger row (30-Oct, owner: daily report with the high /
    low after each call). Futures rows track the futures; option-buy rows track their underlying (option ≈ 0.5 × move).
    A row opened before today also takes today's full day high / low from the quote (all of it is after the call)."""
    today = now.normalize()
    for r in state.get("ledger", []):
        if r.get("status") != "OPEN":
            continue
        q = quotes.get(r.get("mark_key")) if r.get("mark_key") else None
        p = _ltp(q)
        if p is None:
            continue
        base = float(r["und_entry"]) if r.get("cat") == "OPTION BUY" and r.get("und_entry") is not None else float(r["entry"])
        hi, lo = max(r.get("uhi", base), p), min(r.get("ulo", base), p)
        if isinstance(q, dict) and pd.Timestamp(r.get("time")).normalize() < today:
            dh, dl = float(q.get("high") or 0), float(q.get("low") or 0)
            if dh > 0:
                hi = max(hi, dh)
            if dl > 0:
                lo = min(lo, dl)
        r["uhi"], r["ulo"], r["ulast"], r["uat"] = round(hi, 2), round(lo, 2), round(p, 2), str(now)


def _opt_est(r, und_px):
    s = 1 if r.get("und_side") == "BUY" else -1
    return max(0.05, float(r["entry"]) + 0.5 * s * (und_px - float(r["und_entry"])))


def _hilo(r):
    """(high, low) of the CALLED instrument after the call, or (None, None)."""
    if r.get("uhi") is None:
        return r.get("hi"), r.get("lo")
    if r.get("cat") == "OPTION BUY" and r.get("und_entry") is not None:
        a, b = _opt_est(r, r["uhi"]), _opt_est(r, r["ulo"])
        return max(a, b), min(a, b)
    return r["uhi"], r["ulo"]


def option_sells(today):
    """Option-SELL calls of today (open + closed) from the option-selling engine's state file."""
    for f in OPT_STATE_CANDIDATES:
        if f and Path(f).exists():
            try:
                st = json.loads(Path(f).read_text())
            except Exception:
                continue
            out = []
            for p, status in [(p, "OPEN") for p in st.get("positions", [])] + [(p, "CLOSED") for p in st.get("closed", [])]:
                if str(p.get("opened", ""))[:10] != today and status == "CLOSED":
                    continue
                leg = (p.get("legs") or [{}])[0]
                out.append(dict(seg="MCX" if p.get("exch") == "MCX" else "NSE", cat="OPTION SELL", name=p.get("name"),
                                symbol=leg.get("symbol", ""), type=("Intraday" if p.get("mode") == "intraday" else "Positional"),
                                side="SELL", entry=p.get("credit"), sl=p.get("sl_val"), target=p.get("target_val"),
                                lot=p.get("lot"), status=status, time=p.get("opened"),
                                pnl=p.get("pnl_rs_per_lot") if status == "CLOSED" else None,
                                note=p.get("exit_reason", "") if status == "CLOSED" else ""))
            return out
    return []


OBUY_STATE = os.getenv("OBUY_STATE_FILE", "state/obuy/state.json")


def option_buys(today):
    """Stock option-BUY calls (obuy engine): every open one + those closed today, with the premium high / low after the call."""
    try:
        st = json.loads(Path(OBUY_STATE).read_text())
    except Exception:
        return []
    out = []
    for a, status in [(a, "OPEN") for a in st.get("open", [])] + [(a, "CLOSED") for a in st.get("closed", [])]:
        if status == "CLOSED" and str(a.get("closed", a.get("opened", "")))[:10] != today:
            continue
        lot = a.get("lot")
        cmp_ = a.get("exit") if status == "CLOSED" else a.get("last")
        pnl = a.get("rs_lot") if status == "CLOSED" else (round((float(cmp_) - float(a["entry"])) * float(lot)) if cmp_ and lot else None)
        out.append(dict(seg="NSE", cat="OPTION BUY", name=a.get("name"), symbol=a.get("symbol"),
                        type="Intraday" if a.get("mode") == "intraday" else "Positional", side="BUY", entry=a.get("entry"),
                        sl=a.get("sl"), target=a.get("tg"), lot=lot, mult=lot, status=status, time=a.get("opened"),
                        hi=a.get("hi"), lo=a.get("lo"), cmp=cmp_, pnl=pnl,
                        note=a.get("why_exit", "") if status == "CLOSED" else ""))
    for r in (st.get("sweep15") or {}).get("open", []) + (st.get("sweep15") or {}).get("closed", []):
        if not r.get("send") or r.get("entry") is None:
            continue
        status = "CLOSED" if r.get("status") == "closed" else "OPEN"
        if status == "CLOSED" and str(r.get("closed", ""))[:10] != today:
            continue
        lot = r.get("lot") or 1
        sd = 1 if r.get("side") == "BUY" else -1
        pnl = round(sd * (float(r["exit"]) - float(r["entry"])) * float(lot)) if status == "CLOSED" and r.get("exit") is not None else None
        out.append(dict(seg="NSE", cat="FUTURES", name=r.get("name"), symbol=r.get("contract") or r.get("name"), type="Intraday (15-min sweep)",
                        side=r.get("side"), entry=r.get("entry"), sl=r.get("stop"), target=r.get("target"), lot=lot, mult=lot,
                        status=status, time=r.get("entry_time") or r.get("sweep_time"), hi=r.get("hi"), lo=r.get("lo"),
                        cmp=r.get("exit"), pnl=pnl, note=r.get("exit_reason", "") if status == "CLOSED" else ""))
    return out


def rows_for(state, seg, today, marks):
    """Every OPEN call (any day) + every call CLOSED today, with high / low after the call, CMP (or exit) and P&L per lot."""
    out = []
    for r in state.get("ledger", []):
        if r["seg"] != seg or r["status"] == "VOID" or (r["status"] == "CLOSED" and str(r.get("closed", r["date"]))[:10] != today):
            continue
        mk = _ltp(marks.get(r.get("mark_key"))) if r["status"] == "OPEN" else None
        if mk is None and r["status"] == "OPEN":
            mk = r.get("ulast")
        if r["cat"] == "OPTION BUY" and mk is not None and r.get("und_entry") is not None:
            mk = _opt_est(r, mk)
        hi, lo = _hilo(r)
        cmp_ = r.get("exit") if r["status"] == "CLOSED" else mk
        out.append(dict(r, pnl=pnl_rs(r, mk), hi=hi, lo=lo, cmp=cmp_))
    out += [x for x in option_sells(today) + option_buys(today) if x["seg"] == seg]
    for x in out:                                         # best / worst ₹ per lot reached after the call
        m, s_ = float(x.get("mult") or x.get("lot") or 1), 1 if x.get("side") == "BUY" else -1
        if x.get("hi") is not None and x.get("lo") is not None and x.get("entry") is not None and x.get("cat") != "OPTION SELL":
            e = float(x["entry"])
            fav, adv = (float(x["hi"]), float(x["lo"])) if s_ > 0 else (float(x["lo"]), float(x["hi"]))
            x["best"], x["worst"] = round(s_ * (fav - e) * m), round(s_ * (adv - e) * m)
    return out


def _fmt(v):
    if v is None or v == "":
        return "-"
    try:
        v = float(v)
    except Exception:
        return str(v)
    if v == 0:
        return "0"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


HEAD = ["Called", "Instrument", "Category", "Call type", "Side", "Entry", "SL", "Target", "Lot", "High after", "Low after",
        "CMP / Exit", "Best ₹", "Worst ₹", "P&L ₹/lot", "Status"]


def _cells(r):
    t = pd.Timestamp(r.get("time")) if r.get("time") else None
    pn = r.get("pnl")
    return [f"{t:%d-%b %H:%M}" if t is not None else "-", r.get("symbol") or r["name"], r["cat"], r["type"], r["side"],
            _fmt(r.get("entry")), _fmt(r.get("sl")), _fmt(r.get("target")), str(int(r["lot"])) if r.get("lot") else "-",
            _fmt(r.get("hi")), _fmt(r.get("lo")), _fmt(r.get("cmp")),
            _fmt(r.get("best")), _fmt(r.get("worst")), ("+" if (pn or 0) > 0 else "") + _fmt(pn),
            r["status"] + (f" ({r['note']})" if r.get("note") else "")]


def render(rows, title, path):
    """Table image (PNG). Returns path, or None when matplotlib is not available."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    body = [_cells(r) for r in rows]
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    n_open = sum(r["status"] == "OPEN" for r in rows)
    fig_h = 1.0 + 0.36 * (max(1, len(body)) + 1)
    fig, ax = plt.subplots(figsize=(21, fig_h))
    ax.axis("off")
    ax.set_title(f"{title}   ·   open {n_open} · closed today {len(rows) - n_open}   ·   P&L (closed + open at CMP): "
                 f"{'+' if tot > 0 else ''}₹{tot:,.0f} per lot", fontsize=14, fontweight="bold", loc="left")
    if not body:
        body = [["-", "No open calls and none closed today"] + [""] * (len(HEAD) - 2)]
    t = ax.table(cellText=body, colLabels=HEAD, loc="upper center", cellLoc="center",
                 colWidths=[0.055, 0.13, 0.06, 0.09, 0.035, 0.05, 0.05, 0.05, 0.035, 0.055, 0.055, 0.055, 0.05, 0.05, 0.055, 0.12])
    t.auto_set_font_size(False)
    t.set_fontsize(9)
    t.scale(1, 1.5)
    for (i, j), cell in t.get_celld().items():
        if i == 0:
            cell.set_facecolor("#1f3b57"); cell.set_text_props(color="white", fontweight="bold")
        else:
            row = body[i - 1]
            cell.set_facecolor("#f7f7f2" if i % 2 else "white")
            if j in (12, 13, 14) and row[j] not in ("-", ""):
                cell.set_text_props(color="#0a7a2f" if not row[j].startswith("-") else "#b3261e", fontweight="bold" if j == 14 else "normal")
            if j == 4:
                cell.set_text_props(color="#0a7a2f" if row[4] == "BUY" else "#b3261e")
    plt.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def text_table(rows, title):
    L = [title]
    for r in rows:
        c = _cells(r)
        L.append(f"• {c[0]} {c[1]} · {r['cat']} · {r['type']} · {r['side']} {c[5]} · SL {c[6]} · T {c[7]} · lot {c[8]}\n"
                 f"   high {c[9]} · low {c[10]} · {'exit' if r['status'] == 'CLOSED' else 'CMP'} {c[11]} · best {c[12]} · worst {c[13]} · "
                 f"P&L {c[14]} · {c[15]}")
    if len(rows) == 0:
        L.append("No open calls and none closed today.")
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    L.append(f"Total P&L: ₹{tot:,.0f} per lot (closed at exit, open at the current price; ₹ per lot = 1 lot; "
             "option-buy rows on futures calls ≈ 0.5 × futures move)")
    return "\n".join(L)


# ───────────── 17-Nov-2026 (owner): clean INDEX + STOCK layout ─────────────
# Text: one block per call, every value on its own line, basis (swing 4-hour / positional weekly ...) on its own line,
# open and closed-today calls in separate sections. Image: no internal call-type / category columns, plus the closed-call
# history of index + stock futures.
TEXT_LIMIT = 3500          # Telegram cuts a message at 4,000 characters – long reports are split into several messages


def _rs(v):
    if v is None:
        return "–"
    v = float(v)
    return f"{'+' if v > 0 else '−' if v < 0 else ''}₹{abs(v):,.0f}"


def _px(v):
    return "–" if v in (None, "") else _fmt(v)


def basis(r):
    """customer-facing basis of a call (no internal strategy codes)."""
    t = str(r.get("type") or "")
    tl = t.lower()
    for k in ("weekly", "monthly"):
        if k in tl:
            return f"Positional · {k} chart"
    for k in ("1-hour", "2-hour", "3-hour", "4-hour"):
        if k in tl:
            return f"Swing · {k} chart"
    if "15-min" in tl:
        return "Intraday · 15-min chart"
    if tl.startswith("intraday"):
        return "Intraday"
    if tl.startswith("daily") or tl.startswith("positional"):
        return "Positional · daily chart"
    return t.split(" ")[0] if t else "–"


def instrument(r):
    if r.get("cat") == "FUTURES" or str(r.get("cat", "")).startswith("FUTURES"):
        return f"{r['name']} FUT"
    return f"{r.get('symbol') or r['name']} ({'option buy' if r.get('cat') == 'OPTION BUY' else 'option sell'})"


def _pct(r):
    try:
        s_ = 1 if r["side"] == "BUY" else -1
        return 100 * s_ * (float(r["cmp"]) - float(r["entry"])) / float(r["entry"])
    except (TypeError, ValueError, KeyError, ZeroDivisionError):
        return None


def result_label(r):
    n = str(r.get("note") or "").lower()
    if "cancel" in n or "skip" in n:
        return "🚫 No trade (opened past the entry)"
    if "target" in n:
        return "🎯 Target hit"
    if "trail" in n:
        return "🔁 Trailing stop hit"
    if "stop" in n or n.startswith("sl"):
        return "🛑 Stop-loss hit"
    if "time" in n or "expiry" in n:
        return "⏱ Time / expiry exit"
    return f"Closed ({r.get('note')})" if r.get("note") else "Closed"


def call_block(i, r):
    t = pd.Timestamp(r.get("time")) if r.get("time") else None
    side = f"{'🟢' if r['side'] == 'BUY' else '🔴'} {r['side']}"
    lot = f" · lot {int(r['lot'])}" if r.get("lot") else ""
    L = [f"{i}. {instrument(r)} · {side}{lot}",
         f"🗓 Issued : {t:%d-%b %H:%M}" if t is not None else "🗓 Issued : –"]
    if r["status"] == "CLOSED" and r.get("closed"):
        L[-1] += f" · closed {pd.Timestamp(r['closed']):%d-%b %H:%M}"
    L += [f"📌 Basis  : {basis(r)}",
          f"💰 Entry  : {_px(r.get('entry'))}",
          f"🛑 SL     : {_px(r.get('sl'))}   🎯 Target : {_px(r.get('target'))}",
          f"📈 High   : {_px(r.get('hi'))}",
          f"📉 Low    : {_px(r.get('lo'))}",
          f"💹 {'Exit' if r['status'] == 'CLOSED' else 'CMP '}   : {_px(r.get('cmp'))}",
          f"✅ Best profit  : {_rs(r.get('best'))}",
          f"⚠️ Highest loss : {_rs(r.get('worst'))}"]
    pn, pc = r.get("pnl"), _pct(r)
    pct = f" ({pc:+.1f}%)" if pc is not None else ""
    if r["status"] == "CLOSED":
        L.append(f"{result_label(r)} : {_rs(pn)}{pct}")
    elif pn is None:
        L.append("⚪ Status : price not available")
    else:
        L.append(f"{'🟢 In profit' if pn > 0 else '🔴 In loss' if pn < 0 else '⚪ Flat'} : {_rs(pn)}{pct}")
    return "\n".join(L)


def text_nse(rows, title):
    """-> list of messages (each under TEXT_LIMIT characters)."""
    op = [r for r in rows if r["status"] == "OPEN"]
    cl = [r for r in rows if r["status"] == "CLOSED"]
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    in_p = sum(1 for r in op if (r.get("pnl") or 0) > 0)
    head = (f"📊 {title}\n"
            f"Open {len(op)} ({in_p} in profit) · Closed today {len(cl)}\n"
            f"P&L (open at CMP + closed today): {_rs(tot)} per lot")
    parts = [head]
    if op:
        parts.append("━━━━━━━━━━━━━━\n🟢 OPEN CALLS\n━━━━━━━━━━━━━━")
        parts += [call_block(i, r) for i, r in enumerate(op, 1)]
    if cl:
        parts.append("━━━━━━━━━━━━━━\n📕 CLOSED TODAY\n━━━━━━━━━━━━━━")
        parts += [call_block(i, r) for i, r in enumerate(cl, 1)]
    if not rows:
        parts.append("No open calls and none closed today.")
    parts.append("₹ per 1 lot · open calls valued at the current price · alert only, not investment advice")
    out, cur = [], ""
    for p_ in parts:
        if cur and len(cur) + len(p_) + 2 > TEXT_LIMIT:
            out.append(cur); cur = ""
        cur = f"{cur}\n\n{p_}" if cur else p_
    if cur:
        out.append(cur)
    return out


def history_nse(state, limit=40):
    """closed index + stock FUTURES calls (newest first) with high / low after the call, exit, best / worst and P&L per lot."""
    out = []
    for r in reversed(state.get("ledger", [])):
        if r.get("seg") != "NSE" or r.get("cat") != "FUTURES" or r.get("status") != "CLOSED":
            continue
        hi, lo = _hilo(r)
        x = dict(r, pnl=pnl_rs(r), hi=hi, lo=lo, cmp=r.get("exit"))
        try:
            m, s_ = float(x.get("mult") or x.get("lot") or 1), 1 if x["side"] == "BUY" else -1
            if hi is not None and lo is not None:
                e = float(x["entry"]); fav, adv = (float(hi), float(lo)) if s_ > 0 else (float(lo), float(hi))
                x["best"], x["worst"] = round(s_ * (fav - e) * m), round(s_ * (adv - e) * m)
        except (TypeError, ValueError):
            pass
        if result_label(x).startswith("🚫"):                 # no trade: no position, so no excursion / P&L to show
            x.update(best=None, worst=None, hi=None, lo=None, pnl=None, cmp=None)
        out.append(x)
        if len(out) >= limit:
            break
    return out


HEAD_NSE = ["Issued", "Instrument", "Side", "Entry", "SL", "Target", "Lot", "High", "Low", "CMP / Exit", "Best ₹", "Worst ₹",
            "P&L ₹/lot", "Status"]
HEAD_HIST = ["Issued", "Closed", "Instrument", "Side", "Entry", "Exit", "High", "Low", "Best ₹", "Worst ₹", "P&L ₹/lot", "Result"]


def _cells_nse(r):
    t = pd.Timestamp(r.get("time")) if r.get("time") else None
    pn = r.get("pnl")
    st_ = "OPEN" if r["status"] == "OPEN" else result_label(r).split(" ", 1)[1]
    return [f"{t:%d-%b %H:%M}" if t is not None else "-", instrument(r), r["side"], _fmt(r.get("entry")), _fmt(r.get("sl")),
            _fmt(r.get("target")), str(int(r["lot"])) if r.get("lot") else "-", _fmt(r.get("hi")), _fmt(r.get("lo")), _fmt(r.get("cmp")),
            _fmt(r.get("best")), _fmt(r.get("worst")), ("+" if (pn or 0) > 0 else "") + _fmt(pn), st_]


def _cells_hist(r):
    t = pd.Timestamp(r.get("time")) if r.get("time") else None
    c = pd.Timestamp(r.get("closed")) if r.get("closed") else None
    pn = r.get("pnl")
    return [f"{t:%d-%b %H:%M}" if t is not None else "-", f"{c:%d-%b %H:%M}" if c is not None else "-", instrument(r), r["side"],
            _fmt(r.get("entry")), _fmt(r.get("cmp")), _fmt(r.get("hi")), _fmt(r.get("lo")), _fmt(r.get("best")), _fmt(r.get("worst")),
            ("+" if (pn or 0) > 0 else "") + _fmt(pn), result_label(r).split(" ", 1)[1]]


def _style(t, body, pnl_cols, side_col):
    t.auto_set_font_size(False); t.set_fontsize(9); t.scale(1, 1.5)
    for (i, j), cell in t.get_celld().items():
        if i == 0:
            cell.set_facecolor("#1f3b57"); cell.set_text_props(color="white", fontweight="bold")
            continue
        row = body[i - 1]
        cell.set_facecolor("#f7f7f2" if i % 2 else "white")
        if j in pnl_cols and row[j] not in ("-", ""):
            cell.set_text_props(color="#b3261e" if row[j].startswith("-") else "#0a7a2f", fontweight="bold" if j == pnl_cols[-1] else "normal")
        if j == side_col:
            cell.set_text_props(color="#0a7a2f" if row[j] == "BUY" else "#b3261e", fontweight="bold")


def render_nse(rows, hist, title, path):
    """two tables in one image: open + closed today, then the closed-call history (index + stock futures)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    b1 = [_cells_nse(r) for r in rows] or [["-", "No open calls and none closed today"] + [""] * (len(HEAD_NSE) - 2)]
    b2 = [_cells_hist(r) for r in hist] or [["-", "-", "No closed calls yet"] + [""] * (len(HEAD_HIST) - 3)]
    h1, h2 = 0.36 * (len(b1) + 1) + 0.6, 0.36 * (len(b2) + 1) + 0.6
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(19, h1 + h2), gridspec_kw=dict(height_ratios=[h1, h2], hspace=0.02))
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    n_open = sum(r["status"] == "OPEN" for r in rows)
    for ax in (a1, a2):
        ax.axis("off")
    a1.set_title(f"{title}   ·   open {n_open} · closed today {len(rows) - n_open}   ·   P&L (open at CMP + closed today): "
                 f"{'+' if tot > 0 else ''}₹{tot:,.0f} per lot", fontsize=14, fontweight="bold", loc="left")
    t1 = a1.table(cellText=b1, colLabels=HEAD_NSE, loc="upper center", cellLoc="center",
                  colWidths=[0.07, 0.13, 0.045, 0.06, 0.06, 0.06, 0.045, 0.06, 0.06, 0.07, 0.065, 0.065, 0.075, 0.11])
    _style(t1, b1, [10, 11, 12], 2)
    wins = sum(1 for r in hist if (r.get("pnl") or 0) > 0); losses = sum(1 for r in hist if (r.get("pnl") or 0) < 0)
    flat = sum(1 for r in hist if r.get("pnl") == 0)
    htot = sum(float(r["pnl"]) for r in hist if r.get("pnl") is not None)
    a2.set_title(f"CLOSED CALLS – index + stock futures (last {len(hist)})   ·   won {wins} · lost {losses} · "
                 f"no trade {len(hist) - wins - losses - flat}   ·   total {'+' if htot > 0 else ''}₹{htot:,.0f} per lot",
                 fontsize=13, fontweight="bold", loc="left")
    t2 = a2.table(cellText=b2, colLabels=HEAD_HIST, loc="upper center", cellLoc="center",
                  colWidths=[0.075, 0.075, 0.13, 0.045, 0.065, 0.065, 0.065, 0.065, 0.07, 0.07, 0.08, 0.17])
    _style(t2, b2, [8, 9, 10], 3)
    plt.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def build(state, seg, now, marks, out_dir):
    today = str(now.date())
    rows = sorted(rows_for(state, seg, today, marks), key=lambda r: (r["status"] != "OPEN", str(r.get("time"))))
    title = f"{'MCX' if seg == 'MCX' else 'INDEX + STOCK'} CALLS – {now:%d %b %Y} (all open + closed today)"
    if seg != "MCX":                                       # 17-Nov owner layout (index + stock)
        try:
            heal(state)
        except Exception as e_:
            print(f"[report] ledger heal skipped: {type(e_).__name__}: {e_}")
        rows = sorted(rows_for(state, seg, today, marks), key=lambda r: (r["status"] != "OPEN", str(r.get("time"))))
        title = f"INDEX + STOCK CALLS – {now:%d %b %Y}"
        png = render_nse(rows, history_nse(state), title, Path(out_dir) / f"report_{seg}.png")
        return ([f"PHOTO::{png}::{title}"] if png else []) + text_nse(rows, title)
    png = render(rows, title, Path(out_dir) / f"report_{seg}.png")
    txt = text_table(rows, "📊 " + title)
    return ([f"PHOTO::{png}::{title}"] if png else []) + [txt]

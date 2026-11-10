"""NSE CASH POSITIONAL BUY – scored 50-day breakout (EXPERIMENTAL, live from 10-Nov-2026 on the owner's instruction
"we need all calls live first"). BUY ONLY. ALERTS ONLY.

Research: exp/cash-equity-engine, research/cashq (buy_events.py / buy_score.py / BUY_ENGINE.md), official NSE bhavcopies
2005-26, delisted stocks included, delivery costs 0.393 %. Score >= 70 after costs: 2020-26 461 trades, 34.5 % winners,
T1 reached 48.8 %, +0.35R per trade, PF 1.65; 2015-19 +0.28R; 2005-14 +0.44R. WEAK SPOTS: only ~1 trade in 3 wins (a few
large winners pay for many small losses) and 2024 −0.55R, 2025 −0.22R, 2026 −0.06R. No live record yet -> EXPERIMENTAL.

Rules (identical to the research code; parity checked in tests/test_cash_breakout.py):
  universe  60-session median turnover (to yesterday) >= ₹25 cr, close >= ₹50, >= 250 sessions of history
  signal    first close above the 50-session high in 5 sessions
  score     relative strength (126-day return percentile) >= .85 -> 35 / >= .70 -> 22 / >= .50 -> 10
            ADX(14) >= 30 -> 25 / >= 22 -> 15 / >= 16 -> 6 · ATR10/ATR50 yesterday <= .85 -> 20 / <= 1.0 -> 10
            close not in the top 15 % of the day's range -> 10 · share of stocks above EMA50 >= .55 -> 10 / >= .40 -> 5
  call      score >= MIN_SCORE (70), only when no earlier breakout trade of the stock is still running (busy_mask).
            Entry next session's open,
            stop 3 ATR below the entry, T1 +1R, T2 +2R (information), exit on a close below EMA50 (sell next open) or after
            250 sessions. Tracked daily: high / low since entry, T1 / T2 / stop / exit, P&L for 100 shares.
"""
import numpy as np
import pandas as pd

MIN_TURNOVER, MIN_PRICE, MIN_HIST = 25e7, 50.0, 250
MIN_SCORE, STOP_ATR, MAX_SESSIONS, QTY = 70, 3.0, 250, 100
VERSION = "cash-bo-0.1 (CASHQ-BUY, experimental)"
WARN = "Alert only – no auto trade. Not investment advice."
LINE = "━━━━━━━━━━━━━━"


def _w(x, n):
    return x.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def _atr(h, l, c, n):
    pc = c.shift(1)
    return _w(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())), n)


def _adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0); mdm = dn.where((dn > up) & (dn > 0), 0.0)
    a = _atr(h, l, c, n)
    pdi, mdi = 100 * _w(pdm, n) / a, 100 * _w(mdm, n) / a
    return _w(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), n)


def wide(A):
    idx = pd.DatetimeIndex(sorted({t for d in A.values() for t in d["time"]}))
    W = {f: pd.DataFrame({k: pd.Series(d[f].values.astype(float), index=pd.DatetimeIndex(d["time"])) for k, d in A.items()}).reindex(idx)
         for f in ("open", "high", "low", "close", "volume")}
    W["symbol"] = pd.Series({k: str(d["symbol"].iloc[-1]) for k, d in A.items()})
    return W


def features(W):
    o, h, l, c, v = (W[x] for x in ("open", "high", "low", "close", "volume"))
    F = dict(W)
    to60 = (c * v).rolling(60, min_periods=40).median().shift(1)
    F["elig"] = (to60 >= MIN_TURNOVER) & (c >= MIN_PRICE) & (c.notna().cumsum() >= MIN_HIST) & c.notna()
    F["turnover_cr"] = to60 / 1e7
    F["atr"] = _atr(h, l, c, 14)
    F["adx"] = _adx(h, l, c, 14)
    F["ema50"] = c.ewm(span=50, adjust=False, min_periods=50).mean()
    hi50 = c > h.shift(1).rolling(50).max()
    F["signal"] = hi50 & ~hi50.shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool) & F["elig"]
    F["rs126"] = (c / c.shift(126) - 1).where(F["elig"]).rank(axis=1, pct=True)
    F["tight"] = (_atr(h, l, c, 10) / _atr(h, l, c, 50)).shift(1)
    F["clv"] = (c - l) / (h - l).replace(0, np.nan)
    F["breadth50"] = ((c > F["ema50"]) & F["elig"]).sum(axis=1) / F["elig"].sum(axis=1).replace(0, np.nan)
    return F


def busy_mask(F):
    """Research parity: the backtest holds ONE position per stock – a breakout signal that comes while an earlier breakout
    trade of the same stock is still running (any score) was never a trade there (2026: 241 signals with score >= 70 vs 64
    tested trades). Replays every signal of the loaded window with the research exits (stop 3 ATR, close below EMA50 ->
    next open, 250 sessions) and returns a frame that is True where a signal must be ignored."""
    sig = F["signal"]
    out = pd.DataFrame(False, index=sig.index, columns=sig.columns)
    n = len(sig.index)
    for k in sig.columns[sig.values.any(axis=0)]:
        s = sig[k].values
        o, h, l, c, e, a = (F[f][k].values for f in ("open", "high", "low", "close", "ema50", "atr"))
        b = np.zeros(n, bool)
        t = 0
        while t < n - 1:
            if not s[t] or not a[t] > 0:
                t += 1; continue
            en = t + 1
            if not (h[en] > l[en]):                       # locked / no trade next session: no entry
                t += 1; continue
            st_ = o[en] - STOP_ATR * a[t]
            j = en
            while j < n:
                if np.isnan(o[j]):
                    j += 1; continue
                if (j > en and o[j] <= st_) or l[j] <= st_ or j - en + 1 >= MAX_SESSIONS:
                    break
                if c[j] < e[j]:
                    if j + 1 < n and not np.isnan(o[j + 1]):
                        j += 1; break
                j += 1
            j = min(j, n - 1)
            b[en:j + 1] = True                            # signals from the entry day to the exit day are ignored
            t = j + 1
        out[k] = b
    return out


def score_parts(rs, adx, tight, clv, breadth):
    p = dict(rs=35 if rs >= 0.85 else 22 if rs >= 0.70 else 10 if rs >= 0.50 else 0,
             trend=25 if adx >= 30 else 15 if adx >= 22 else 6 if adx >= 16 else 0,
             base=20 if tight <= 0.85 else 10 if tight <= 1.0 else 0,
             entry=10 if clv <= 0.85 else 0,
             breadth=10 if breadth >= 0.55 else 5 if breadth >= 0.40 else 0)
    return p, sum(p.values())


def candidates(F, day=None):
    """All signals of `day` (default: the last session) with their score, best first."""
    idx = F["close"].index
    i = len(idx) - 1 if day is None else idx.get_loc(pd.Timestamp(day))
    if "busy" not in F:
        F["busy"] = busy_mask(F)
    row = F["signal"].iloc[i] & ~F["busy"].iloc[i]
    out = []
    for k in row.index[row.values]:
        g = lambda f: float(F[f][k].iloc[i])
        vals = dict(rs=g("rs126"), adx=g("adx"), tight=g("tight"), clv=g("clv"), breadth=float(F["breadth50"].iloc[i]))
        if any(not np.isfinite(x) for x in vals.values()) or not g("atr") > 0:
            continue
        parts, sc = score_parts(**vals)
        out.append(dict(key=k, symbol=F["symbol"][k], day=str(idx[i].date()), close=round(g("close"), 2), atr=round(g("atr"), 2),
                        ema50=round(g("ema50"), 2), score=int(sc), parts=parts, rs126=round(vals["rs"], 3), adx=round(vals["adx"], 1),
                        tight=round(vals["tight"], 2), clv=round(vals["clv"], 2), breadth50=round(vals["breadth"], 2),
                        turnover_cr=round(g("turnover_cr"), 1)))
    return sorted(out, key=lambda r: -r["score"])


def _f(x):
    return f"{x:,.2f}"


def call_msgs(c):
    risk = STOP_ATR * c["atr"]
    ref = c["close"]
    card = "\n".join([
        f"🟢 BUY  {c['symbol']} (NSE cash)  ·  Positional · 🧪 EXPERIMENTAL – scored 50-day breakout",
        LINE,
        f"Entry   : next session's open (reference close {_f(ref)}) – as in the backtest, whatever the gap",
        f"SL      : ~{_f(ref - risk)}  (3 ATR = {_f(risk)} below the actual entry – exact level sent after the open)",
        f"Target  : T1 ~{_f(ref + risk)} (1R) · T2 ~{_f(ref + 2 * risk)} (2R) · then trail: exit on a close below the 50-day EMA",
        f"Qty     : {QTY} shares ≈ ₹{QTY * ref:,.0f} · risk ≈ ₹{QTY * risk:,.0f} ({100 * risk / ref:.1f} %)  ·  delivery (CNC)"])
    p = c["parts"]
    why = "\n".join([
        f"📌 WHY – {c['symbol']} BUY (positional)", LINE,
        f"• Chart   : daily close {_f(ref)} on {pd.Timestamp(c['day']):%d-%b} – first close above the 50-day high in 5 sessions",
        f"• Score   : {c['score']} / 100 (rank, not a probability)",
        f"• RS      : stronger than {100 * c['rs126']:.0f} % of liquid stocks over 6 months ({p['rs']}/35)",
        f"• Trend   : ADX {c['adx']:.0f} ({p['trend']}/25) · base before the breakout: ATR10/50 {c['tight']:.2f} ({p['base']}/20)",
        f"• Entry   : close at {100 * c['clv']:.0f} % of the day's range ({p['entry']}/10) · market breadth {100 * c['breadth50']:.0f} % above EMA50 ({p['breadth']}/10)",
        "• Exit    : SL, or sell at the next open after a daily close below the 50-day EMA · average hold ~7 weeks · max 250 sessions",
        "• Record  : BACKTEST ONLY, after costs – score ≥ 70 in 2020-26: 461 trades, 34 % winners, T1 reached 49 %, +0.35R avg, "
        "PF 1.65; 2024-26 negative. About 1 trade in 3 wins – the result depends on a few big winners. No live record yet.",
        WARN])
    return [card, why]


def _row(F, key, day):
    """(open, high, low, close, ema50) of `key` on `day` from the adjusted panel, or None."""
    if key not in F["close"].columns or pd.Timestamp(day) not in F["close"].index:
        return None
    i = F["close"].index.get_loc(pd.Timestamp(day))
    v = [float(F[f][key].iloc[i]) for f in ("open", "high", "low", "close", "ema50")]
    return None if not np.isfinite(v[0]) else v


def step(st, F, msgs):
    """One evening run: entries of pending calls, tracking of open calls, new calls. st: dict(pending, open, closed, seen)."""
    for k in ("pending", "open", "closed", "seen"):
        st.setdefault(k, [])
    idx = F["close"].index
    last = idx[-1]
    # 1. entries (first session after the signal day)
    keep = []
    for p in st["pending"]:
        after = idx[idx > pd.Timestamp(p["day"])]
        r = _row(F, p["key"], after[0]) if len(after) else None
        if not len(after):
            keep.append(p); continue
        if r is None:
            msgs.append(f"⛔ CANCELLED – {p['symbol']} BUY (cash positional, EXPERIMENTAL): no trade on {after[0]:%d-%b}. {WARN}")
            continue
        o = r[0]
        risk = STOP_ATR * p["atr"]
        rec = dict(p, entry=round(o, 2), entry_day=str(after[0].date()), stop=round(o - risk, 2), risk=round(risk, 2),
                   t1=round(o + risk, 2), t2=round(o + 2 * risk, 2), hi=round(o, 2), lo=round(o, 2), last=round(o, 2), sessions=0,
                   checked=str(pd.Timestamp(p["day"]).date()), t1_hit=False, t2_hit=False, exit_next_open=False, version=VERSION)
        st["open"].append(rec)
        msgs.append(f"⚡ ENTRY – {p['symbol']} BUY (cash positional, EXPERIMENTAL) filled at the open {_f(o)} on {after[0]:%d-%b}\n"
                    f"SL {_f(rec['stop'])} · T1 {_f(rec['t1'])} · T2 {_f(rec['t2'])} · then trail below the 50-day EMA · "
                    f"risk ₹{QTY * risk:,.0f} per {QTY} shares. {WARN}")
    st["pending"] = keep
    # 2. tracking
    still = []
    for r in st["open"]:
        days = idx[idx > pd.Timestamp(r["checked"])]
        done = None
        for d in days:
            b = _row(F, r["key"], d)
            if b is None:
                continue
            o, h, l, c, e50 = b
            r["checked"] = str(d.date())
            if r.get("exit_next_open") and str(d.date()) > r["entry_day"]:
                done = (o, d, "close below the 50-day EMA – sold at the next open"); break
            r["sessions"] += 1
            r["hi"], r["lo"], r["last"] = round(max(r["hi"], h), 2), round(min(r["lo"], l), 2), round(c, 2)
            if str(d.date()) > r["entry_day"] and o <= r["stop"]:
                done = (o, d, "stop-loss (gap down at the open)"); break
            if l <= r["stop"]:
                done = (r["stop"], d, "stop-loss"); break
            for tk, lab in (("t1", "T1 (1R)"), ("t2", "T2 (2R)")):
                if not r[f"{tk}_hit"] and h >= r[tk]:
                    r[f"{tk}_hit"] = True
                    msgs.append(f"🎯 {lab} reached – {r['symbol']} BUY (cash positional, EXPERIMENTAL): high {_f(h)} ≥ {_f(r[tk])} on "
                                f"{d:%d-%b}. Trail continues (exit on a close below the 50-day EMA). {WARN}")
            if r["sessions"] >= MAX_SESSIONS:
                done = (c, d, "time exit (250 sessions)"); break
            if np.isfinite(e50) and c < e50:
                r["exit_next_open"] = True
                msgs.append(f"⚠️ EXIT SIGNAL – {r['symbol']} BUY (cash positional, EXPERIMENTAL): close {_f(c)} below the 50-day EMA "
                            f"{_f(e50)} on {d:%d-%b} → sell at the next session's open. {WARN}")
        if done:
            px, d, why = done
            pnl = (px - r["entry"]) * QTY
            R = (px - r["entry"]) / r["risk"]
            r.update(exit=round(px, 2), exit_day=str(d.date()), exit_reason=why, R=round(R, 3), pnl_100=round(pnl))
            st["closed"] = (st["closed"] + [r])[-400:]
            msgs.append(f"{'✅' if pnl > 0 else '❌'} EXIT – {r['symbol']} BUY (cash positional, EXPERIMENTAL) at {_f(px)} on {d:%d-%b}: {why}\n"
                        f"Entry {_f(r['entry'])} · {R:+.2f}R · ₹{pnl:+,.0f} per {QTY} shares before costs · high {_f(r['hi'])} / low {_f(r['lo'])} "
                        f"after entry · {r['sessions']} sessions. {WARN}")
        else:
            still.append(r)
    st["open"] = still
    # 3. new calls on the last session
    held = {r["key"] for r in st["open"]} | {p["key"] for p in st["pending"]}
    cands = candidates(F)
    st["last_candidates"] = [dict(symbol=c["symbol"], score=c["score"], close=c["close"], day=c["day"]) for c in cands]
    for c in cands:
        sid = f"{c['key']}|{c['day']}"
        if c["score"] < MIN_SCORE or sid in st["seen"] or c["key"] in held:
            continue
        st["seen"] = (st["seen"] + [sid])[-2000:]
        st["pending"].append(c)
        msgs.extend(call_msgs(c))
    st["asof"] = str(last.date())
    return st

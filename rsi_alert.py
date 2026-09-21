"""
ENGINE B - INDEPENDENT 1-HOUR RSI EXTREME ALERTS  (NSE indices + MCX futures)

Purely informational. It does NOT import, feed, or get fed by the option-selling engine:
no score, no direction, no strike, no entry/SL/target. Shares only market data + Telegram.
"""
import json
from pathlib import Path
import pandas as pd
import config as C
import notify
from angel import now_ist

STATE_FILE = Path(__file__).parent / "state" / "rsi_state.json"
SESSION_CLOSE = {"NSE": "15:30", "MCX": "23:55"}
SESSION_OPEN = {"NSE": "09:15", "MCX": "09:00"}


def rsi(close, n):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, 1e-9))


def zone(v):
    return "OVERSOLD" if v < C.RSI_OVERSOLD else "OVERBOUGHT" if v > C.RSI_OVERBOUGHT else None


def history_stats(df, r, z):
    """What happened after past ENTRIES into the same zone (statistics only)."""
    zones = r.map(zone)
    entries = [i for i in range(1, len(df) - 1) if zones.iloc[i] == z and zones.iloc[i - 1] != z]
    out = {}
    for label, bars in (("+3h", 3), ("+6h", 6)):
        rets = [(df["close"].iloc[i + bars] / df["close"].iloc[i] - 1) * 100 for i in entries if i + bars < len(df) - 1]
        if len(rets) >= 3:
            s = pd.Series(rets)
            out[label] = (round(s.mean(), 2), round(s.median(), 2), round((s > 0).mean() * 100), len(s))
    return out


def _instruments(master):
    out = [("NSE", n, C.INDEX_TOKENS[n], n) for n in C.RSI_NSE if n in C.INDEX_TOKENS]
    today = now_ist().normalize()
    mcx = master[(master["exch_seg"] == "MCX") & (master["instrumenttype"] == "FUTCOM")]
    for n in C.RSI_MCX:
        m = mcx[(mcx["name"] == n) & (mcx["expiry_dt"] >= today + pd.Timedelta(days=3))].sort_values("expiry_dt")
        if not m.empty:
            out.append(("MCX", n, str(m.iloc[0]["token"]), m.iloc[0]["symbol"]))
    return out


def run(api, master):
    st = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    st.setdefault("done", {}); st.setdefault("log", [])
    now = now_ist()
    today = now.normalize()
    for exch, name, tok, label in _instruments(master):
        h, m = map(int, SESSION_OPEN[exch].split(":"))
        if now < today + pd.Timedelta(hours=h, minutes=m + 60):
            continue
        df = api.candles(exch, tok, "ONE_HOUR", now - pd.Timedelta(days=90), now)
        if df is None or len(df) < C.RSI_PERIOD + 5:
            continue
        ch, cm = map(int, SESSION_CLOSE[exch].split(":"))
        end = df["time"].map(lambda t: min(t + pd.Timedelta(hours=1), t.normalize() + pd.Timedelta(hours=ch, minutes=cm)))
        df = df[end <= now].reset_index(drop=True)                    # completed candles only
        if df.empty or df["time"].iloc[-1].normalize() != today:
            continue
        key = f"{exch}|{name}|{df['time'].iloc[-1]:%Y-%m-%d %H:%M}"
        if key in st["done"]:
            continue
        st["done"][key] = f"{today:%Y-%m-%d}"

        r = rsi(df["close"], C.RSI_PERIOD)
        cur, prev = float(r.iloc[-1]), float(r.iloc[-2])
        z, zp = zone(cur), zone(prev)
        if not z:
            continue
        entered = zp != z
        if C.RSI_ALERT_MODE == "entry" and not entered:
            continue
        hours = 1
        while hours < len(r) and zone(float(r.iloc[-1 - hours])) == z:
            hours += 1
        icon = "🔵" if z == "OVERSOLD" else "🟠"
        cond = f"RSI < {C.RSI_OVERSOLD}" if z == "OVERSOLD" else f"RSI > {C.RSI_OVERBOUGHT}"
        tag = "" if C.RSI_ALERT_MODE == "every_hour" else (" – ENTERED" if entered else f" – STILL ({hours}h)")
        L = [f"{icon} *RSI {z}*{tag}", f"{name} ({exch}) | 1H", "",
             f"CMP: {df['close'].iloc[-1]:,.2f}", f"RSI({C.RSI_PERIOD}): *{cur:.1f}*  (previous {prev:.1f})",
             f"Condition: {cond}  | Candle {df['time'].iloc[-1]:%d %b %H:%M}"]
        if C.RSI_SHOW_HISTORY:
            hs = history_stats(df, r, z)
            if hs:
                L.append("\n_Past 90 days after entering this zone (stats only):_")
                for k, (avg, med, pos, n) in hs.items():
                    L.append(f" {k}: avg {avg:+}% | median {med:+}% | up {pos}% of {n} cases")
        L += ["", "📖 " + ("Price has fallen very fast in the last few hours (sellers exhausted?). "
                          "It can bounce – or keep falling in a strong downtrend." if z == "OVERSOLD" else
                          "Price has risen very fast in the last few hours (buyers exhausted?). "
                          "It can cool off – or keep rising in a strong uptrend."),
              "_Independent RSI alert. Not an option-selling signal. No trade recommendation._"]
        notify.send("\n".join(L))
        st["log"].append({"time": str(df["time"].iloc[-1]), "exch": exch, "name": name, "rsi": round(cur, 1),
                          "prev": round(prev, 1), "status": z, "price": float(df["close"].iloc[-1])})

    cutoff = f"{today - pd.Timedelta(days=5):%Y-%m-%d}"
    st["done"] = {k: v for k, v in st["done"].items() if v >= cutoff}
    st["log"] = st["log"][-500:]
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=1))

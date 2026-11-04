"""MCX news & event context (owner 4-Nov-2026: "connect futures calls with live news and possible impact").

1. enrich(msgs, now)      – every MCX futures CALL message gets a news block: up to 3 headlines from the last 24 h
                            (Google News RSS), a keyword tone tag, and any scheduled event in the next 24 h with its
                            MEASURED typical move.
2. alerts(state, now)     – separate messages: (a) a heads-up ~1-2 h before each scheduled event, (b) a fresh
                            high-impact headline (OPEC, Fed, war, sanctions…) on a commodity, max NEWS_MAX_DAY per day.

Tone tags are keyword matches, NOT a forecast. Event impact numbers are measured on MCX 1-hour candles Jul-2022 to Oct-2026
(average absolute 1-hour move in the event hour vs the same hour on other days; research ICSS-001 branch exp/icss-backtest).
Any failure (no internet, feed change) returns the messages unchanged – news can never block a call.
"""
import re, html
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import pandas as pd

NEWS_ENABLED = True
NEWS_MAX_DAY = 4                      # high-impact headline alerts per day (all commodities together)
EVENT_LEAD_MIN = (45, 120)            # event heads-up sent when the event is this many minutes away

QUERY = {
    "CRUDEOIL": "crude oil price OR OPEC OR Brent",
    "NATURALGAS": "natural gas price OR Henry Hub OR LNG",
    "GOLD": "gold price OR bullion",
    "SILVER": "silver price",
    "COPPER": "copper price OR LME copper",
    "ZINC": "zinc price OR LME zinc",
    "ALUMINIUM": "aluminium price OR aluminum price LME",
}
BULL = {
    "_": ["surge", "jump", "rally", "soar", "record high", "spike", "climb", "gain", "rise", "rises", "higher", "up "],
    "CRUDEOIL": ["output cut", "production cut", "supply disruption", "inventory draw", "stocks fall", "sanction", "attack", "outage", "drawdown"],
    "NATURALGAS": ["cold", "freeze", "storage draw", "lng outage", "heatwave", "supply disruption"],
    "GOLD": ["rate cut", "safe haven", "safe-haven", "geopolitical", "central bank buying", "weak dollar", "dollar falls"],
    "SILVER": ["rate cut", "safe haven", "industrial demand", "solar demand", "weak dollar", "dollar falls"],
    "COPPER": ["stimulus", "supply disruption", "mine strike", "shortage", "china demand"],
}
BEAR = {
    "_": ["slump", "plunge", "tumble", "drop", "fall", "slide", "sink", "lowest", "lower", "down ", "decline", "slips", "eases"],
    "CRUDEOIL": ["output hike", "production increase", "inventory build", "stocks rise", "ceasefire", "demand worries", "surplus"],
    "NATURALGAS": ["mild weather", "storage build", "injection", "warm weather", "oversupply"],
    "GOLD": ["rate hike", "strong dollar", "dollar rises", "hawkish", "profit taking", "profit-taking"],
    "SILVER": ["rate hike", "strong dollar", "dollar rises", "hawkish", "profit taking"],
    "COPPER": ["demand worries", "tariff", "slowdown", "surplus", "inventories rise"],
}
RELEVANT = {"CRUDEOIL": ["oil", "crude", "brent", "wti", "opec"], "NATURALGAS": ["gas", "lng", "henry hub"],
            "GOLD": ["gold", "bullion"], "SILVER": ["silver"], "COPPER": ["copper"], "ZINC": ["zinc"],
            "ALUMINIUM": ["aluminium", "aluminum"]}
HIGH_IMPACT = ["opec", "fed ", "federal reserve", "rate cut", "rate hike", "war", "attack", "sanction", "tariff", "ceasefire",
               "hurricane", "strike", "embargo", "missile", "explosion", "outage", "emergency"]

# measured on MCX 1h candles (Jul-2022 – Oct-2026): (avg % move in the event hour, same hour other days, 90th pct)
IMPACT = {
    "NG_STORAGE": {"NATURALGAS": (1.28, 0.74, 2.54), "CRUDEOIL": (0.59, 0.54, 1.33)},
    "EIA_CRUDE": {"CRUDEOIL": (0.59, 0.54, 1.22)},
    "US_JOBS": {"SILVER": (0.66, 0.37, 1.57), "GOLD": (0.26, 0.18, 0.64), "COPPER": (0.33, 0.21, 0.73),
                "CRUDEOIL": (0.59, 0.48, 1.19), "NATURALGAS": (0.88, 1.00, 1.84)},
}
AFFECTS = {"EIA_CRUDE": ["CRUDEOIL"], "NG_STORAGE": ["NATURALGAS"],
           "US_JOBS": ["GOLD", "SILVER", "COPPER", "CRUDEOIL"], "US_CPI": ["GOLD", "SILVER", "COPPER", "CRUDEOIL"],
           "FOMC": ["GOLD", "SILVER", "COPPER", "CRUDEOIL", "NATURALGAS", "ZINC", "ALUMINIUM"]}
LABEL = {"EIA_CRUDE": "EIA crude inventory (US)", "NG_STORAGE": "EIA natural-gas storage (US)", "US_JOBS": "US jobs report (NFP)",
         "US_CPI": "US CPI inflation", "FOMC": "US Fed (FOMC) rate decision"}
# dated events, US Eastern clock time. Owner: add / check dates here (BLS CPI schedule, federalreserve.gov FOMC calendar).
DATED = [("US_CPI", "2026-11-10 08:30"), ("FOMC", "2026-12-09 14:00"), ("US_CPI", "2026-12-10 08:30")]


def _us_dst(d):
    y = d.year
    m = pd.Timestamp(y, 3, 8); start = m + pd.Timedelta(days=(6 - m.weekday()) % 7)
    n = pd.Timestamp(y, 11, 1); end = n + pd.Timedelta(days=(6 - n.weekday()) % 7)
    return start <= pd.Timestamp(d).normalize() < end


def _et_to_ist(day, hhmm):
    """US Eastern clock time on `day` -> IST (naive). EDT = UTC-4 -> +9:30; EST = UTC-5 -> +10:30."""
    t = pd.Timestamp(f"{pd.Timestamp(day):%Y-%m-%d} {hhmm}")
    return t + pd.Timedelta(hours=9, minutes=30) + (pd.Timedelta(0) if _us_dst(t) else pd.Timedelta(hours=1))


def events(now, hours=24):
    """Scheduled events from now to now+hours: list of (key, ist_time)."""
    now = pd.Timestamp(now).tz_localize(None) if pd.Timestamp(now).tzinfo else pd.Timestamp(now)
    out = []
    for k in range(-1, 3):
        d = (now - pd.Timedelta(hours=12)).normalize() + pd.Timedelta(days=k)    # ET date ≈ IST date - ~10 h
        wd = d.weekday()
        if wd == 2:
            out.append(("EIA_CRUDE", _et_to_ist(d, "10:30")))
        if wd == 3:
            out.append(("NG_STORAGE", _et_to_ist(d, "10:30")))
        if wd == 4 and d.day <= 7:
            out.append(("US_JOBS", _et_to_ist(d, "08:30")))
    for key, et in DATED:
        t = pd.Timestamp(et)
        out.append((key, _et_to_ist(t.normalize(), f"{t:%H:%M}")))
    out = sorted({(k, t) for k, t in out if now <= t <= now + pd.Timedelta(hours=hours)}, key=lambda x: x[1])
    return out


def impact_line(key, name):
    v = IMPACT.get(key, {}).get(name)
    if v:
        x = v[0] / v[1] if v[1] else 1
        return f"usually moves {name} {v[0]:.2f}% in that hour ({x:.1f}× a normal hour; 1 in 10 times > {v[2]:.1f}%)"
    if key in ("US_CPI", "FOMC"):
        return "high-volatility event – expect a sharp move either way; SL may slip"
    return "no measured effect on this commodity"


def _fetch(q, timeout=8):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{q} when:1d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (option-bot alerts)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title") or "").strip()
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(tz=None)
            ts = pd.Timestamp(ts).tz_convert("Asia/Kolkata").tz_localize(None)
        except Exception:
            ts = None
        out.append(dict(title=title, link=it.findtext("link") or "", time=ts))
    out.sort(key=lambda x: x["time"] or pd.Timestamp(0), reverse=True)
    return out


_CACHE = {}


def headlines(name, now, hours=24):
    if name not in QUERY:
        return []
    if name not in _CACHE:
        try:
            _CACHE[name] = _fetch(QUERY[name])
        except Exception as e:
            print(f"[news] {name}: fetch failed {type(e).__name__}")
            _CACHE[name] = []
    lo = pd.Timestamp(now).tz_localize(None) - pd.Timedelta(hours=hours) if pd.Timestamp(now).tzinfo else pd.Timestamp(now) - pd.Timedelta(hours=hours)
    rel = RELEVANT.get(name, [])
    return [h for h in _CACHE[name] if (h["time"] is None or h["time"] >= lo)
            and any(w in h["title"].lower().split(" - ")[0] for w in rel)                       # headline is about it
            and not (name != "GOLD" and "gold" in h["title"].lower().split(" - ")[0][:25])]  # gold stories leak into others


def tone(name, title):
    t = " " + title.lower() + " "
    b = sum(w in t for w in BULL["_"] + BULL.get(name, []))
    s = sum(w in t for w in BEAR["_"] + BEAR.get(name, []))
    return "▲ bullish words" if b > s else "▼ bearish words" if s > b else "• neutral"


def _short(title, n=95):
    title = re.sub(r"\s+-\s+[^-]{2,40}$", "", title)       # drop " - Publisher"
    return title if len(title) <= n else title[: n - 1] + "…"


def block(name, now, side=None):
    """News block for one MCX commodity (text) – appended under a futures call."""
    hs = headlines(name, now)[:3]
    ev = [(k, t) for k, t in events(now) if name in AFFECTS.get(k, [])]
    if not hs and not ev:
        return ""
    lines = ["", "📰 News & events (context only, not part of the signal)"]
    tones = []
    for h in hs:
        tg = tone(name, h["title"]); tones.append(tg)
        lines.append(f"• {_short(h['title'])}  [{tg}{', ' + format(h['time'], '%H:%M') if h['time'] is not None else ''}]")
    if side and hs:
        nb, ns = sum("bullish" in t for t in tones), sum("bearish" in t for t in tones)
        if (side == "BUY" and ns > nb) or (side == "SELL" and nb > ns):
            lines.append(f"⚠️ Headline keywords lean AGAINST this {side} – check the news before entering")
        elif (side == "BUY" and nb > ns) or (side == "SELL" and ns > nb):
            lines.append(f"✅ Headline keywords lean WITH this {side}")
    for k, t in ev:
        lines.append(f"🗓 {LABEL[k]} at {t:%a %H:%M} IST – {impact_line(k, name)}")
    return "\n".join(lines)


_CALL = re.compile(r"(BUY|SELL)\b[^\n]*?\b(CRUDEOIL|NATURALGAS|GOLD|SILVER|COPPER|ZINC|ALUMINIUM)\b")


def enrich(msgs, now):
    """Append a news block to every MCX futures call (first line names BUY/SELL + commodity, and it has Entry and SL)."""
    if not NEWS_ENABLED:
        return msgs
    out = []
    for m in msgs:
        try:
            first = m.split("\n", 1)[0]
            g = _CALL.search(first)
            if g and "Entry" in m and "SL" in m and "OPTION" not in first.upper():
                b = block(g.group(2), now, g.group(1))
                if b:
                    m = m + "\n" + b
        except Exception as e:
            print(f"[news] enrich failed {type(e).__name__}")
        out.append(m)
    return out


def alerts(state, now):
    """Event heads-ups + high-impact headline alerts. Dedup in state['news']."""
    if not NEWS_ENABLED:
        return []
    now_n = pd.Timestamp(now).tz_localize(None) if pd.Timestamp(now).tzinfo else pd.Timestamp(now)
    ns = state.setdefault("news", {"sent_ev": [], "seen": [], "day": "", "n": 0})
    if ns.get("day") != f"{now_n:%Y-%m-%d}":
        ns.update(day=f"{now_n:%Y-%m-%d}", n=0)
    msgs = []
    for k, t in events(now_n, hours=3):
        mins = (t - now_n).total_seconds() / 60
        key = f"{k}|{t:%Y-%m-%d %H:%M}"
        big = k in ("US_CPI", "FOMC") or any(v[0] >= 1.3 * v[1] for v in IMPACT.get(k, {}).values())
        if big and EVENT_LEAD_MIN[0] <= mins <= EVENT_LEAD_MIN[1] and key not in ns["sent_ev"]:
            ns["sent_ev"] = (ns["sent_ev"] + [key])[-40:]
            lines = [f"🗓 EVENT AHEAD – {LABEL[k]} at {t:%H:%M} IST (in {int(mins)} min)"]
            for name in AFFECTS[k]:
                lines.append(f"• {name}: {impact_line(k, name)}")
            lines.append("Open MCX positions: SL may slip in that hour. New entries: wait for the candle after the release.")
            msgs.append("\n".join(lines))
    for name in QUERY:
        if ns["n"] >= NEWS_MAX_DAY:
            break
        for h in headlines(name, now_n, hours=1):
            low = " " + h["title"].lower() + " "
            hid = re.sub(r"\W+", "", h["title"].lower())[:80]
            if hid in ns["seen"] or not any(w in low for w in HIGH_IMPACT):
                continue
            ns["seen"] = (ns["seen"] + [hid])[-300:]
            ns["n"] += 1
            msgs.append(f"📰 HIGH-IMPACT NEWS – {name}\n{_short(h['title'], 160)}\n{tone(name, h['title'])} (keyword tag, not a forecast)"
                        + (f" · {h['time']:%H:%M} IST" if h["time"] is not None else ""))
            break
    return msgs

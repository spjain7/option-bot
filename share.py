"""Shares one price snapshot with the PokharnaResearch website (its Cloudflare Worker), so the website needs no Angel One
calls of its own: both use the same Angel key and share one rate limit.

One Angel market-quote call per scan, made with the session the bot already has: Nifty 50, Bank Nifty, India VIX and the
nearest MCX gold, silver, crude oil, natural gas and copper futures. Sent to PR_FEED_URL/api/feed/snapshot with the
access key PR_FEED_KEY (repository secrets). Without them nothing is sent. Never raises: the bot's own work comes first.
"""
import json, os, urllib.request

IDX = [("nifty-50", "99926000"), ("bank-nifty", "99926009"), ("india-vix", "99926017")]
MCX = [("mcx-gold", "GOLD"), ("mcx-silver", "SILVER"), ("mcx-crude", "CRUDEOIL"), ("mcx-natgas", "NATURALGAS"), ("mcx-copper", "COPPER")]


def nearest(master, base, today):
    """Nearest MCX future of `base` that has not expired: (token, symbol, expiry ISO) or None."""
    df = master[(master["exch_seg"] == "MCX") & (master["instrumenttype"] == "FUTCOM") & (master["name"] == base)
                & (master["expiry_dt"] >= today.normalize())].sort_values("expiry_dt")
    if not len(df):
        return None
    r = df.iloc[0]
    return str(r["token"]), str(r["symbol"]), r["expiry_dt"].date().isoformat()


def rows(fetched, meta):
    """Angel quote rows -> the website's snapshot items (only the instruments we asked for)."""
    out = []
    for q in fetched or []:
        m = meta.get((q.get("exchange"), str(q.get("symbolToken"))))
        if not m or not q.get("ltp"):
            continue
        key, symbol, expiry = m
        out.append({"key": key, "token": str(q.get("symbolToken")), "symbol": q.get("tradingSymbol") or symbol, "expiry": expiry,
                    "last": q.get("ltp"), "open": q.get("open"), "high": q.get("high"), "low": q.get("low"), "prev_close": q.get("close"),
                    "volume": q.get("tradeVolume"), "oi": q.get("opnInterest"), "time": q.get("exchFeedTime") or q.get("exchTradeTime")})
    return out


def push(api, master, now):
    url, key = os.getenv("PR_FEED_URL", "").strip().rstrip("/"), os.getenv("PR_FEED_KEY", "").strip()
    if not url or not key:
        return "off"
    try:
        meta, want = {}, {"NSE": [], "MCX": []}
        for k, tok in IDX:
            meta[("NSE", tok)] = (k, None, None); want["NSE"].append(tok)
        for k, base in MCX:
            n = nearest(master, base, now)
            if n:
                meta[("MCX", n[0])] = (k, n[1], n[2]); want["MCX"].append(n[0])
        api._wait(api.QUOTE_GAP)                              # same spacing as the bot's own quote calls
        r = api.api.getMarketData("FULL", {ex: t for ex, t in want.items() if t})
        items = rows(((r or {}).get("data") or {}).get("fetched"), meta)
        if not items:
            return "no prices"
        req = urllib.request.Request(url + "/api/feed/snapshot", data=json.dumps({"items": items}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Access-Key": key, "User-Agent": "option-bot"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return f"shared {json.load(resp).get('stored')} prices"
    except Exception as e:                                    # never break the scan; never print the key
        return f"not shared ({type(e).__name__})"

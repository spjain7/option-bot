"""Background collector: Angel WebSocket (SmartWebSocketV2, SNAP_QUOTE) -> live 1-minute futures bars in .cache/ws.
Started once per job by scripts/market_loop.sh (restarted by the shell if it exits). Market data only – no orders.

Subscribed (ONE connection, hard cap 950 tokens – Angel allows 1,000 per connection):
  * futures: current month of every stock future, NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY and the followed MCX futures
    (+ next month during the last 7 days before expiry)                                                       ≈ 220-430
  * options (30-Oct): at 09:30, from the live ticks (no REST calls), the 40 stock futures with the highest traded value so
    far + NIFTY + BANKNIFTY: ATM ± 2 strikes, CE and PE (10 each); re-centred every 30 min when the price moves  ≈ 420-600
Prices arrive in paise -> ₹. Watchdog: no tick for 120 s while a market is open -> exit (the shell restarts it).
python -m wsfeed
"""
import logging
import os
import threading
import time
import pandas as pd

import wsbars as WB
from angel import Angel, load_master, now_ist

MCX_NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
IDX_NAMES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
EXCH_TYPE = {"NFO": 2, "MCX": 5}
STALE_SEC = 120
CAP = 950                     # tokens on the one connection (Angel limit 1,000)
TOP_STOCKS, WING = 40, 2      # option underlyings by traded value · strikes each side of ATM
OPT_START, RECENTRE_MIN = "09:30", 30


def tokens(master, now):
    today = now.normalize()
    f = master[(master["expiry_dt"] >= today) & (
        ((master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTSTK")) |
        ((master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTIDX") & master["name"].isin(IDX_NAMES)) |
        ((master["exch_seg"] == "MCX") & (master["instrumenttype"] == "FUTCOM") & master["name"].isin(MCX_NAMES)))]
    f = f.sort_values("expiry_dt")
    first = f.groupby(["exch_seg", "name"])["expiry_dt"].transform("min")
    rank = f.groupby(["exch_seg", "name"]).cumcount()
    f = f[(rank == 0) | ((rank == 1) & ((first - today).dt.days <= 7))]   # next month only in the expiry week
    return {ex: [str(t) for t in g["token"]] for ex, g in f.groupby("exch_seg")}


def option_tokens(master, now, px, names, have, room):
    """ATM ± WING strikes (CE + PE) of each underlying at its live price px[name]; skips tokens already subscribed;
    stops at `room` new tokens. -> list of master rows (token, name, symbol, expiry, strike)."""
    today = now.normalize()
    o = master[(master["exch_seg"] == "NFO") & master["instrumenttype"].isin(["OPTSTK", "OPTIDX"]) & master["name"].isin(names)
               & (master["expiry_dt"] >= today)]
    out = []
    for nm in names:
        if nm not in px or len(out) >= room:
            continue
        x = o[o["name"] == nm]
        if x.empty:
            continue
        min_days = 1 if nm in IDX_NAMES else 3                 # stock options: skip an expiry 0-2 days away
        exps = sorted(e for e in x["expiry_dt"].unique() if (pd.Timestamp(e) - today).days >= min_days)
        if not exps:
            continue
        x = x[x["expiry_dt"] == exps[0]].copy()
        x["K"] = x["strike"] / 100
        ks = sorted(x["K"].unique())
        if not ks:
            continue
        i = min(range(len(ks)), key=lambda j: abs(ks[j] - px[nm]))
        pick = set(ks[max(0, i - WING): i + WING + 1])
        for r in x[x["K"].isin(pick)].itertuples():
            t = str(r.token)
            if t not in have and len(out) < room:
                out.append(dict(token=t, exch="NFO", name=nm, symbol=r.symbol, expiry=pd.Timestamp(r.expiry_dt).strftime("%Y-%m-%d")))
    return out


def is_open(ex, now):
    if now.weekday() >= 5:
        return False
    h, m = WB.OPEN[ex]; hc, mc = WB.CLOSE[ex]
    return now.normalize() + pd.Timedelta(hours=h, minutes=m) <= now <= now.normalize() + pd.Timedelta(hours=hc, minutes=mc)


def main():
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    import logzero
    a = Angel()
    master = load_master()
    now = now_ist()
    toks = tokens(master, now)
    try:                                                  # token -> symbol map, kept with the exported bars
        mm = master[master["token"].astype(str).isin([t for v in toks.values() for t in v])]
        mm.assign(exch=mm["exch_seg"], expiry=mm["expiry_dt"].dt.strftime("%Y-%m-%d"))[["token", "exch", "name", "symbol", "expiry"]] \
            .to_csv(WB._dir() / "tokens.csv", index=False)
    except Exception as e:
        print("[ws] token map not written:", e)
    os.chdir(WB._dir())                                  # the SDK writes a log folder into the working directory
    B, lock = WB.Builder(), threading.Lock()
    st = dict(start=str(now), last_tick={}, tokens=[t for v in toks.values() for t in v], ticks=0, pid=os.getpid(),
              counts={ex: len(v) for ex, v in toks.items()})
    WB.write_status(st)
    by_type = {v: k for k, v in EXCH_TYPE.items()}
    ws = SmartWebSocketV2(a.jwt, os.environ["ANGEL_API_KEY"], os.environ["ANGEL_CLIENT_ID"], a.feed, max_retry_attempt=3)
    logzero.loglevel(logging.WARNING)
    try:
        logzero.logfile(os.path.join("logs", "ws.log"), loglevel=logging.WARNING)
    except Exception:
        pass

    fut_name = {str(t): n for t, n in zip(master["token"].astype(str), master["name"])
                if t in set(st["tokens"])}
    lastpx, value = {}, {}

    def on_data(wsapp, msg):
        try:
            ex = by_type.get(msg.get("exchange_type"))
            if ex is None or not msg.get("last_traded_price"):
                return
            t = pd.Timestamp(msg["exchange_timestamp"], unit="ms", tz="UTC").tz_convert("Asia/Kolkata").tz_localize(None)
            with lock:
                tok, ltp, cv = str(msg["token"]), msg["last_traded_price"] / 100.0, msg.get("volume_trade_for_the_day") or 0
                B.tick(tok, t, ltp, cv, msg.get("open_interest") or 0)
                if tok in fut_name:
                    lastpx[tok], value[tok] = ltp, ltp * cv
                st["last_tick"][ex] = str(now_ist()); st["ticks"] += 1
        except Exception as e:
            print("[ws] tick error", type(e).__name__, e)

    def on_open(wsapp):
        for ex, tl in toks.items():
            for i in range(0, len(tl), 200):
                ws.subscribe(f"ob{ex}{i}"[:10], ws.SNAP_QUOTE, [{"exchangeType": EXCH_TYPE[ex], "tokens": tl[i:i + 200]}])
        print(f"[ws] connected – subscribed {st['counts']}", flush=True)

    ws.on_data, ws.on_open = on_data, on_open
    ws.on_error = lambda *a_: print("[ws] error", *a_, flush=True)
    ws.on_close = lambda *a_: print("[ws] closed", flush=True)
    th = threading.Thread(target=ws.connect, daemon=True)
    th.start()
    t0, last_n = time.time(), -1
    opt_names, last_centre = None, None
    have = set(st["tokens"])

    def add_options(n):
        nonlocal opt_names
        if opt_names is None:                            # once: top stocks by traded value so far + the 2 main indices
            stk = [(v, fut_name[t]) for t, v in value.items() if fut_name[t] not in IDX_NAMES and fut_name[t] not in MCX_NAMES]
            opt_names = ["NIFTY", "BANKNIFTY"] + [nm for _, nm in sorted(stk, reverse=True)[:TOP_STOCKS]]
        px = {}
        for t, p in lastpx.items():                     # current-month futures price per underlying
            px.setdefault(fut_name[t], p)
        new = option_tokens(master, n, px, opt_names, have, max(CAP - len(have), 0))
        if not new:
            return
        for i in range(0, len(new), 200):
            ws.subscribe(f"op{len(have) + i}"[:10], ws.SNAP_QUOTE, [{"exchangeType": 2, "tokens": [x["token"] for x in new[i:i + 200]]}])
        have.update(x["token"] for x in new)
        with lock:
            st["tokens"] = sorted(have); st.setdefault("counts", {})["NFO_options"] = st["counts"].get("NFO_options", 0) + len(new)
        try:
            pd.DataFrame(new).to_csv(WB._dir() / "tokens.csv", mode="a", header=False, index=False)
        except Exception:
            pass
        print(f"[ws] {n:%H:%M} options subscribed +{len(new)} (total tokens {len(have)} / cap {CAP})", flush=True)

    while True:
        time.sleep(15)
        n = now_ist()
        with lock:
            B.flush(n)
            WB.write_status(st)
        try:                                             # options: from 09:30, re-centred every 30 min (no REST calls)
            if is_open("NFO", n) and f"{n:%H:%M}" >= OPT_START and lastpx and (
                    last_centre is None or (n - last_centre).total_seconds() >= RECENTRE_MIN * 60):
                last_centre = n
                add_options(n)
        except Exception as e:
            print("[ws] option subscribe skipped:", type(e).__name__, e, flush=True)
        if n.hour == 23 and n.minute >= 58:
            print("[ws] day over – exit", flush=True); break
        if not th.is_alive():
            print("[ws] connection thread ended – exit for a restart", flush=True); break
        live = [ex for ex in toks if is_open(ex, n)]
        lt = [pd.Timestamp(st["last_tick"][ex]) for ex in live if st["last_tick"].get(ex)]
        if live and time.time() - t0 > STALE_SEC and (not lt or (n - max(lt)).total_seconds() > STALE_SEC):
            print(f"[ws] no ticks for {STALE_SEC}s while {live} open – exit for a restart", flush=True); break
        if st["ticks"] // 50000 != last_n:
            last_n = st["ticks"] // 50000
            print(f"[ws] {n:%H:%M} ticks {st['ticks']:,} last {st['last_tick']}", flush=True)
    try:
        ws.close_connection()
    except Exception:
        pass
    with lock:
        B.flush(now_ist() + pd.Timedelta(minutes=1))


if __name__ == "__main__":
    main()

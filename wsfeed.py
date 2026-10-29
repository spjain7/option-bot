"""Background collector: Angel WebSocket (SmartWebSocketV2, SNAP_QUOTE) -> live 1-minute futures bars in .cache/ws.
Started once per job by scripts/market_loop.sh (restarted by the shell if it exits). Market data only – no orders.

Subscribed: the 2 nearest expiries of every stock future, NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY futures and the MCX
futures the alert engine follows (≈ 450 tokens; Angel allows 1,000 per connection). Prices arrive in paise -> ₹.
Watchdog: no tick for 120 s while a market is open -> exit (the shell restarts it with a fresh login).
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


def tokens(master, now):
    today = now.normalize()
    f = master[(master["expiry_dt"] >= today) & (
        ((master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTSTK")) |
        ((master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTIDX") & master["name"].isin(IDX_NAMES)) |
        ((master["exch_seg"] == "MCX") & (master["instrumenttype"] == "FUTCOM") & master["name"].isin(MCX_NAMES)))]
    f = f.sort_values("expiry_dt").groupby(["exch_seg", "name"]).head(2)
    return {ex: [str(t) for t in g["token"]] for ex, g in f.groupby("exch_seg")}


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

    def on_data(wsapp, msg):
        try:
            ex = by_type.get(msg.get("exchange_type"))
            if ex is None or not msg.get("last_traded_price"):
                return
            t = pd.Timestamp(msg["exchange_timestamp"], unit="ms", tz="UTC").tz_convert("Asia/Kolkata").tz_localize(None)
            with lock:
                B.tick(str(msg["token"]), t, msg["last_traded_price"] / 100.0, msg.get("volume_trade_for_the_day") or 0,
                       msg.get("open_interest") or 0)
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
    while True:
        time.sleep(15)
        n = now_ist()
        with lock:
            B.flush(n)
            WB.write_status(st)
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

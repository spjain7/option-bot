"""Angel One SmartAPI market-data client (no orders are ever placed)."""
import os, json, time, datetime as dt
from pathlib import Path
import pandas as pd
import requests
import wsbars as WB

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
ROOT = Path(__file__).parent
CACHE = ROOT / ".cache"
CACHE.mkdir(exist_ok=True)


def now_ist():
    return pd.Timestamp(dt.datetime.now(IST).replace(tzinfo=None))


def _naive(s):
    t = pd.to_datetime(s)
    return t.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None) if t.dt.tz is not None else t


class Angel:
    """Rate-limit aware SmartAPI client. Added after Angel started answering 'Access denied because of exceeding access rate':
      * a cool-down shared by every engine process in the job (one engine hitting the limit slows the others down too,
        instead of each one hammering the API again);
      * after several limit errors in a row, calls fail fast (return None) instead of retrying for minutes;
      * candle series fetched by one engine are re-used by the next engine for DISK_TTL seconds (they all ask for the same
        GOLD / CRUDEOIL / NIFTY ... candles);
      * every API call is counted and one summary line is printed when the process ends."""

    # Angel limits historical APIs to ~3 req/sec (and less per minute); stay safely under it.
    HIST_GAP, QUOTE_GAP = 0.75, 1.1
    COOL_STEPS = (8, 15, 30, 60, 90)   # seconds to pause after the 1st, 2nd, 3rd ... consecutive rate-limit error
    FAILFAST_AFTER = 5                 # from this many limit errors in a row: skip calls (return None) until the pause is over
    STREAK_FORGET = 300                # a block that ended this many seconds ago no longer counts (fresh retries next scan)
    DISK_TTL = 240                     # seconds a candle series may be re-used by another engine process

    def __init__(self):
        from SmartApi import SmartConnect
        import pyotp
        self.api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
        totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"].replace(" ", "")).now()
        s = self.api.generateSession(os.environ["ANGEL_CLIENT_ID"], os.environ["ANGEL_PIN"], totp)
        if not s or not s.get("status"):
            raise RuntimeError(f"Angel login failed: {s}")
        self.jwt, self.feed = (s.get("data") or {}).get("jwtToken"), (s.get("data") or {}).get("feedToken")   # for wsfeed.py
        self._setup()

    def _setup(self, cache_dir=None, ws_dir=None, ws=None):
        """Runtime state (separate from the login so the throttling logic can be tested offline)."""
        self._ws_dir = ws_dir
        self._ws_on = (os.getenv("ANGEL_WS", "1") == "1") if ws is None else ws
        self._last = 0.0
        self._cache, self._cc = {}, {}
        self._dir = Path(cache_dir) if cache_dir else CACHE / "api"
        self._dir.mkdir(parents=True, exist_ok=True)
        self.stats = dict(calls=0, ok=0, rate_limited=0, skipped=0, mem_hits=0, disk_hits=0, ws_hits=0, ws_fallback=0)
        self._ws_note = {}
        import atexit
        atexit.register(self.report)

    def _wait(self, gap=0.4):
        d = time.time() - self._last
        if d < gap:
            time.sleep(gap - d)
        self._last = time.time()

    # ── shared cool-down ("circuit breaker"), stored in a small file so all engine processes of the job see it ──
    @staticmethod
    def _is_rate(text):
        t = str(text).lower()
        return any(k in t for k in ("access rate", "too many", "ab1021", "rate limit"))

    def _bfile(self, group):
        # 29-Oct: separate pauses – Angel limits quotes (market/v1/quote) separately from candles / OI history, and quotes
        # kept working while candles were blocked; one shared pause had stopped the quotes too
        return self._dir / ("breaker.json" if group == "hist" else f"breaker_{group}.json")

    def _breaker(self, group="hist"):
        try:
            b = json.loads(self._bfile(group).read_text())
            until, streak = float(b.get("until", 0)), int(b.get("streak", 0))
        except Exception:
            return 0.0, 0
        if until < time.time() - self.STREAK_FORGET:   # an old block (e.g. from the previous 15-min scan) is forgotten:
            return 0.0, 0                              # the new scan gets its normal retries instead of failing fast at once
        return until, streak

    def _trip(self, group="hist"):
        """A rate-limit reply came back: pause every engine for a while (longer each time in a row)."""
        self.stats["rate_limited"] += 1
        _, streak = self._breaker(group)
        streak += 1
        cool = self.COOL_STEPS[min(streak - 1, len(self.COOL_STEPS) - 1)]
        try:
            self._bfile(group).write_text(json.dumps({"until": time.time() + cool, "streak": streak}))
        except Exception:
            pass
        print(f"[angel] rate limit ({streak} in a row) - pausing {'quote' if group == 'quote' else 'candle/OI'} calls for {cool}s")

    def _reset(self, group="hist"):
        if self._breaker(group)[1]:
            try:
                self._bfile(group).write_text(json.dumps({"until": 0, "streak": 0}))
            except Exception:
                pass

    def failfast(self, group="hist"):
        """True while the API is blocked and calls are being skipped (callers can stop retrying)."""
        until, streak = self._breaker(group)
        return streak >= self.FAILFAST_AFTER and until > time.time()

    def wait_clear(self, max_s=100):
        """Priority callers (index / MCX futures calls): wait out an active block (at most max_s) and start a fresh streak,
        instead of skipping the data. Returns True when the block is over."""
        until, streak = self._breaker()
        remaining = until - time.time()
        if remaining > max_s:
            return False
        if remaining > 0:
            print(f"[angel] priority fetch: waiting {remaining:.0f}s for the rate-limit pause to end")
            time.sleep(remaining + 1)
        try:
            (self._dir / "breaker.json").write_text(json.dumps({"until": 0, "streak": 0}))
        except Exception:
            pass
        return True

    def _gate(self, group="hist"):
        """May an API call go out now? Waits out a short cool-down; during a long block returns False (skip the call)."""
        until, streak = self._breaker(group)
        remaining = until - time.time()
        if remaining <= 0:
            return True
        if streak >= self.FAILFAST_AFTER:
            return False
        time.sleep(min(remaining, max(self.COOL_STEPS)))
        return True

    def _count(self):
        """Count one real API request (also appended to a per-job log so the hourly total can be reported)."""
        self.stats["calls"] += 1
        try:
            with open(self._dir / "calls.log", "a") as f:
                f.write(f"{int(time.time())}\n")
        except Exception:
            pass

    def report(self):
        if getattr(self, "_reported", False) or not self.stats["calls"] + self.stats["skipped"] + self.stats["mem_hits"] + self.stats["disk_hits"]:
            return
        self._reported = True
        hour = "?"
        try:
            f = self._dir / "calls.log"
            now = time.time()
            ts = [int(x) for x in f.read_text().split() if x.strip().isdigit() and now - int(x) <= 3600]
            f.write_text("\n".join(map(str, ts)) + ("\n" if ts else ""))
            hour = len(ts)
        except Exception:
            pass
        s = self.stats
        print(f"[angel-stats] API requests={s['calls']} ok={s['ok']} rate-limited={s['rate_limited']} skipped(blocked)={s['skipped']} "
              f"cache hits memory/disk={s['mem_hits']}/{s['disk_hits']} | requests by all engines of this job in the last 60 min={hour} "
              f"(community-reported Angel cap for candles: ~5000/h)")
        st = WB.status(self._ws_dir)
        if st:
            print(f"[ws] collector since {str(st.get('start'))[:16]} · ticks {st.get('ticks', 0):,} · last tick {st.get('last_tick')} · "
                  f"served from WebSocket bars {s['ws_hits']} · REST fallback {s['ws_fallback']}"
                  + (f" · {self._ws_note}" if self._ws_note else ""))

    def _call(self, fn, *a, retries=3):
        self._cache = getattr(self, "_cache", {})
        key = (fn.__name__, repr(a))
        if key in self._cache:                       # same request twice in one run -> reuse
            self.stats["mem_hits"] += 1
            return self._cache[key]
        for i in range(retries):
            if not self._gate():                     # API is blocked: don't pile more requests on it (not cached: a later call may work)
                self.stats["skipped"] += 1
                return None
            self._wait(self.HIST_GAP)
            self._count()
            try:
                r = fn(*a)
            except Exception as e:                   # rate limit shows up as a non-JSON reply
                msg = str(e)
                print("API error:", msg[:120])
                if self._is_rate(msg):
                    self._trip()
                else:
                    time.sleep(1)
                continue
            if r and r.get("status") and r.get("data") is not None:
                self.stats["ok"] += 1
                self._reset()
                self._cache[key] = r["data"]
                return r["data"]
            if r and self._is_rate(f"{r.get('message', '')} {r.get('errorcode', '')}"):
                self._trip()
                continue
            break                                    # real "bad request / no data" -> don't retry
        self._cache[key] = None
        return None

    # ── candle series shared between the engine processes of one job (successful fetches only) ──
    def _disk_path(self, key):
        return self._dir / ("c_" + "_".join(str(x) for x in key) + ".pkl")

    def _disk_get(self, key, frm, to):
        try:
            e = pd.read_pickle(self._disk_path(key))
            if time.time() - e["saved"] <= self.DISK_TTL and e["frm"] <= frm and abs((to - e["to"]).total_seconds()) <= self.DISK_TTL:
                return e["df"]
        except Exception:
            pass
        return None

    def _disk_put(self, key, frm, to, df):
        try:
            pd.to_pickle(dict(saved=time.time(), frm=frm, to=to, df=df), self._disk_path(key))
        except Exception:
            pass

    # ── today's bars from the WebSocket collector (wsfeed.py), history before today from REST once a day ──
    DAY_EXT = {"ONE_HOUR": 400, "ONE_DAY": 400, "FIFTEEN_MINUTE": 30, "THIRTY_MINUTE": 30, "FIVE_MINUTE": 10,
               "TEN_MINUTE": 10, "THREE_MINUTE": 5, "ONE_MINUTE": 3}

    def _now(self):
        return now_ist()

    def _rest(self, kind, exch, token, interval, frm, to):
        return self._candles(exch, token, interval, frm, to) if kind == "candles" else self._oi_rest(exch, token, interval, frm, to)

    def _day_hist(self, kind, exch, token, interval, frm, day0):
        """Bars before today, fetched once per day per series (disk, shared by the engine processes of the job)."""
        p = self._dir / f"day_{kind}_{exch}_{token}_{interval}_{day0:%Y%m%d}.pkl"
        try:
            e = pd.read_pickle(p)
            if e["frm"] <= frm:
                self.stats["disk_hits"] += 1
                return e["df"]
        except Exception:
            pass
        f0 = min(frm, day0 - pd.Timedelta(days=self.DAY_EXT.get(interval, 30)))
        df = self._rest(kind, exch, token, interval, f0, day0 - pd.Timedelta(minutes=1))
        if df is None:
            return None
        df = df[df["time"] < day0].reset_index(drop=True)
        try:
            pd.to_pickle(dict(frm=f0, df=df), p)
        except Exception:
            pass
        return df

    def _pre(self, kind, exch, token, interval, day0, ws_start):
        """Today's REST bars up to the moment the collector started (only when it started after the open)."""
        p = self._dir / f"pre_{kind}_{exch}_{token}_{interval}_{ws_start:%Y%m%d%H%M%S}.pkl"
        try:
            return pd.read_pickle(p)
        except Exception:
            pass
        df = self._rest(kind, exch, token, interval, day0, ws_start)
        if df is not None:
            df = df[df["time"] >= day0].reset_index(drop=True)
            try:
                pd.to_pickle(df, p)
            except Exception:
                pass
        return df

    def _ws_verify(self, exch, token, st, now):
        """Once an hour per exchange: the last completed 15-min bars from REST vs the WebSocket bars. A mismatch switches
        the WebSocket bars off for that exchange for the hour (REST is used) and is printed in the run log."""
        vf = WB._dir(self._ws_dir) / "verify.json"
        try:
            v = json.loads(vf.read_text())
        except Exception:
            v = {}
        e = v.get(exch) or {}
        if e.get("hour") == f"{now:%Y%m%d%H}":
            self._ws_note[exch] = e.get("note")
            return e.get("ok") is not False
        ws_start = pd.Timestamp(st["start"])
        b0 = WB.bucket_start(ws_start, "FIFTEEN_MINUTE", exch) + pd.Timedelta(minutes=15)
        b1 = WB.bucket_start(now, "FIFTEEN_MINUTE", exch)
        if b1 - b0 < pd.Timedelta(minutes=30):
            return True                                   # not enough WebSocket history yet to compare
        rest = self._candles(exch, token, "FIFTEEN_MINUTE", b0, now)
        wsb = WB.aggregate(WB.minutes(token, now, self._ws_dir), "FIFTEEN_MINUTE", exch)
        if rest is None:
            return True                                   # REST blocked – keep the WebSocket bars, check again next call
        cut = lambda d: d[(d["time"] >= b0) & (d["time"] < b1)]
        ok, note = WB.verify_ok(cut(rest), cut(wsb))
        if ok is None:
            return True
        v[exch] = dict(hour=f"{now:%Y%m%d%H}", ok=bool(ok), note=f"{'OK' if ok else 'MISMATCH – REST used'}: {note}", token=str(token))
        try:
            vf.write_text(json.dumps(v))
        except Exception:
            pass
        self._ws_note[exch] = v[exch]["note"]
        print(f"[ws] verify {exch} {token}: {v[exch]['note']}")
        return bool(ok)

    def _ws_series(self, exch, token, interval, frm, to, kind):
        if not self._ws_on or interval not in WB.MINUTES or exch not in WB.OPEN:
            return None
        now = self._now()
        day0 = now.normalize()
        if to < day0:
            return None
        st = WB.status(self._ws_dir)
        if not WB.usable(st, exch, token, now):
            return None
        if not self._ws_verify(exch, token, st, now):
            self.stats["ws_fallback"] += 1
            return None
        hist = None
        if frm < day0:
            hist = self._day_hist(kind, exch, token, interval, frm, day0)
            if hist is None:
                self.stats["ws_fallback"] += 1
                return None
        ws_start = pd.Timestamp(st["start"])
        h, m = WB.OPEN[exch]
        open_t = day0 + pd.Timedelta(hours=h, minutes=m)
        pre, boundary = None, None
        if ws_start.normalize() == day0 and ws_start > open_t + pd.Timedelta(minutes=1) and now > open_t:
            boundary = WB.bucket_start(ws_start, interval, exch)
            pre = self._pre(kind, exch, token, interval, day0, ws_start)
            if pre is None:
                self.stats["ws_fallback"] += 1
                return None
        m1 = WB.minutes(token, day0, self._ws_dir)
        if len(m1):
            m1 = m1[m1["time"] >= ws_start.floor("min")]
        wsb = WB.aggregate(m1, interval, exch)
        if kind == "candles":
            df = WB.combine(hist, pre, wsb.drop(columns=["oi"]), boundary)
        else:
            parts = [x for x in (hist, pre[pre["time"] <= boundary] if pre is not None and boundary is not None else pre,
                                 wsb[["time", "oi"]] if len(wsb) else None) if x is not None and len(x)]
            df = pd.concat(parts, ignore_index=True).drop_duplicates("time", keep="last").sort_values("time") if parts else None
        if df is None:
            return None
        self.stats["ws_hits"] += 1
        return df[(df["time"] >= frm) & (df["time"] <= to)].reset_index(drop=True)

    def candles(self, exch, token, interval, frm, to):
        # same series asked again in this run (e.g. RSI engine, then MCX buy/sell engine) -> reuse, saves API quota
        self._cc = getattr(self, "_cc", {})
        key = (exch, str(token), interval)
        hit = self._cc.get(key)
        if hit is not None and hit[0] <= frm and abs((to - hit[1]).total_seconds()) <= 300:
            self.stats["mem_hits"] += 1
            return hit[2][hit[2]["time"] >= frm].reset_index(drop=True)
        ws = self._ws_series(exch, token, interval, frm, to, "candles")   # 29-Oct: today from the WebSocket bars
        if ws is not None:
            self._cc[key] = (frm, to, ws)
            return ws
        dh = self._disk_get(key, frm, to)                # fetched a moment ago by another engine process of this job
        if dh is not None:
            self.stats["disk_hits"] += 1
            self._cc[key] = (frm, to, dh)
            return dh[dh["time"] >= frm].reset_index(drop=True)
        df = self._candles(exch, token, interval, frm, to)
        if df is not None:
            self._cc[key] = (frm, to, df)
            self._disk_put(key, frm, to, df)
        return df

    def _candles(self, exch, token, interval, frm, to):
        d = self._call(self.api.getCandleData, {
            "exchange": exch, "symboltoken": str(token), "interval": interval,
            "fromdate": frm.strftime("%Y-%m-%d %H:%M"), "todate": to.strftime("%Y-%m-%d %H:%M")})
        if not d:
            return None
        df = pd.DataFrame(d, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = _naive(df["time"])
        return df

    def oi_history(self, exch, token, interval, frm, to):
        if exch == "MCX":                            # Angel does not serve OI history for MCX (AB1012)
            return None
        ws = self._ws_series(exch, token, interval, frm, to, "oi")
        if ws is not None:
            return ws
        return self._oi_rest(exch, token, interval, frm, to)

    def _oi_rest(self, exch, token, interval, frm, to):
        d = self._call(self.api.getOIData, {
            "exchange": exch, "symboltoken": str(token), "interval": interval,
            "fromdate": frm.strftime("%Y-%m-%d %H:%M"), "todate": to.strftime("%Y-%m-%d %H:%M")})
        if not d:
            return None
        df = pd.DataFrame(d)
        df["time"] = _naive(df["time"])
        return df.rename(columns={"openInterest": "oi"}).sort_values("time")

    def quotes(self, exch_tokens):
        """exch_tokens: {"NFO": [tok,...], "NSE": [...]} -> {token: quote dict}"""
        out = {}
        for ex, toks in exch_tokens.items():
            toks = [str(t) for t in toks]
            for i in range(0, len(toks), 50):
                for attempt in range(3):
                    if not self._gate("quote"):
                        self.stats["skipped"] += 1
                        break
                    self._wait(self.QUOTE_GAP)
                    self._count()
                    try:
                        r = self.api.getMarketData("FULL", {ex: toks[i:i + 50]})
                        if r and self._is_rate(f"{r.get('message', '')} {r.get('errorcode', '')}"):
                            self._trip("quote")
                            continue
                        for q in (r.get("data") or {}).get("fetched", []):
                            out[str(q["symbolToken"])] = q
                        self.stats["ok"] += 1
                        self._reset("quote")
                        break
                    except Exception as e:
                        print("quote error:", str(e)[:120])
                        if self._is_rate(e):
                            self._trip("quote")
                        else:
                            time.sleep(3 + 2 * attempt)
        return out


# ─────────────── scrip master ───────────────
def load_master():
    f = CACHE / f"scrip_{now_ist():%Y%m%d}.json"
    if not f.exists():
        for old in CACHE.glob("scrip_*.json"):
            old.unlink()
        f.write_bytes(requests.get(SCRIP_URL, timeout=180).content)
    df = pd.DataFrame(json.loads(f.read_text()))
    keep = df["instrumenttype"].isin(["OPTIDX", "OPTSTK", "FUTIDX", "FUTSTK"]) & df["exch_seg"].isin(["NFO", "BFO"])
    eq = (df["exch_seg"] == "NSE") & df["symbol"].str.endswith("-EQ")
    mcx = (df["exch_seg"] == "MCX") & df["instrumenttype"].isin(["FUTCOM", "OPTFUT", "OPTCOM"])
    df = df[keep | eq | mcx].copy()
    df["expiry_dt"] = pd.to_datetime(df["expiry"], format="%d%b%Y", errors="coerce")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["lotsize"] = pd.to_numeric(df["lotsize"], errors="coerce")
    df["tick"] = pd.to_numeric(df["tick_size"], errors="coerce") / 100 if "tick_size" in df else float("nan")   # paise -> ₹
    return df

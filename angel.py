"""Angel One SmartAPI market-data client (no orders are ever placed)."""
import os, json, time, datetime as dt
from pathlib import Path
import pandas as pd
import requests

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
        self._setup()

    def _setup(self, cache_dir=None):
        """Runtime state (separate from the login so the throttling logic can be tested offline)."""
        self._last = 0.0
        self._cache, self._cc = {}, {}
        self._dir = Path(cache_dir) if cache_dir else CACHE / "api"
        self._dir.mkdir(parents=True, exist_ok=True)
        self.stats = dict(calls=0, ok=0, rate_limited=0, skipped=0, mem_hits=0, disk_hits=0)
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

    def _breaker(self):
        try:
            b = json.loads((self._dir / "breaker.json").read_text())
            until, streak = float(b.get("until", 0)), int(b.get("streak", 0))
        except Exception:
            return 0.0, 0
        if until < time.time() - self.STREAK_FORGET:   # an old block (e.g. from the previous 15-min scan) is forgotten:
            return 0.0, 0                              # the new scan gets its normal retries instead of failing fast at once
        return until, streak

    def _trip(self):
        """A rate-limit reply came back: pause every engine for a while (longer each time in a row)."""
        self.stats["rate_limited"] += 1
        _, streak = self._breaker()
        streak += 1
        cool = self.COOL_STEPS[min(streak - 1, len(self.COOL_STEPS) - 1)]
        try:
            (self._dir / "breaker.json").write_text(json.dumps({"until": time.time() + cool, "streak": streak}))
        except Exception:
            pass
        print(f"[angel] rate limit ({streak} in a row) - pausing API calls for {cool}s")

    def _reset(self):
        if self._breaker()[1]:
            try:
                (self._dir / "breaker.json").write_text(json.dumps({"until": 0, "streak": 0}))
            except Exception:
                pass

    def failfast(self):
        """True while the API is blocked and calls are being skipped (callers can stop retrying)."""
        until, streak = self._breaker()
        return streak >= self.FAILFAST_AFTER and until > time.time()

    def _gate(self):
        """May an API call go out now? Waits out a short cool-down; during a long block returns False (skip the call)."""
        until, streak = self._breaker()
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

    def candles(self, exch, token, interval, frm, to):
        # same series asked again in this run (e.g. RSI engine, then MCX buy/sell engine) -> reuse, saves API quota
        self._cc = getattr(self, "_cc", {})
        key = (exch, str(token), interval)
        hit = self._cc.get(key)
        if hit is not None and hit[0] <= frm and abs((to - hit[1]).total_seconds()) <= 300:
            self.stats["mem_hits"] += 1
            return hit[2][hit[2]["time"] >= frm].reset_index(drop=True)
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
                    if not self._gate():
                        self.stats["skipped"] += 1
                        break
                    self._wait(self.QUOTE_GAP)
                    self._count()
                    try:
                        r = self.api.getMarketData("FULL", {ex: toks[i:i + 50]})
                        if r and self._is_rate(f"{r.get('message', '')} {r.get('errorcode', '')}"):
                            self._trip()
                            continue
                        for q in (r.get("data") or {}).get("fetched", []):
                            out[str(q["symbolToken"])] = q
                        self.stats["ok"] += 1
                        self._reset()
                        break
                    except Exception as e:
                        print("quote error:", str(e)[:120])
                        if self._is_rate(e):
                            self._trip()
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

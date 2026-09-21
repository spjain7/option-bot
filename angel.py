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
    def __init__(self):
        from SmartApi import SmartConnect
        import pyotp
        self.api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
        totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"].replace(" ", "")).now()
        s = self.api.generateSession(os.environ["ANGEL_CLIENT_ID"], os.environ["ANGEL_PIN"], totp)
        if not s or not s.get("status"):
            raise RuntimeError(f"Angel login failed: {s}")
        self._last = 0.0

    def _wait(self, gap=0.4):
        d = time.time() - self._last
        if d < gap:
            time.sleep(gap - d)
        self._last = time.time()

    def _call(self, fn, *a, retries=3):
        for i in range(retries):
            self._wait()
            try:
                r = fn(*a)
                if r and r.get("status") and r.get("data") is not None:
                    return r["data"]
            except Exception as e:
                print("API error:", e)
            time.sleep(1 + i)
        return None

    def candles(self, exch, token, interval, frm, to):
        d = self._call(self.api.getCandleData, {
            "exchange": exch, "symboltoken": str(token), "interval": interval,
            "fromdate": frm.strftime("%Y-%m-%d %H:%M"), "todate": to.strftime("%Y-%m-%d %H:%M")})
        if not d:
            return None
        df = pd.DataFrame(d, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = _naive(df["time"])
        return df

    def oi_history(self, exch, token, interval, frm, to):
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
                self._wait(0.6)
                try:
                    r = self.api.getMarketData("FULL", {ex: toks[i:i + 50]})
                    for q in (r.get("data") or {}).get("fetched", []):
                        out[str(q["symbolToken"])] = q
                except Exception as e:
                    print("quote error:", e)
        return out


# ─────────────── scrip master ───────────────
def load_master():
    f = CACHE / f"scrip_{now_ist():%Y%m%d}.json"
    if not f.exists():
        for old in CACHE.glob("scrip_*.json"):
            old.unlink()
        f.write_bytes(requests.get(SCRIP_URL, timeout=180).content)
    df = pd.DataFrame(json.loads(f.read_text()))
    keep = df["instrumenttype"].isin(["OPTIDX", "OPTSTK", "FUTIDX", "FUTSTK"]) & (df["exch_seg"] == "NFO")
    eq = (df["exch_seg"] == "NSE") & df["symbol"].str.endswith("-EQ")
    mcx = (df["exch_seg"] == "MCX") & df["instrumenttype"].isin(["FUTCOM", "OPTFUT", "OPTCOM"])
    df = df[keep | eq | mcx].copy()
    df["expiry_dt"] = pd.to_datetime(df["expiry"], format="%d%b%Y", errors="coerce")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["lotsize"] = pd.to_numeric(df["lotsize"], errors="coerce")
    return df

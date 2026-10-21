"""Offline stand-ins for the Angel client, built from REAL recorded candles (research/data/angel) or synthetic frames.
The fake behaves like Angel: candles with start time ≤ now are returned, INCLUDING the one still forming."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research" / "data" / "angel" / "MCX"


def master(extra=()):
    rows = [dict(name="CRUDEOIL", exch_seg="MCX", instrumenttype="FUTCOM", symbol="CRUDEOIL19NOV26FUT", token="573422",
                 lotsize=100, tick_size="100.000000", expiry_dt=pd.Timestamp("2026-11-19")),
            dict(name="CRUDEOIL", exch_seg="MCX", instrumenttype="FUTCOM", symbol="CRUDEOIL18DEC26FUT", token="576264",
                 lotsize=100, tick_size="100.000000", expiry_dt=pd.Timestamp("2026-12-18")),
            dict(name="CRUDEOIL", exch_seg="MCX", instrumenttype="FUTCOM", symbol="CRUDEOIL19JAN27FUT", token="580001",
                 lotsize=100, tick_size="100.000000", expiry_dt=pd.Timestamp("2027-01-19")),
            dict(name="CRUDEOILM", exch_seg="MCX", instrumenttype="FUTCOM", symbol="CRUDEOILM19NOV26FUT", token="573500",
                 lotsize=10, tick_size="100.000000", expiry_dt=pd.Timestamp("2026-11-19")),
            dict(name="CRUDEOILM", exch_seg="MCX", instrumenttype="FUTCOM", symbol="CRUDEOILM18DEC26FUT", token="576300",
                 lotsize=10, tick_size="100.000000", expiry_dt=pd.Timestamp("2026-12-18"))]
    return pd.DataFrame(rows + list(extra))


def load(sym, iv):
    f = DATA / f"{sym}_{iv}.csv"
    return pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]] if f.exists() else None


class FakeAngel:
    """series: {(token, interval): DataFrame}. Mini contract (no recorded data) mirrors the main contract's candles."""
    def __init__(self, series, oi=None, now=None, fail=()):
        self.series, self.oi, self.now, self.fail, self.calls = series, oi or {}, now, set(fail), []

    def candles(self, exch, token, interval, frm, to):
        self.calls.append(("candles", token, interval))
        if (token, interval) in self.fail or "candles" in self.fail:
            return None
        d = self.series.get((str(token), interval))
        if d is None:
            return None
        return d[(d["time"] >= frm) & (d["time"] <= min(to, self.now))].reset_index(drop=True)

    def quotes(self, et):
        self.calls.append(("quotes",))
        if "quotes" in self.fail:
            return {}
        out = {}
        for toks in et.values():
            for t in toks:
                d = self.series.get((str(t), "FIFTEEN_MINUTE"))
                if d is None:
                    continue
                d = d[d["time"] <= self.now]
                if d.empty:
                    continue
                last = d.iloc[-1]
                forming = self.now < last["time"] + pd.Timedelta(minutes=15)
                feed = min(self.now, last["time"] + pd.Timedelta(minutes=14, seconds=59))
                px = float(last["open"] if forming else last["close"])    # never leak the forming candle's close
                out[str(t)] = dict(ltp=px, opnInterest=self.oi.get(str(t), 1400000), tradeVolume=40000,
                                   exchFeedTime=feed.strftime("%d-%b-%Y %H:%M:%S"))
        return out


def real_api(now):
    s = {}
    for sym, tok in (("CRUDEOIL19NOV26FUT", "573422"), ("CRUDEOIL18DEC26FUT", "576264")):
        for iv in ("FIFTEEN_MINUTE", "ONE_HOUR"):
            d = load(sym, iv)
            if d is not None:
                s[(tok, iv)] = d
    s[("573500", "FIFTEEN_MINUTE")] = s[("573422", "FIFTEEN_MINUTE")]     # mini mirrors main (offline only)
    return FakeAngel(s, now=now)

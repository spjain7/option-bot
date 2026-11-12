"""Data layer for the MCX institutional BUY research engine (research only, read-only on all source files).

Sources (all REAL observations unless marked):
  research/data/angel/MCX/*_{FIVE_MINUTE,ONE_HOUR,ONE_DAY}.csv  Angel One SmartAPI front-month stitched futures (manifest
                                                                 rows with front_stitched=True). 7 commodities.
  research/data/mcx_bhav/days/YYYYMMDD.csv                       MCX official daily bhavcopy, every contract, with OI.
  research/data/proxy/*_1d.csv, USDINR_1d.csv                    international benchmark futures (Yahoo daily), USD/INR.
Derived (CALCULATED, disclosed):
  15m / 30m bars    resampled from 5-minute bars, anchored at 09:00 IST
  4h bars           resampled from 1-hour bars, anchored at 09:00 (09-13, 13-17, 17-21, 21-close)
  LEAD daily        built from the bhavcopy: nearest contract with > 4 days to expiry (switch when it changes)
  roll ratio        at each contract switch: next / expiring contract close on the last common day (bhavcopy, exact)
                    where available, else the switch bar open / previous close (INFERRED, includes a real overnight gap)
  adjusted prices   multiplicative back-adjustment, used ONLY for indicators / levels; trades are simulated on raw prices and
                    never held across a switch.
  daily OI          sum of oi_lots over all futures expiries of the symbol (rollover-neutral aggregate).
"""
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "research/data"
CACHE = DATA / "mcxib_cache"
INTRA = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]
ALL9 = INTRA + ["LEAD", "NICKEL"]
IV = {"5m": "FIVE_MINUTE", "1h": "ONE_HOUR", "1d": "ONE_DAY"}
TF_MIN = {"15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}


def _raw(name, iv):
    man = pd.read_csv(DATA / "angel/manifest.csv")
    m = man[(man.exch == "MCX") & (man.name == name) & (man.interval == iv) & (man.front_stitched.astype(str) == "True")]
    if m.empty:
        return None
    p = DATA / "angel/MCX" / f"{m.symbol.iat[0]}_{iv}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
    return d.sort_values("time").reset_index(drop=True)


@lru_cache(maxsize=None)
def bhav():
    """every futures row of the bhavcopy (date, symbol, expiry, OHLC, volume, OI)."""
    fp = CACHE / "bhav_fut.pkl"
    if fp.exists():
        return pd.read_pickle(fp)
    fs = sorted((DATA / "mcx_bhav/days").glob("*.csv"))
    cols = ["date", "symbol", "instrument", "expiry", "open", "high", "low", "close", "volume_lots", "oi_lots"]
    D = pd.concat([pd.read_csv(f, usecols=cols) for f in fs], ignore_index=True)
    D = D[D.instrument.astype(str).str.startswith("FUT") & D.symbol.isin(ALL9)].copy()
    D["date"] = pd.to_datetime(D.date); D["expiry"] = pd.to_datetime(D.expiry, format="%d%b%Y", errors="coerce")
    D = D.drop(columns="instrument").reset_index(drop=True)
    CACHE.mkdir(parents=True, exist_ok=True); D.to_pickle(fp)
    return D


def daily_oi(name):
    """date-indexed: total OI (all expiries), total volume (lots), n contracts with OI. Official end-of-day values."""
    B = bhav(); g = B[B.symbol == name]
    return g.groupby("date").agg(oi=("oi_lots", "sum"), vol=("volume_lots", "sum"), n_oi=("oi_lots", lambda s: int((s > 0).sum())))


def roll_ratio(name, switch_dates):
    """exact roll ratio from the bhavcopy: on the last trading day before each switch, close(next) / close(expiring)."""
    B = bhav(); g = B[(B.symbol == name) & (B.close > 0)]
    out = {}
    days = np.sort(g.date.unique())
    for s in switch_dates:
        prev = days[days < np.datetime64(s)]
        if not len(prev):
            continue
        d0 = prev[-1]; x = g[g.date == d0].sort_values("expiry")
        x = x[x.expiry >= d0]
        if len(x) >= 2:
            out[pd.Timestamp(s)] = float(x.close.iloc[1] / x.close.iloc[0])
    return out


def _switch_flags(name, d):
    from research.search import strategy_search as SS
    sw = SS.switch_days(name, "MCX", d)
    day = d.time.dt.normalize()
    return (day.isin(sw) & (day != day.shift(1))).values


def lead_daily(name="LEAD"):
    """daily series from the bhavcopy: the nearest contract with more than 4 calendar days to expiry (roll 5 days early,
    like the Angel stitched series). Used for LEAD (no Angel data) and NICKEL. Days with zero volume are dropped."""
    B = bhav(); g = B[(B.symbol == name) & (B.volume_lots > 0) & (B.close > 0) & ((B.expiry - B.date).dt.days > 4)]
    g = g.sort_values(["date", "expiry"]).groupby("date").head(1)
    d = g.rename(columns={"date": "time", "volume_lots": "volume"})[["time", "open", "high", "low", "close", "volume", "expiry"]]
    d = d.reset_index(drop=True)
    sw = np.array(d.expiry != d.expiry.shift(1), dtype=bool); sw[0] = False
    ratios = {}
    for i in np.where(sw)[0]:
        prev = B[(B.symbol == name) & (B.date == d.time.iloc[i - 1])]
        a = prev[prev.expiry == d.expiry.iloc[i - 1]].close; b = prev[prev.expiry == d.expiry.iloc[i]].close
        if len(a) and len(b) and a.iloc[0] > 0 and b.iloc[0] > 0:
            ratios[d.time.iloc[i].normalize()] = float(b.iloc[0] / a.iloc[0])
    return d.drop(columns="expiry"), sw, ratios


def resample(d, minutes):
    day = d.time.dt.normalize()
    if minutes >= 1440:
        k = pd.Series(0, index=d.index)
    else:
        k = ((d.time - day).dt.total_seconds() // 60 - 540) // minutes
    g = d.groupby([day, k], sort=True)
    return g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                 volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)


def bars(name, tf):
    """OHLCV + switch flag + segment id + adjusted OHLC (indicators only) + roll-source flag for one commodity/timeframe."""
    fp = CACHE / f"bars_{name}_{tf}.pkl"
    if fp.exists():
        return pd.read_pickle(fp)
    exact = {}
    if name in ("LEAD", "NICKEL"):
        if tf != "1d":
            return None
        d, sw, exact = lead_daily(name); d["switch"] = sw
    else:
        src = "5m" if tf in ("15m", "30m") else ("1h" if tf in ("1h", "4h") else "1d")
        d = _raw(name, IV[src])
        if d is None:
            return None
        d = d.drop_duplicates("time").reset_index(drop=True)
        d["volume"] = d.volume.clip(lower=0)
        d["switch"] = _switch_flags(name, d)
        if tf in ("15m", "30m", "4h"):
            d = resample(d, TF_MIN[tf])
        if tf != "1d":
            hm = d.time.dt.hour * 60 + d.time.dt.minute
            d = d[(hm >= 540) & (hm < 23 * 60 + 55)].reset_index(drop=True)
        exact = roll_ratio(name, d.time[d.switch.astype(bool)].dt.normalize().unique())
    d = d.reset_index(drop=True)
    d["seg"] = np.cumsum(d.switch.astype(bool).values)
    # back-adjust: walking backwards, multiply everything before a switch by that switch's ratio
    f = np.ones(len(d)); src_flag = np.zeros(len(d), np.int8)
    idx = np.where(d.switch.astype(bool).values)[0]
    for i in idx[::-1]:
        day = d.time.iloc[i].normalize()
        r = exact.get(day)
        if r is None:
            r = float(d.open.iloc[i] / d.close.iloc[i - 1]) if i > 0 else 1.0
            src_flag[i] = 2
        else:
            src_flag[i] = 1
        f[:i] *= r
    for x in ("open", "high", "low", "close"):
        d[f"a_{x}"] = d[x].values * f
    d["roll_src"] = src_flag            # 1 exact (bhavcopy), 2 inferred (switch bar open / previous close)
    d["name"] = name
    CACHE.mkdir(parents=True, exist_ok=True); d.to_pickle(fp)
    return d


def proxy_daily(name):
    """international benchmark daily (Yahoo, USD), date-indexed. None if unavailable (ZINC, LEAD, NICKEL)."""
    p = DATA / "proxy" / f"{name}_1d.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p); d["time"] = pd.to_datetime(d.iloc[:, 0]); return d.set_index("time")[["open", "high", "low", "close"]]


def usdinr():
    d = pd.read_csv(DATA / "proxy/USDINR_1d.csv"); d["time"] = pd.to_datetime(d.iloc[:, 0]); return d.set_index("time")["close"]

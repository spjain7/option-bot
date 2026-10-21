"""Estimated roll adjustment for Angel One's vendor-stitched MCX front-month series.

Angel keeps the expiring contract until its expiry (including the illiquid tender/delivery days, volume often < 100)
and switches to the next contract the following day, which then shows a volume jump. That switch day is detected
inside a window around the contract's expiry rule. The roll gap is ESTIMATED as the part of that day's MCX return
that the proxy market (international future x USD/INR) does not explain; zinc has no proxy, so the average MCX
return of copper and aluminium that day is used. The series is then back-adjusted by those gaps.

Validation: the same gap estimator applied to Angel's NIFTY/BANKNIFTY stitched series (with the cash index as the
"proxy") is compared with the TRUE roll gaps from NSE bhavcopy -> research/output_v2/roll_estimator_validation.csv.
Data holes (calendar gaps > 7 days, e.g. Angel has no MCX data Dec-2021 → Apr-2022) are reported, not filled.
"""
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
# expiry rule: which months the main contract expires in, and the rule day used to centre the search window
RULES = {"GOLD": ((2, 4, 6, 8, 10, 12), 5), "SILVER": ((3, 5, 7, 9, 12), 5), "CRUDEOIL": (tuple(range(1, 13)), 19),
         "NATURALGAS": (tuple(range(1, 13)), 26), "COPPER": (tuple(range(1, 13)), 31), "ZINC": (tuple(range(1, 13)), 31),
         "ALUMINIUM": (tuple(range(1, 13)), 31)}
PROXY_FILE = {"GOLD": "GOLD_1d", "SILVER": "SILVER_1d", "CRUDEOIL": "CRUDEOIL_1d", "NATURALGAS": "NATURALGAS_1d",
              "COPPER": "COPPER_1d", "ALUMINIUM": "ALUMINIUM_1d", "NIFTY": "NIFTY_SPOT_1d", "BANKNIFTY": "BANKNIFTY_SPOT_1d"}
HOLE_DAYS = 7


def _ret(path):
    d = pd.read_csv(path, parse_dates=["time"]).set_index("time")["close"]
    d.index = d.index.normalize()
    return d.pct_change()


def expected_return(name, dates, peers=None):
    """Return the market move that is NOT a roll, for each date (proxy x FX, or peer MCX average for zinc)."""
    if name in PROXY_FILE and (DATA / "proxy" / f"{PROXY_FILE[name]}.csv").exists():
        r = _ret(DATA / "proxy" / f"{PROXY_FILE[name]}.csv")
        if name not in ("NIFTY", "BANKNIFTY"):
            r = r.add(_ret(DATA / "proxy" / "USDINR_1d.csv"), fill_value=0)
        return r.reindex(dates)
    if peers is not None:
        return peers.reindex(dates)
    return pd.Series(np.nan, index=dates)


def holes(df):
    g = df["time"].diff().dt.days
    return df.loc[g > HOLE_DAYS, "time"].tolist(), g


def detect_rolls(df, name):
    """Switch days: inside each expiry window, the day with the biggest volume jump vs the prior 3 days."""
    months, day = RULES[name]
    t = df["time"]; vol = df["volume"].astype(float)
    ratio = vol / vol.shift(1).replace(0, np.nan)                    # new contract's volume vs the expiring one's last day
    out = []
    for y in range(t.dt.year.min(), t.dt.year.max() + 1):
        for m in months:
            last = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
            rule = min(pd.Timestamp(y, m, min(day, last.day)), last)
            w = df[(t >= rule - pd.Timedelta(days=6)) & (t <= rule + pd.Timedelta(days=10))].index
            if len(w) == 0:
                continue
            i = ratio.loc[w].idxmax() if ratio.loc[w].notna().any() else None
            if i is not None and ratio.loc[i] >= 2.0:
                out.append(i)
    return sorted(set(out))


def adjust(df, name, peers=None):
    """Returns (adjusted frame, roll table). Prices before each detected switch are shifted by the estimated gap."""
    df = df.copy().reset_index(drop=True)
    dates = df["time"].dt.normalize()
    exp = expected_return(name, dates, peers).values
    rolls = detect_rolls(df, name)
    rows = []
    gap = np.zeros(len(df))
    for i in rolls:
        if i == 0:
            continue
        prev = df.at[i - 1, "close"]
        e = exp[i] if not np.isnan(exp[i]) else 0.0
        g = df.at[i, "close"] - prev * (1 + e)                       # move not explained by the market = roll gap
        gap[i - 1] = g                                               # old contract's last day still unadjusted
        rows.append(dict(name=name, switch_day=df.at[i, "time"], prev_close=prev, close=df.at[i, "close"],
                         market_move_pct=round(e * 100, 3), est_gap_pts=round(g, 2), est_gap_pct=round(g / prev * 100, 3),
                         vol_before=df.at[i - 1, "volume"], vol_after=df.at[i, "volume"],
                         proxy_missing=bool(np.isnan(exp[i]))))
    shift = pd.Series(gap)[::-1].cumsum()[::-1].values
    for k in ("open", "high", "low", "close"):
        df["raw_" + k] = df[k]
        df[k] = df[k] + shift
    df["offset"] = shift
    df["roll"] = gap != 0
    df["roll_gap"] = gap
    df["contract"] = "ANGEL-FRONT-ADJ"
    return df, pd.DataFrame(rows)


def validate_on_index(nse_cont, angel, name):
    """Gap estimator vs TRUE roll gaps (NSE bhavcopy) at the real expiry switch days of Angel's index series."""
    rows = []
    a = angel.set_index(angel["time"].dt.normalize())
    exp = expected_return(name, a.index)
    # bhavcopy: for each monthly expiry E, true gap = next contract close - expiring contract close on E
    from research.adapters.nse_bhavcopy import load
    r = load([name])
    from research.continuous import monthly_contracts, _clean
    r = monthly_contracts(_clean(r))
    exps = sorted(r["expiry"].unique())
    for k, E in enumerate(exps[:-1]):
        E = pd.Timestamp(E); N = pd.Timestamp(exps[k + 1])
        old = r[(r.expiry == E) & (r.date == E)]; new = r[(r.expiry == N) & (r.date == E)]
        nxt = a.index[a.index > E]
        if old.empty or new.empty or len(nxt) == 0 or E not in a.index:
            continue
        d = nxt[0]
        prev = a.at[E, "close"]
        est = a.at[d, "close"] - prev * (1 + (exp.get(d) if pd.notna(exp.get(d)) else 0))
        true = float(new.close.iloc[0] - old.close.iloc[0])
        rows.append(dict(name=name, expiry=E, switch_day=d, true_gap_pct=round(true / prev * 100, 3),
                         est_gap_pct=round(est / prev * 100, 3)))
    return pd.DataFrame(rows)


_CACHE = {}


def load_mcx(name, adjusted=True):
    """Angel MCX front-month daily, with data-hole flags; back-adjusted by ESTIMATED roll gaps when adjusted=True."""
    from research import continuous as CO
    key = (name, adjusted)
    if key in _CACHE:
        return _CACHE[key]
    d = CO.load_angel(name, "ONE_DAY")
    if d is None:
        return None, pd.DataFrame()
    d = d.reset_index(drop=True)
    tab = pd.DataFrame()
    if adjusted:
        peers = None
        if name == "ZINC":                       # no proxy: use same-day MCX copper/aluminium average move
            rs = []
            for p in ("COPPER", "ALUMINIUM"):
                x = CO.load_angel(p, "ONE_DAY").set_index("time")["close"]
                x.index = x.index.normalize(); rs.append(x.pct_change())
            peers = pd.concat(rs, axis=1).mean(axis=1)
        d, tab = adjust(d, name, peers)
        d["contract"] = "ANGEL-FRONT-ADJ"
    else:
        d["contract"] = "ANGEL-FRONT"
    g = d["time"].diff().dt.days
    d["hole"] = (g > HOLE_DAYS).values
    _CACHE[key] = (d, tab)
    return d, tab

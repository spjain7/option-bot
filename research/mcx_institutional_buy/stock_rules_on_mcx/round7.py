"""ROUND 7 (owner 17-Nov-2026): breakout / breakdown entries not tested before, per commodity, BUY and SELL.
All entries are STOP orders at the level (filled at the level, or at the open if the candle gaps through it).
  1-hour candles (Jul-2022 ->)
    ORB1   first hour (09:00) range: buy-stop above its high / sell-stop below its low, valid until 23:00 the same day
    ORB2   first two hours (09:00-11:00) range, valid until 23:00
    ORBE   evening hour (17:00, US session) range, valid until 23:00
    PDH    previous day's high (sell: low), valid the whole next day
    BOX    consolidation: the last 10 / 20 hourly candles fit inside 2 / 3 / 4 ATR -> stop order at the box edge, valid 5 candles
    stops  the range's other side (STRUCT; box: its other edge), or 2 / 3 hourly ATR from the entry level
    hold   EOD (closed at the day's last candle) or SWING (up to 40 hourly candles)
  daily candles (2006 ->)
    NR7    today's range is the smallest of 7 days -> next day stop order at today's high / low
    IDNR7  NR7 and an inside day
    PWH    previous week's high / low, valid all week
    BOX    last 10 / 20 days inside 3 / 4 / 5 ATR -> stop order at the box edge, valid 5 days
    stops  STRUCT (the day's / week's / box's other side) or 1 / 1.5 / 2 daily ATR      hold up to 20 days
  targets 1 / 1.5 / 2 / 3 x risk, or a 3 ATR trailing stop        filter none / DT (daily trend on our side)
  pick    per commodity and side, on TRAIN + VALID only (robust score + neighbours + better than random entries with the
          same stop size, target and holding, 200 draws). OOS shown unchanged.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round7 -> reports/mcx_round7.csv, mcx_round7_pick.json"""
import json
import warnings
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames, dtrend

warnings.filterwarnings("ignore")
TG = [(0, 1.0), (0, 1.5), (0, 2.0), (0, 3.0), (2, 0.0)]
MULT = R4.MULT


def mirror(f, side):
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    return (o, h, l, c) if side > 0 else (-o, -l, -h, -c)


def setups_1h(f, dd, side):
    """-> list of (fam, sig, level, struct_stop, win)."""
    o, h, l, c = mirror(f, side); t = pd.to_datetime(f["time"]); day = t.dt.normalize().values; hr = t.dt.hour.values
    n = len(c); out = []
    dser = pd.Series(np.arange(n)).groupby(day)
    last_of_day = np.zeros(n, bool); last_of_day[dser.max().values] = True
    first_idx = dser.transform("min").values
    for fam, hrs in (("ORB1", (9,)), ("ORB2", (9, 10)), ("ORBE", (17,))):
        sig = np.zeros(n, bool); lvl = np.full(n, np.nan); st = np.full(n, np.nan)
        end = hrs[-1]
        for i in np.where(hr == end)[0]:
            j0 = i - (len(hrs) - 1)
            if j0 < 0 or day[j0] != day[i] or hr[j0] != hrs[0]:
                continue
            sig[i] = True; lvl[i] = h[j0:i + 1].max(); st[i] = l[j0:i + 1].min()
        out.append((fam, sig, lvl, st, 14))
    # previous day's high: signal on the day's last candle, level = that day's high
    dh = pd.Series(h).groupby(day).transform("max").values; dl = pd.Series(l).groupby(day).transform("min").values
    out.append(("PDH", last_of_day & (c < dh), dh, dl, 15))
    for N in (10, 20):
        hh = pd.Series(h).rolling(N).max().values; ll = pd.Series(l).rolling(N).min().values
        w = (hh - ll) / f["atr"].values
        for cw in (2, 3, 4):
            out.append((f"BOX{N}_{cw}", (w <= cw) & (c < hh), hh, ll, 5))
    return out


def setups_1d(f, side):
    o, h, l, c = mirror(f, side); n = len(c); rg = h - l
    out = []
    nr7 = rg <= pd.Series(rg).rolling(7).min().values
    inside = (h < np.r_[np.nan, h[:-1]]) & (l > np.r_[np.nan, l[:-1]])
    out.append(("NR7", nr7, h, l, 1)); out.append(("IDNR7", nr7 & inside, h, l, 1))
    t = pd.to_datetime(f["time"]); wk = t.dt.to_period("W").values
    wh = pd.Series(h).groupby(wk).transform("max").values; wl = pd.Series(l).groupby(wk).transform("min").values
    lastw = np.r_[wk[1:] != wk[:-1], True]
    out.append(("PWH", lastw & (c < wh), wh, wl, 5))
    for N in (10, 20):
        hh = pd.Series(h).rolling(N).max().values; ll = pd.Series(l).rolling(N).min().values
        w = (hh - ll) / f["atr"].values
        for cw in (3, 4, 5):
            out.append((f"BOX{N}_{cw}", (w <= cw) & (c < hh), hh, ll, 5))
    return out


NAN = {}


def sim(f, side, sig, lvl, stop, win, kind, r, maxh, seg, name):
    o, h, l, c = mirror(f, side); a = f["atr"].values.astype(float); n = len(c)
    NAN.setdefault(n, np.full(n, np.nan))
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * side
    return S.simulate(o, h, l, c, a, seg, costf, np.asarray(sig, bool), stop, lvl, NAN[n], kind, float(r), int(maxh), int(maxh),
                      3.0, int(win), 0.25, 6.0, 1.0)[:8]


def pst(nr, pe):
    o = {}
    for p in ("TRAIN", "VAL", "OOS"):
        x = nr[pe == p]; o[f"{p}_n"] = len(x)
        o[f"{p}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else np.nan
        o[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else np.nan
    return o


def grid(name):
    F, dd = frames(name); rows = []; keep = {}
    f1 = F["1h"].reset_index(drop=True); f1["atr"] = f1["atr"].values
    t1 = pd.to_datetime(f1["time"]); per1 = RN.period_of("1h", t1)
    dayid = pd.factorize(t1.dt.normalize())[0]
    seg_eod = (f1["seg"].values.astype(np.int64) * 100000 + dayid).astype(np.int64); seg_sw = f1["seg"].values.astype(np.int64)
    fd = R4.feats(dd); td = pd.to_datetime(fd["time"]); perd = RN.period_of("1d", td)
    dt1 = dtrend(f1, dd); dtd = dtrend(fd, dd)
    jobs = []
    for side in (1, -1):
        for fam, sig, lvl, st, win in setups_1h(f1, dd, side):
            for flt in ("none", "DT"):
                s = sig & (dt1 == side) if flt == "DT" else sig
                for stp in ("STRUCT", 2.0, 3.0):
                    stop = st if stp == "STRUCT" else lvl - stp * f1["atr"].values
                    for hold, seg, mh in (("EOD", seg_eod, 15), ("SWING", seg_sw, 40)):
                        jobs.append(("1h", side, fam, flt, stp, hold, s, lvl, stop, win, seg, mh, f1, per1))
        for fam, sig, lvl, st, win in setups_1d(fd, side):
            for flt in ("none", "DT"):
                s = sig & (dtd == side) if flt == "DT" else sig
                for stp in ("STRUCT", 1.0, 1.5, 2.0):
                    stop = st if stp == "STRUCT" else lvl - stp * fd["atr"].values
                    jobs.append(("1d", side, fam, flt, stp, "SWING", s, lvl, stop, win, fd["seg"].values.astype(np.int64), 20, fd, perd))
    for tf, side, fam, flt, stp, hold, s, lvl, stop, win, seg, mh, f, per in jobs:
        if s.sum() < 15:
            continue
        for kind, r in TG:
            si, ei, xi, g, nr, mfe, mae, why = sim(f, side, s, lvl, stop, win, kind, r, mh, seg, name)
            if len(nr) < 10:
                continue
            row = dict(name=name, tf=tf, side="BUY" if side > 0 else "SELL", fam=fam, filt=flt, stop=str(stp), hold=hold,
                       exit="trail 3ATR" if kind == 2 else f"{r:g}R", **pst(nr, per[ei]))
            rows.append(row)
    return rows


def main():
    rows = []
    for name in D.INTRA:
        rows += grid(name); print(name, len(rows), flush=True)
    L = pd.DataFrame(rows); L.to_csv(RN.REPORTS / "mcx_round7.csv", index=False)
    print("tested", len(L))


if __name__ == "__main__":
    main()

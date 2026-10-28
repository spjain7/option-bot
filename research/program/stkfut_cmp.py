"""STKFUT-CMP-001 (29-Oct-2026) – owner's request: compare components from 8 public GitHub repositories against the existing
stock-futures alerts, on IDENTICAL data and execution, with a FIXED 1:1 risk-reward. Research only, no production code.

Data: Angel One 1-hour candles of the FRONT stock-futures contract, 181 F&O stocks, Jul-2022 → Oct-2026 (contracts
concatenated, no price back-adjustment; the first day after each roll is excluded for intraday setups and exits before
a roll for swing setups). Daily OI label of the previous completed day (from Nov-2023). NIFTY daily (NSE 2011-26) for the
market regime of the PREVIOUS close; NIFTY futures 1-hour for intraday index direction.

Execution (all setups):
  • signal on a completed candle; entry at the NEXT candle's open ("next_open") or at a stop-order trigger level
    ("stop": filled at the trigger, or at the open if the candle opens beyond it)
  • stop as defined by the setup; target = entry ± 1 × risk (1:1)
  • a candle that opens beyond the stop or target fills at the open; if one candle touches both, the STOP is counted
  • intraday setups: no entry on the 15:15 candle; exit at the close of the day's last candle (15:15–15:30)
  • swing setups: max hold in daily candles, exit before a contract roll
  • one open trade per stock per setup
Costs per round trip per unit: STT on the sell leg by date (0.0125 % before 1-Oct-2024, 0.02 % until 31-Mar-2026,
0.05 % from 1-Apr-2026), NSE exchange 0.00173 % × 2, stamp 0.002 % (buy), SEBI, GST 18 % on brokerage + exchange,
brokerage ₹20 × 2 per lot (+GST) spread over the lot, slippage 0.03 % per side. Reported at 1× and 2×.
Periods: train < 1-Jul-2024 ≤ valid < 1-Jul-2025 ≤ test (untouched for these external rules: defaults taken from the
source repositories, no tuning). Null model: the same entries with a RANDOM side, to estimate how many variants pass by luck.
"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import reversal as RV, harness as H  # noqa: E402
from research.search import stock_search as SR, stock_oi_buy_run as RN  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
SLIP = 0.0003


def stt(day):
    return 0.000125 if day < pd.Timestamp("2024-10-01") else 0.0002 if day < pd.Timestamp("2026-04-01") else 0.0005


def cost_units(price, lot, day):
    """Round-trip cost per unit (price points)."""
    exch = 2 * 0.0000173; stamp = 0.00002; sebi = 2 * 1e-6
    gst = 0.18 * (exch + sebi)
    return price * (stt(day) + exch + stamp + sebi + gst + 2 * SLIP) + 40 * 1.18 / lot


# ─────────────── market regime (nse-trading-lab tape_monitor.assess_tape, on the PREVIOUS close) ───────────────
def nifty_regime():
    n = H.nseidx("NIFTY").sort_values("time")
    c = n.set_index(n["time"].dt.normalize())["close"].astype(float)
    e50, e200 = c.ewm(span=50, adjust=False).mean(), c.ewm(span=200, adjust=False).mean()
    ret60 = (c / c.shift(60) - 1) * 100
    slope = (e200 / e200.shift(20) - 1) * 100
    trend = (c > e50) & (e50 > e200) & (ret60 > 5) & (slope > 0.5)
    hostile = (c < e200) | (ret60 < -3) | (slope < -0.5)
    lab = pd.Series(np.where(trend, "TRENDING", np.where(hostile, "HOSTILE", "MIXED")), index=c.index)
    return lab.shift(1)                                         # known before the day starts


def nifty_intraday():
    x = RV.mcx_index_1h("NIFTY", "NFO")[1][["time", "open", "close"]].copy()
    x["day"] = x["time"].dt.normalize()
    x["day_open"] = x.groupby("day")["open"].transform("first")
    x["up"] = np.sign(x["close"] - x["day_open"])               # NIFTY up/down on the day so far (completed candle)
    return x.set_index("time")["up"]


# ─────────────── generic trade simulator ───────────────
def simulate(f, i, side, stop, entry_mode, trigger, intraday, max_days, lot, wait=3):
    o, h, l, c, sw = (f[x].values for x in ("open", "high", "low", "close", "switch"))
    day = f["day"].values
    n = len(c)
    j0 = None
    if entry_mode == "next_open":
        j0 = i + 1
        if j0 >= n or (intraday and (day[j0] != day[i] or f["hhmm"].iat[j0] == "15:15")):
            return None
        e0 = o[j0]
    else:
        for j in range(i + 1, min(i + 1 + wait, n)):
            if intraday and (day[j] != day[i] or f["hhmm"].iat[j] == "15:15"):
                break
            if side * (o[j] - trigger) > 0:
                j0, e0 = j, o[j]; break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                break
            if (h[j] > trigger) if side > 0 else (l[j] < trigger):
                j0, e0 = j, trigger; break
        if j0 is None:
            return None
    R = side * (e0 - stop)
    if not R > 0 or R / e0 > 0.06:
        return None
    tp = e0 + side * R
    px = why = None; j = j0
    days_seen = {day[j0]}
    while j < n:
        if j > j0 and sw[j]:
            px, why, j = c[j - 1], "roll", j - 1; break
        if j > j0:
            if side * (o[j] - stop) <= 0:
                px, why = o[j], "stop-gap"; break
            if side * (o[j] - tp) >= 0:
                px, why = o[j], "target-gap"; break
        s_hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
        t_hit = (h[j] >= tp) if side > 0 else (l[j] <= tp)
        if s_hit:
            px, why = stop, "stop" + ("*" if t_hit else ""); break
        if t_hit:
            px, why = tp, "target"; break
        if intraday and (j + 1 >= n or day[j + 1] != day[j]):
            px, why = c[j], "eod"; break
        days_seen.add(day[j])
        if not intraday and len(days_seen) > max_days:
            px, why = c[j], "time"; break
        j += 1
    if px is None:
        return None
    cu = cost_units(e0, lot, pd.Timestamp(day[j0]))
    g = side * (px - e0)
    return dict(j0=j0, j=j, entry=e0, stop=stop, target=tp, exit=px, why=why, R=R, gross_R=g / R,
                net_R=(g - cu) / R, net2_R=(g - 2 * cu) / R, cost_R=cu / R, rs=(g - cu) * lot, hold=j - j0 + 1)


# ─────────────── setups ───────────────
def prep(f, lot):
    f = f.copy().reset_index(drop=True)
    f["day"] = f["time"].dt.normalize()
    f["hhmm"] = f["time"].dt.strftime("%H:%M")
    f = f[f["hhmm"].isin(["09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"])].reset_index(drop=True)
    g = f.groupby("day")
    d = g.agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"), v=("volume", "sum"),
              roll=("switch", "max"))
    d["pdh"], d["pdl"], d["pdc"] = d["h"].shift(1), d["l"].shift(1), d["c"].shift(1)
    tr = pd.concat([d["h"] - d["l"], (d["h"] - d["c"].shift(1)).abs(), (d["l"] - d["c"].shift(1)).abs()], axis=1).max(axis=1)
    d["datr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().shift(1)   # previous days only
    for k in ("pdh", "pdl", "pdc", "datr"):
        f[k] = f["day"].map(d[k])
    f["rollday"] = f["day"].map(d["roll"]).astype(bool)
    f["first_h"] = f["day"].map(g["high"].first()); f["first_l"] = f["day"].map(g["low"].first())
    f["first_c"] = f["day"].map(g["close"].first()); f["first_o"] = f["day"].map(g["open"].first())
    f["bar"] = g.cumcount()
    return f, d


def setups_hourly(f):
    """Yields (setup, i, side, stop, entry_mode, trigger)."""
    hh, bar = f["hhmm"].values, f["bar"].values
    o, h, l, c = (f[x].values for x in ("open", "high", "low", "close"))
    vw, e20, atr = f["vwap"].values, f["ema20"].values, f["atr"].values
    fh, fl, fc, fo = (f[x].values for x in ("first_h", "first_l", "first_c", "first_o"))
    pdh, pdl, roll = f["pdh"].values, f["pdl"].values, f["rollday"].values
    done = {}
    for i in range(len(f)):
        if roll[i] or not np.isfinite(atr[i]) or hh[i] == "15:15":
            continue
        dk = f["day"].iat[i]
        # ORB-60 (backtest-platform orb_breakout / intraday-playbook orb / zerodha-bot intraday_orb, adapted to the
        # first 1-hour candle): first later close beyond the range -> next open; stop = opposite end of the range.
        if bar[i] >= 1 and hh[i] <= "14:15" and not done.get(("ORB", dk)):
            if c[i] > fh[i]:
                done[("ORB", dk)] = True; yield ("ORB60", i, 1, fl[i], "next_open", None)
            elif c[i] < fl[i]:
                done[("ORB", dk)] = True; yield ("ORB60", i, -1, fh[i], "next_open", None)
        # VWAP pullback (kite-algo-bot strategies/vwap_pullback.py defaults: EMA20 trend, ≤ 0.5 ATR from VWAP,
        # previous candle tagged VWAP, close back on the trend side; stop VWAP ∓ 1.2 ATR) – here with 1:1 target.
        if bar[i] >= 2 and hh[i] <= "13:15" and np.isfinite(vw[i]) and atr[i] > 0:
            dist = abs(c[i] - vw[i]) / atr[i]
            if c[i] > e20[i] and vw[i] < c[i] and dist <= 0.5 and l[i - 1] <= vw[i - 1] and c[i] > vw[i]:
                yield ("VWAPPB", i, 1, vw[i] - 1.2 * atr[i], "next_open", None)
            elif c[i] < e20[i] and vw[i] > c[i] and dist <= 0.5 and h[i - 1] >= vw[i - 1] and c[i] < vw[i]:
                yield ("VWAPPB", i, -1, vw[i] + 1.2 * atr[i], "next_open", None)
        # Failed breakout / IB failure (nse-algo-trading-system screener.system_7_ib_failure / system_8_is_failure):
        # gap above the previous-day high but the first candle closes back below it -> SELL below that candle's low,
        # stop above its high (mirror for longs). Signal known at the close of the first candle.
        if bar[i] == 0 and np.isfinite(pdh[i]):
            if fo[i] > pdh[i] and fc[i] < pdh[i]:
                yield ("IBFAIL", i, -1, fh[i], "stop", fl[i])
            elif fo[i] < pdl[i] and fc[i] > pdl[i]:
                yield ("IBFAIL", i, 1, fl[i], "stop", fh[i])
        # Initiative / gap-and-go (intraday-playbook gap_and_go, nse-algo S3/S4): gap beyond PDH/PDL and the first
        # candle closes in the gap direction -> next open, stop at the first candle's opposite end.
        if bar[i] == 0 and np.isfinite(pdh[i]):
            if fo[i] > pdh[i] and fc[i] > fo[i]:
                yield ("GAPGO", i, 1, fl[i], "next_open", None)
            elif fo[i] < pdl[i] and fc[i] < fo[i]:
                yield ("GAPGO", i, -1, fh[i], "next_open", None)


def overlays(f, i, side, reg, nidx):
    day = f["day"].iat[i]
    r = reg.get(day)
    ni = nidx.get(f["time"].iat[i])
    rng = f["high"].iat[i] - f["low"].iat[i]
    pos = (f["close"].iat[i] - f["low"].iat[i]) / rng if rng > 0 else 0.5
    return dict(
        regime=r or "NA",
        RG=(r in ("TRENDING", "MIXED")) if side > 0 else (r == "HOSTILE"),
        V=bool(f["slotx"].iat[i] >= 1.5),
        O=f["oi_lab"].iat[i] == ("LB" if side > 0 else "SB"),
        N=(ni is not None and np.sign(ni) == side),
        C=(pos >= 0.7) if side > 0 else (pos <= 0.3),
        W=(f["close"].iat[i] > f["vwap"].iat[i]) if side > 0 else (f["close"].iat[i] < f["vwap"].iat[i]),
        NR=bool((f["first_h"].iat[i] - f["first_l"].iat[i]) <= 0.5 * f["datr"].iat[i]) if np.isfinite(f["datr"].iat[i]) else False)


# ─────────────── daily baselines (existing bot rules, at 1:1) ───────────────
def daily_frame(name, lot):
    S = RN.load_stock(name, lot)
    if S is None:
        return None
    f0 = S["f"]
    d = pd.DataFrame(dict(time=f0["time"], open=f0["open"], high=f0["high"], low=f0["low"], close=f0["close"],
                          volume=(f0["volx"] * f0["va"]).fillna(0), doi=f0["doi"], dp=f0["dp"]))
    sw = np.zeros(len(d), bool); sw[1:] = S["last"][:-1]; d["switch"] = sw
    d["day"] = d["time"].dt.normalize(); d["hhmm"] = "D"
    return d.reset_index(drop=True)


def setups_daily(d):
    c, h, l, o, v = (d[x].astype(float) for x in ("close", "high", "low", "open", "volume"))
    a = I.atr(d, 14); e200 = I.ema(c, 200); e20 = I.ema(c, 20); e50 = I.ema(c, 50)
    hh, ll = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    va = v.rolling(20).mean().shift(1)
    doi, dp = d["doi"], d["dp"]
    body, rng = (c - o).abs(), h - l
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    ham = (rng > 0) & (lw >= 2 * body) & (uw <= 0.3 * rng)
    r5 = c / c.shift(5) - 1
    bear = (c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))
    for i in range(210, len(d) - 1):
        if d["switch"].iat[i] or not a.iat[i] > 0:
            continue
        ai = a.iat[i]
        # B-OI: live stock OI-breakout rule (alerts/stocks.evaluate): 20-day breakout, volume > 1.5×, OI ≥ +2 %, EMA200 side; stop 2 ATR
        if c.iat[i] > hh.iat[i] and v.iat[i] > 1.5 * va.iat[i] and dp.iat[i] > 0 and doi.iat[i] >= 0.02 and c.iat[i] > e200.iat[i]:
            yield ("B_OIBRK", i, 1, c.iat[i] - 2 * ai, "next_open", None, 40)
        if c.iat[i] < ll.iat[i] and v.iat[i] > 1.5 * va.iat[i] and dp.iat[i] < 0 and doi.iat[i] >= 0.02 and c.iat[i] < e200.iat[i]:
            yield ("B_OIBRK", i, -1, c.iat[i] + 2 * ai, "next_open", None, 40)
        # B-BEARENG: live bearish engulfing after a rise, volume > 1.5×; stop 1.5 ATR, target 1R, 10 sessions
        if bear.iat[i] and r5.iat[i] > 0 and v.iat[i] > 1.5 * va.iat[i] and c.iat[i] > e20.iat[i]:
            yield ("B_BEARENG", i, -1, c.iat[i] + 1.5 * ai, "next_open", None, 10)
        # B-HANGMAN: live (29-Oct) hanging man in an uptrend, break of its low, stop above its high
        if ham.iat[i] and e20.iat[i] > e50.iat[i] and c.iat[i - 1] > e50.iat[i - 1]:
            yield ("B_HANGMAN", i, -1, h.iat[i] + 0.05 * ai, "stop", l.iat[i], 20)


def run(job):
    name, lot = job
    out = []
    try:
        x = RV.stock_1h(name, lot)
        reg, nidx = REG, NIDX
        if x is not None:
            f, _ = prep(x[1], lot)
            busy = {}
            for st, i, side, stop, em, trig in setups_hourly(f):
                if i <= busy.get(st, -1):
                    continue
                t = simulate(f, i, side, stop, em, trig, True, 1, lot)
                if t is None:
                    continue
                busy[st] = t["j"]
                ov = overlays(f, i, side, reg, nidx)
                out.append(dict(setup=st, tf="1h", name=name, time=f["time"].iat[i], side=side, **ov,
                                **{k: t[k] for k in ("entry", "stop", "target", "exit", "why", "R", "gross_R", "net_R", "net2_R", "cost_R", "rs", "hold")},
                                entry_time=f["time"].iat[t["j0"]], exit_time=f["time"].iat[t["j"]]))
        d = daily_frame(name, lot)
        if d is not None:
            busy = {}
            for st, i, side, stop, em, trig, mx in setups_daily(d):
                if i <= busy.get(st, -1):
                    continue
                t = simulate(d, i, side, stop, em, trig, False, mx, lot)
                if t is None:
                    continue
                busy[st] = t["j"]
                r = reg.get(d["day"].iat[i])
                out.append(dict(setup=st, tf="1d", name=name, time=d["time"].iat[i], side=side, regime=r or "NA",
                                RG=(r in ("TRENDING", "MIXED")) if side > 0 else (r == "HOSTILE"), V=False, O=False, N=False,
                                C=False, W=False, NR=False,
                                **{k: t[k] for k in ("entry", "stop", "target", "exit", "why", "R", "gross_R", "net_R", "net2_R", "cost_R", "rs", "hold")},
                                entry_time=d["time"].iat[t["j0"]], exit_time=d["time"].iat[t["j"]]))
    except Exception as e:
        print("skip", name, type(e).__name__, e)
    return out


REG, NIDX = None, None


def _init():
    global REG, NIDX
    REG = nifty_regime().to_dict()
    NIDX = nifty_intraday().to_dict()


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    jobs = [(n, int(l)) for n, l in zip(man["name"], man["lot"])]
    if len(sys.argv) > 1:
        jobs = jobs[: int(sys.argv[1])]
    with Pool(2, initializer=_init) as p:
        rows = [r for x in p.imap_unordered(run, jobs, chunksize=1) for r in x]
    T = pd.DataFrame(rows)
    T["time"] = pd.to_datetime(T["time"])
    T["split"] = np.where(T["time"] < "2024-07-01", "train", np.where(T["time"] < "2025-07-01", "valid", "test"))
    T.to_csv(OUT / "stkfut_cmp_trades.csv.gz", index=False)
    print(len(T), T.groupby("setup").size().to_dict())


if __name__ == "__main__":
    main()

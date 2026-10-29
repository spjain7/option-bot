"""OBUY-REAL-001 (29-Oct-2026) – option BUYING on the bot's stock-futures setups with REAL NSE option prices (daily bhavcopy).
Question: do the proven futures setups make money when traded through bought options, and do the 29-Oct option-buy rules
(strike, normal move vs risk, expensive premium, time stop) improve it?

Signals (stock futures, daily, 2022-07 → 2026-10, research/program data):
  HANGMAN  hanging man in an uptrend (live STK_HANGMAN), SELL
  OIBRK    live OI breakout (20-day breakout, volume > 1.5×, OI ≥ +2 %, EMA200 side), BUY and SELL
  BEARENG  live bearish engulfing after a rise, volume > 1.5×, SELL
Timing (daily data cannot show the option price at an intraday trigger, so everything is close-confirmed, open-filled):
  • setup confirmed on day c (HANGMAN: a close below the pattern low within 3 days; others: the signal day itself)
  • BUY the option at the real OPEN of day c+1 (contracts traded that day, open > 0)
  • futures stop / target as the futures rule (HANGMAN: above the pattern high, 2R; OIBRK: 2 ATR, 2R; BEARENG: 1.5 ATR, 1R),
    checked on futures DAILY CLOSES; exit the option at the next day's real OPEN (close if no open trade)
  • time exit after 10 sessions (option close); never held into the expiry week: expiry chosen ≥ 15 days after entry
Same timing traded on the futures themselves for comparison.
Option choices: ATM, 1 strike ITM, 1 strike OTM. Filters (from obuy/improve.py): IV ≤ 1.5× 20-day realised (IV from the previous
day's option close), normal move (1 daily ATR over 3 days) lifts the premium ≥ +30 %, time stop (exit at day 3 open if the
option is not +10 % at day-2 close).
Option costs per round trip: brokerage ₹20 × 2 + GST, exchange 0.03503 % of premium × 2, stamp 0.003 % (buy), STT on the sell
premium by date (0.0625 % → 0.1 % from 1-Oct-2024 → 0.15 % from 1-Apr-2026), slippage 1 % of premium per side.
Periods: train < Jul-24 ≤ valid < Jul-25 ≤ test.
"""
import functools
import math
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import stock_search as SR, stock_oi_buy_run as RN  # noqa: E402
from crude import indicators as I  # noqa: E402
sys.path.insert(0, str(ROOT))
import greeks as G  # noqa: E402

OUT = ROOT / "research/program/results"
OPT = ROOT / "research/data/nse_opt/days"
MAXD = 10


def stt_opt(day):
    return 0.000625 if day < pd.Timestamp("2024-10-01") else 0.001 if day < pd.Timestamp("2026-04-01") else 0.0015


def opt_cost_rs(buy, sell, lot, day):
    tb, ts = buy * lot, sell * lot
    brk = 40.0; exch = 0.0003503 * (tb + ts); sebi = 1e-6 * (tb + ts)
    return brk + exch + sebi + 0.18 * (brk + exch + sebi) + 0.00003 * tb + stt_opt(day) * ts + 0.01 * (tb + ts)


def fut_cost_rs(price, lot, day):
    stt = 0.000125 if day < pd.Timestamp("2024-10-01") else 0.0002 if day < pd.Timestamp("2026-04-01") else 0.0005
    return price * lot * (stt + 2 * 0.0000173 + 0.00002 + 2 * 0.0003 + 0.18 * 2 * 0.0000173) + 40 * 1.18


@functools.lru_cache(maxsize=400)
def day_file(d):
    fp = OPT / f"{pd.Timestamp(d):%Y%m%d}.csv"
    if not fp.exists():
        return None
    return pd.read_csv(fp, parse_dates=["date", "expiry"])


def signals(name, lot):
    S = RN.load_stock(name, lot)
    if S is None:
        return None, []
    f0 = S["f"]
    d = pd.DataFrame(dict(time=f0["time"], open=f0["open"], high=f0["high"], low=f0["low"], close=f0["close"],
                          volume=(f0["volx"] * f0["va"]).fillna(0), doi=f0["doi"], dp=f0["dp"])).reset_index(drop=True)
    sw = np.zeros(len(d), bool); sw[1:] = S["last"][:-1]; d["switch"] = sw
    d["day"] = d["time"].dt.normalize()
    o, h, l, c, v = (d[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    a = I.atr(d, 14); e200 = I.ema(c, 200); e20 = I.ema(c, 20); e50 = I.ema(c, 50)
    hh, ll = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    va = v.rolling(20).mean().shift(1)
    body, rng = (c - o).abs(), h - l
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    ham = (rng > 0) & (lw >= 2 * body) & (uw <= 0.3 * rng)
    bear = (c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))
    r5 = c / c.shift(5) - 1
    out = []
    for i in range(210, len(d) - 2):
        if d["switch"].iat[i] or not a.iat[i] > 0:
            continue
        ai = a.iat[i]
        if ham.iat[i] and e20.iat[i] > e50.iat[i] and c.iat[i - 1] > e50.iat[i - 1]:
            stop = h.iat[i] + 0.05 * ai
            for j in range(i + 1, min(i + 4, len(d) - 1)):
                if h.iat[j] >= stop:
                    break
                if c.iat[j] < l.iat[i]:
                    out.append(("HANGMAN", j, -1, stop, 2.0)); break
        if c.iat[i] > hh.iat[i] and v.iat[i] > 1.5 * va.iat[i] and d["dp"].iat[i] > 0 and d["doi"].iat[i] >= 0.02 and c.iat[i] > e200.iat[i]:
            out.append(("OIBRK", i, 1, c.iat[i] - 2 * ai, 2.0))
        if c.iat[i] < ll.iat[i] and v.iat[i] > 1.5 * va.iat[i] and d["dp"].iat[i] < 0 and d["doi"].iat[i] >= 0.02 and c.iat[i] < e200.iat[i]:
            out.append(("OIBRK", i, -1, c.iat[i] + 2 * ai, 2.0))
        if bear.iat[i] and r5.iat[i] > 0 and v.iat[i] > 1.5 * va.iat[i] and c.iat[i] > e20.iat[i]:
            out.append(("BEARENG", i, -1, c.iat[i] + 1.5 * ai, 1.0))
    d["atr"] = a
    lr = np.log(c).diff()
    d["hv20"] = lr.rolling(20).std() * math.sqrt(252)
    return d, out


def opt_rows(day, name):
    df = day_file(day)
    if df is None:
        return None
    return df[df["symbol"] == name]


def run(job):
    name, lot = job
    try:
        d, sig = signals(name, lot)
    except Exception as e:
        print("skip", name, e); return []
    if d is None or not sig:
        return []
    days = d["day"].values
    rows = []
    busy = {}
    for st, c_i, side, stop, tr in sig:
        k = c_i + 1                                        # entry day (option bought at its open)
        if k >= len(d) - 1 or k <= busy.get(st, -1) or days[k] < np.datetime64("2022-07-15"):
            continue
        dk = pd.Timestamp(days[k])
        fe = float(d["open"].iat[k])                       # futures entry (same timing)
        R = side * (fe - stop)
        if not R > 0 or R / fe > 0.08:
            continue
        tgt = fe + side * tr * R
        # futures exit on daily closes -> next open
        j, why = None, "time"
        for q in range(k, min(k + MAXD, len(d) - 1)):
            if d["switch"].iat[q + 1] if q + 1 < len(d) else False:
                j, why = q, "roll"; break
            cl = d["close"].iat[q]
            if side * (cl - stop) <= 0:
                j, why = q + 1, "stop"; break
            if side * (cl - tgt) >= 0:
                j, why = q + 1, "target"; break
        if j is None:
            j = min(k + MAXD - 1, len(d) - 1)
        busy[st] = j
        fx = float(d["open"].iat[j]) if why in ("stop", "target") else float(d["close"].iat[j])
        fut_rs = (side * (fx - fe)) * lot - fut_cost_rs(fe, lot, dk)
        base = dict(setup=st, name=name, side="BUY" if side > 0 else "SELL", entry_day=dk, exit_day=pd.Timestamp(days[j]),
                    exit_why=why, fut_R=round(fut_rs / (R * lot), 3), fut_rs=round(fut_rs), lot=lot)
        # option on the entry day
        typ = "CE" if side > 0 else "PE"
        ok_ = opt_rows(dk, name)
        prev = opt_rows(pd.Timestamp(days[k - 1]), name)
        if ok_ is None or ok_.empty or prev is None:
            rows.append(dict(base, opt="no option data")); continue
        ch = ok_[(ok_["kind"] == typ) & (ok_["expiry"] >= dk + pd.Timedelta(days=15))]
        if ch.empty:
            rows.append(dict(base, opt="no expiry ≥ 15 days")); continue
        ch = ch[ch["expiry"] == ch["expiry"].min()]
        ks = np.sort(ch["strike"].unique())
        atm = ks[np.abs(ks - fe).argmin()]
        ia = int(np.where(ks == atm)[0][0])
        pick = {"ATM": atm}
        itm_i = ia - 1 if typ == "CE" else ia + 1
        otm_i = ia + 1 if typ == "CE" else ia - 1
        if 0 <= itm_i < len(ks):
            pick["ITM"] = ks[itm_i]
        if 0 <= otm_i < len(ks):
            pick["OTM"] = ks[otm_i]
        hv = d["hv20"].iat[k - 1]
        atr_d = d["atr"].iat[k - 1]
        pclose = float(d["close"].iat[k - 1])
        for lab, K in pick.items():
            r0 = ch[ch["strike"] == K].iloc[0]
            if not (r0["contracts"] > 0 and r0["open"] > 0):
                rows.append(dict(base, opt=lab, status="not traded at entry")); continue
            e_opt = float(r0["open"])
            exp = r0["expiry"]
            # IV from the previous day's option settle/close and futures close (known before the entry)
            pr = prev[(prev["kind"] == typ) & (prev["strike"] == K) & (prev["expiry"] == exp)]
            iv = None
            if len(pr):
                pv = float(pr["close"].iloc[0]) if pr["contracts"].iloc[0] > 0 else float(pr["settle"].iloc[0])
                T0 = max((exp - pd.Timestamp(days[k - 1])).days, 1) / 365
                iv = G.implied_vol(pv, pclose, K, T0, 0.065, typ)
            T = max((exp - dk).days, 1) / 365
            g_nm = None
            if iv:
                p_now = G.price(fe, K, T, iv, 0.065, typ)
                p_mv = G.price(fe + side * atr_d, K, max(T - 3 / 365, 1 / 365), iv, 0.065, typ)
                g_nm = p_mv / p_now - 1 if p_now > 0 else None
            # option path: exit at the futures exit day (open for stop/target, close for time/roll); time stop variant
            def px_on(day_idx, field):
                rr = opt_rows(pd.Timestamp(days[day_idx]), name)
                if rr is None:
                    return None, None
                x = rr[(rr["kind"] == typ) & (rr["strike"] == K) & (rr["expiry"] == exp)]
                if x.empty:
                    return None, None
                x = x.iloc[0]
                if field == "open" and x["contracts"] > 0 and x["open"] > 0:
                    return float(x["open"]), "open"
                if x["contracts"] > 0 and x["close"] > 0:
                    return float(x["close"]), "close"
                return float(x["settle"]), "settle"
            jj = j
            if exp <= pd.Timestamp(days[j]):                 # never past expiry
                jj = max([q for q in range(k, j + 1) if pd.Timestamp(days[q]) < exp] or [k])
            ox, basis = px_on(jj, "open" if (why in ("stop", "target") and jj == j) else "close")
            if ox is None:
                rows.append(dict(base, opt=lab, status="no exit price")); continue
            ret = (ox - e_opt) * lot - opt_cost_rs(e_opt, ox, lot, dk)
            # time stop: at day-2 close the option is not +10 % -> exit at day-3 open
            ts_ret = ret
            if k + 2 < jj:
                c2, _ = px_on(k + 1, "close")
                if c2 is not None and c2 < e_opt * 1.10:
                    o3, _ = px_on(k + 2, "open")
                    if o3 is not None:
                        ts_ret = (o3 - e_opt) * lot - opt_cost_rs(e_opt, o3, lot, dk)
            rows.append(dict(base, opt=lab, status="ok", K=K, expiry=exp, dte=(exp - dk).days, opt_entry=e_opt, opt_exit=ox,
                             exit_basis=basis, prem_rs=round(e_opt * lot), opt_ret_pct=round((ox / e_opt - 1) * 100, 1),
                             opt_rs=round(ret), opt_rs_timestop=round(ts_ret), iv=iv, hv=hv,
                             iv_ok=(iv is not None and hv and iv <= 1.5 * hv), nm_gain=g_nm,
                             nm_ok=(g_nm is not None and g_nm >= 0.30)))
    return rows


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    jobs = [(n, int(l)) for n, l in zip(man["name"], man["lot"])]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run, jobs, chunksize=1) for r in x]
    T = pd.DataFrame(rows)
    T["split"] = np.where(T["entry_day"] < "2024-07-01", "train", np.where(T["entry_day"] < "2025-07-01", "valid", "test"))
    T.to_csv(OUT / "obuy_real_trades.csv.gz", index=False)
    print(len(T), T.groupby(["setup", "opt"]).size().to_dict())


if __name__ == "__main__":
    main()

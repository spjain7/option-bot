"""CHAN-001 (29-Oct-2026, owner: "scan and backtest for last 2 months" – the Telegram channel's apparent pattern).
Pattern read from the channel's 29-Oct calls (ADANIPORTS CE, HEROMOTOCO PE, PHOENIX CE): morning break of the previous day's
high (CE) / failed gap-up back below it or break of the previous day's low (PE), volume ~2×, ATM option of the month.

Data: Angel 15-min futures + OI, 40 stocks, 20-Aug → 22-Oct-2026 (≈ 44 sessions). Option prices: real NSE daily bhavcopy is used
only for the IV (previous day's ATM close -> Black-76 IV); the intraday option value is then MODELLED from the futures path
(no intraday option prices exist) – so option figures are estimates, futures figures are exact.

Signals, first one per stock per day, 15-min bar closes 09:30–11:30 (entry next bar open):
  PDH_CE   close above the previous day's high          PDL_PE   close below the previous day's low
  GAPFAIL_PE  day opened above the previous day's high, close back below it    GAPFAIL_CE  mirror (opened below PDL, back above)
  HI5_CE / LO5_PE   close beyond the 5-day high / low
Filters: same-slot relative volume ≥ 1 / 1.5 / 2 / 3 · OI since the open: any / supports (CE: long buildup or short covering =
price up; strict: long buildup = price up & OI up; PE: short buildup = price down & OI up) · NIFTY futures up (CE) / down (PE) since the open.
Exits: S1 stop beyond the signal bar (±0.1 ATR15), target 1R · S2 same stop, 2R · EOD hold to 15:15 (no target) ·
"made high" = best option price before 15:15 (what the channel posts; NOT a tradable exit).
Costs: futures 2× (as live), option 2 % of premium round trip (spread + charges).
python research/program/chan_pattern.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from greeks import price, implied_vol  # noqa: E402
from research.search.stock_check import cost_frac  # noqa: E402
from crude import indicators as I  # noqa: E402

D15 = ROOT / "research/data/obuy"
OPT = ROOT / "research/data/nse_opt/days"
OUT = ROOT / "research/program/results"
INDEX = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}


def opt_day(day):
    p = OPT / f"{day:%Y%m%d}.csv"
    return pd.read_csv(p, parse_dates=["expiry"]) if p.exists() else None


def atm_iv(name, prev_day, F, typ, cache):
    """IV of the ATM option (nearest expiry with ≥ 5 days left) from the previous day's real close."""
    k = (name, prev_day, typ)
    if k in cache:
        return cache[k]
    od = cache.setdefault(("day", prev_day), opt_day(prev_day))
    out = None
    if od is not None:
        o = od[(od["symbol"] == name) & (od["kind"] == typ)]
        o = o[o["expiry"] >= prev_day + pd.Timedelta(days=5)]
        if len(o):
            e = o["expiry"].min(); o = o[o["expiry"] == e]
            fut = od[(od["symbol"] == name) & (od["kind"] == "FUT")]
            Fp = float(fut.sort_values("expiry")["close"].iloc[0]) if len(fut) else F
            r = o.iloc[(o["strike"] - Fp).abs().argsort().iloc[0]]
            T = max((e - prev_day).days, 1) / 365
            iv = implied_vol(float(r["close"]), Fp, float(r["strike"]), T, 0.065, typ) if r["close"] > 0 else None
            step = np.median(np.diff(np.sort(o["strike"].unique()))) if o["strike"].nunique() > 2 else 0
            out = (iv, e, step) if iv else None
    cache[k] = out
    return out


def run_stock(path, nifty):
    name = path.stem[4:]
    df = pd.read_csv(path, parse_dates=["time"]).sort_values("time").drop_duplicates("time")
    df = df[(df["time"].dt.strftime("%H:%M") >= "09:15") & (df["time"].dt.strftime("%H:%M") < "15:30")].reset_index(drop=True)
    if len(df) < 300:
        return []
    df["day"] = df["time"].dt.normalize(); df["hm"] = df["time"].dt.strftime("%H:%M")
    d = df.groupby("day").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
    d["pdh"], d["pdl"], d["pc"] = d["h"].shift(1), d["l"].shift(1), d["c"].shift(1)
    d["h5"], d["l5"] = d["h"].shift(1).rolling(5).max(), d["l"].shift(1).rolling(5).min()
    for c_ in ("o", "pdh", "pdl", "h5", "l5"):
        df[c_] = df["day"].map(d[c_])
    df["slot"] = df["hm"]
    df["relvol"] = df["volume"] / df.groupby("slot")["volume"].transform(lambda v: v.shift(1).rolling(10, min_periods=5).mean())
    df["atr"] = I.atr(df, 14)
    df["oi0"] = df.groupby("day")["oi"].transform("first")
    n_map = nifty.set_index("time")["close"]; n_open = nifty.groupby(nifty["time"].dt.normalize())["open"].first()
    days = list(d.index)
    rows, cache = [], {}
    for day, g in df.groupby("day"):
        if pd.isna(g["pdh"].iat[0]) or days.index(day) < 6:
            continue
        prev_day = days[days.index(day) - 1]
        done = set()
        gi = g.index
        for i in gi:
            hm = df.at[i, "hm"]
            if not ("09:30" <= hm <= "11:15") or i + 1 > gi[-1]:
                continue
            c, o_, pdh, pdl = df.at[i, "close"], df.at[i, "o"], df.at[i, "pdh"], df.at[i, "pdl"]
            pc_ = df.at[i - 1, "close"] if i - 1 in gi else df.at[i, "open"]
            sig = []
            if c > pdh and not pc_ > pdh:
                sig.append(("PDH_CE", 1))
            if c < pdl and not pc_ < pdl:
                sig.append(("PDL_PE", -1))
            if o_ > pdh and c < pdh and not pc_ < pdh:
                sig.append(("GAPFAIL_PE", -1))
            if o_ < pdl and c > pdl and not pc_ > pdl:
                sig.append(("GAPFAIL_CE", 1))
            if c > df.at[i, "h5"] and not pc_ > df.at[i, "h5"]:
                sig.append(("HI5_CE", 1))
            if c < df.at[i, "l5"] and not pc_ < df.at[i, "l5"]:
                sig.append(("LO5_PE", -1))
            for typ_s, s in sig:
                if typ_s in done:
                    continue
                done.add(typ_s)
                rows.extend(trade(df, gi, i, s, typ_s, name, day, prev_day, n_map, n_open, cache))
    return rows


def trade(df, gi, i, s, typ_s, name, day, prev_day, n_map, n_open, cache):
    a = df.at[i, "atr"]
    if not a > 0:
        return []
    e0 = df.at[i + 1, "open"]
    st = (df.at[i, "low"] - 0.1 * a) if s > 0 else (df.at[i, "high"] + 0.1 * a)
    R = s * (e0 - st)
    if not R > 0.1 * a:
        return []
    end = gi[-1]
    while df.at[end, "hm"] > "15:15" and end > i + 1:
        end -= 1
    j_idx = list(range(i + 1, end + 1))
    hi, lo, op, cl = (df.loc[j_idx, x].values for x in ("high", "low", "open", "close"))
    tms = df.loc[j_idx, "time"].values

    def run(tgt_r):
        tp = e0 + s * tgt_r * R if tgt_r else None
        for k in range(len(j_idx)):
            if k > 0 and s * (op[k] - st) <= 0:
                return op[k], k, "stop (gap)"
            if (lo[k] <= st) if s > 0 else (hi[k] >= st):
                return st, k, "stop"
            if tp is not None and ((hi[k] >= tp) if s > 0 else (lo[k] <= tp)):
                return tp, k, "target"
        return cl[-1], len(j_idx) - 1, "15:15"
    oi_ch = df.at[i, "oi"] / df.at[i, "oi0"] - 1 if df.at[i, "oi0"] > 0 else np.nan
    px_ch = df.at[i, "close"] / df.at[i, "o"] - 1
    t = df.at[i, "time"]
    try:
        nf = n_map.loc[:t].iloc[-1] / n_open.loc[t.normalize()] - 1
    except Exception:
        nf = np.nan
    typ = "CE" if s > 0 else "PE"
    ivx = atm_iv(name, prev_day, e0, typ, cache)
    cf = cost_frac(e0, 500) * 2
    out = []
    for ex, tr in (("S1", 1.0), ("S2", 2.0), ("EOD", None)):
        px, k, why = run(tr)
        r_fut = (s * (px - e0) - cf) / R
        opt_ret = mfe_opt = np.nan
        if ivx:
            iv, exp, step = ivx
            K = round(e0 / step) * step if step else e0
            T0 = max((exp - day).days, 1) / 365 - (pd.Timestamp(t) - day).total_seconds() / 86400 / 365
            p0 = price(e0, K, T0, iv, 0.065, typ)
            Tk = lambda kk: max(T0 - (pd.Timestamp(tms[kk]) - pd.Timestamp(t)).total_seconds() / 86400 / 365, 1 / 365)
            if p0 > 0:
                opt_ret = price(px, K, Tk(k), iv, 0.065, typ) / p0 - 1 - 0.02
                best = max(hi[:k + 1]) if s > 0 else min(lo[:k + 1]) if ex != "EOD" else (max(hi) if s > 0 else min(lo))
                if ex == "EOD":
                    best = max(hi) if s > 0 else min(lo)
                mfe_opt = price(best, K, T0, iv, 0.065, typ) / p0 - 1
        out.append(dict(name=name, day=day, time=t, type=typ_s, side=typ, relvol=df.at[i, "relvol"], oi_ch=oi_ch, px_ch=px_ch,
                        nifty=nf, exit=ex, why=why, r_fut=r_fut, opt_ret=opt_ret, made_high=mfe_opt))
    return out


def main():
    nifty = pd.read_csv(D15 / "fut_NIFTY.csv", parse_dates=["time"]).sort_values("time")
    rows = []
    for p in sorted(D15.glob("fut_*.csv")):
        if p.stem[4:] in INDEX:
            continue
        rows.extend(run_stock(p, nifty))
    T = pd.DataFrame(rows)
    T.to_csv(OUT / "chan_pattern_trades.csv.gz", index=False)
    s = np.where(T["side"] == "CE", 1, -1)
    T["oi_sup"] = np.where(s > 0, T["px_ch"] > 0, (T["px_ch"] < 0) & (T["oi_ch"] > 0))
    T["oi_strict"] = np.where(s > 0, (T["px_ch"] > 0) & (T["oi_ch"] > 0), (T["px_ch"] < 0) & (T["oi_ch"] > 0))
    T["mkt"] = np.where(s > 0, T["nifty"] > 0, T["nifty"] < 0)
    T["half"] = np.where(T["day"] < pd.Timestamp("2026-09-22"), "Aug20-Sep21", "Sep22-Oct22")
    print(f"signals: {T[T.exit == 'EOD'].shape[0]} on {T['day'].nunique()} days, {T['name'].nunique()} stocks")
    res = []
    for (ty, ex), G in T.groupby(["type", "exit"]):
        for vx in (0, 1.5, 2.0, 3.0):
            for oi in ("any", "oi_sup", "oi_strict"):
                for mk in ("any", "mkt"):
                    m = G["relvol"].fillna(0) >= vx
                    if oi != "any":
                        m &= G[oi]
                    if mk != "any":
                        m &= G["mkt"]
                    g = G[m]
                    if len(g) < 12:
                        continue
                    h1, h2 = g[g["half"] == "Aug20-Sep21"], g[g["half"] == "Sep22-Oct22"]
                    res.append(dict(type=ty, exit=ex, vol=vx, oi=oi, market=mk, n=len(g), win_fut=(g["r_fut"] > 0).mean() * 100,
                                    R_fut=g["r_fut"].mean(), R_h1=h1["r_fut"].mean(), R_h2=h2["r_fut"].mean(),
                                    opt_win=(g["opt_ret"] > 0).mean() * 100, opt_ret=g["opt_ret"].mean() * 100,
                                    opt_h1=h1["opt_ret"].mean() * 100, opt_h2=h2["opt_ret"].mean() * 100,
                                    made_high=g["made_high"].median() * 100))
    S = pd.DataFrame(res)
    S.to_csv(OUT / "chan_pattern_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    print("\nNo filter, per pattern (futures R after costs; option % modelled; 'made high' = median best option gain before exit/15:15):")
    print(S[(S.vol == 0) & (S.oi == "any") & (S.market == "any")].round(2).to_string(index=False))
    print("\nChannel-like: volume ≥ 2×, OI supports, market same way:")
    print(S[(S.vol == 2.0) & (S.oi == "oi_sup") & (S.market == "mkt")].round(2).to_string(index=False))
    print("\nBest 20 by futures R with both halves positive (n ≥ 15):")
    b = S[(S.n >= 15) & (S.R_h1 > 0) & (S.R_h2 > 0)].sort_values("R_fut", ascending=False)
    print(b.head(20).round(2).to_string(index=False))
    print(f"\ncombos tested {len(S)}, both halves positive {len(b)}")


if __name__ == "__main__":
    main()

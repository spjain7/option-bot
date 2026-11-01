"""DELTA-001 (1-Nov-2026, owner: "check how delta can help us for any trade and in these setups").
Two questions, real NSE option data (bhavcopy Jul-2022 → Oct-2026), live stock futures rules (3h SELL N=20 vol 1.5x 2ATR/2R,
4h SELL N=5 vol 2x 2ATR/2R; TOUCH-001 'CLOSE' trades):
 A. STRIKE BY DELTA – for each futures call, buy the put whose delta is nearest 0.25 / 0.40 / 0.50 / 0.60 / 0.75 / 0.90
    (nearest expiry ≥ 7 days, strike traded that day). Entry and exit priced with Black-76 at the futures entry/exit price using
    that strike's implied vol from the day's real close (captures delta, gamma, theta and day-level IV change); an exit after expiry
    uses the expiry day's real close. Cost: 2 % of premium round trip (stock-option spreads, doubled).
 B. DELTA AS A FILTER – net delta of the option OI (Σ delta × OI, calls + puts, near expiry) and its 1-day change, from the
    previous day's close (no look-ahead): do trades with the option chain leaning their way do better?
python research/program/delta.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, touch as TC  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from greeks import implied_vol, price, greeks  # noqa: E402

DAYS = ROOT / "research/data/nse_opt/days"
OUT = ROOT / "research/program/results"
TARGETS = (0.25, 0.40, 0.50, 0.60, 0.75, 0.90)
RATE, OPT_COST = 0.065, 0.02


def trades_one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return []
    rows = []
    for seg, f0, od, cost in fr:
        if seg != "STOCKS 1h":
            continue
        c_ = np.interp(np.arange(len(f0)), np.linspace(0, len(f0) - 1, len(cost)), cost)
        for n in (3, 4):
            for x in TC.run(f0, c_, "STOCKS", n, TC.RULES[("STOCKS", n)], vars_=("CLOSE",)):
                rows.append((job[1], job[2], n) + x[1:])
    return rows


def day_file(d):
    p = DAYS / f"{d:%Y%m%d}.csv"
    return pd.read_csv(p, parse_dates=["date", "expiry"]) if p.exists() else None


def _bs(F, K, T, sg, put):
    from scipy.stats import norm
    d1 = (np.log(F / K) + 0.5 * sg * sg * T) / (sg * np.sqrt(T)); d2 = d1 - sg * np.sqrt(T)
    df = np.exp(-RATE * T)
    call = df * (F * norm.cdf(d1) - K * norm.cdf(d2))
    putp = df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
    return np.where(put, putp, call), d1


def chain_day(p):
    """per symbol: near-expiry (≥ 7 days) options within ±25 % of the future, vectorised IV + delta; NET = Σ delta·OI / Σ OI."""
    from scipy.stats import norm
    d = pd.read_csv(p, parse_dates=["date", "expiry"])
    day = d["date"].iat[0]
    fut = d[d["kind"] == "FUT"].sort_values("expiry").groupby("symbol").head(1).set_index("symbol")["close"]
    o = d[(d["kind"] != "FUT") & (d["expiry"] >= day + pd.Timedelta(days=7)) & (d["close"] > 0)].copy()
    o = o[o["expiry"] == o.groupby("symbol")["expiry"].transform("min")]
    o = o[o["symbol"].isin(fut.index)]
    o["F"] = o["symbol"].map(fut).astype(float)
    o = o[(o["strike"] - o["F"]).abs() <= 0.25 * o["F"]]
    if o.empty:
        return []
    F, K, P = o["F"].values, o["strike"].values.astype(float), o["close"].values.astype(float)
    T = np.maximum((o["expiry"] - day).dt.days.values, 1) / 365
    put = (o["kind"] == "PE").values
    lo, hi = np.full(len(o), 0.005), np.full(len(o), 4.0)
    for _ in range(50):
        mid = (lo + hi) / 2
        pr, _d = _bs(F, K, T, mid, put)
        hi = np.where(pr > P, mid, hi); lo = np.where(pr > P, lo, mid)
    iv = (lo + hi) / 2
    intr = np.maximum(np.where(put, K - F, F - K), 0) * np.exp(-RATE * T)
    ok = (P > intr + 1e-6) & (iv > 0.03) & (iv < 3)
    _, d1 = _bs(F, K, T, iv, put)
    de = np.where(put, norm.cdf(d1) - 1, norm.cdf(d1))
    o["iv"], o["delta"], o["T"] = np.where(ok, iv, np.nan), np.where(ok, de, np.nan), T
    o = o[ok]
    res = [(day, r.symbol, r.kind, r.expiry, float(r.strike), float(r.close), int(r.contracts), r.iv, r.delta, r.F, r.T)
           for r in o.itertuples()]
    w = o.assign(dw=o["delta"] * o["oi"]).groupby("symbol").agg(dw=("dw", "sum"), oi=("oi", "sum"), F=("F", "first"),
                                                                 expiry=("expiry", "first"))
    res += [(day, s, "NET", r.expiry, np.nan, r.dw / r.oi if r.oi else np.nan, 0, np.nan, np.nan, r.F, np.nan) for s, r in w.iterrows()]
    return res


def chain():
    cache = OUT / "delta_chain.csv.gz"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["date", "expiry"])
    with Pool(3) as p:
        rows = [r for x in p.imap(chain_day, sorted(DAYS.glob("*.csv")), chunksize=8) for r in x]
    C = pd.DataFrame(rows, columns=["date", "symbol", "kind", "expiry", "strike", "close", "contracts", "iv", "delta", "F", "T"])
    C.to_csv(cache, index=False)
    return C


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(trades_one, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["name", "lot", "hours", "time", "r2", "exit", "slip", "t_in", "t_out", "e0", "px", "R"])
    for c in ("time", "t_in", "t_out"):
        T[c] = pd.to_datetime(T[c], format="mixed")
    T["fut_rs"] = T["r2"] * T["R"] * T["lot"]
    print(f"futures trades {len(T):,}")
    C = chain()
    PE = C[C["kind"] == "PE"]
    pe_by = {k: g for k, g in PE.groupby(["date", "symbol"])}
    net = C[C["kind"] == "NET"].set_index(["symbol", "date"])["close"].sort_index()
    raw = {}

    def real_close(day, sym, K, exp):
        if day not in raw:
            raw[day] = day_file(day)
        x = raw[day]
        if x is None:
            return None
        y = x[(x["symbol"] == sym) & (x["kind"] == "PE") & (x["expiry"] == exp) & (x["strike"] == K)]
        return float(y["close"].iat[0]) if len(y) else None

    days = sorted(C["date"].unique())
    out = []
    for t in T.itertuples():
        d_in = t.t_in.normalize()
        g = pe_by.get((d_in, t.name))
        if g is None or g.empty:
            continue
        g = g[g["contracts"] > 0]
        exits = [d for d in days if d >= t.t_out.normalize()]
        if g.empty or not exits:
            continue
        d_out = exits[0]
        for tg in TARGETS:
            r = g.iloc[(g["delta"].abs() - tg).abs().argsort().iloc[0]]
            if abs(abs(r["delta"]) - tg) > 0.1:
                continue
            Tin = max((r["expiry"] - t.t_in).total_seconds() / 86400 / 365, 1 / 365 / 6.25)
            p_in = price(t.e0, r["strike"], Tin, r["iv"], RATE, "PE")
            if t.t_out.normalize() >= r["expiry"]:
                p_out = real_close(r["expiry"], t.name, r["strike"], r["expiry"])
                if p_out is None:
                    p_out = max(r["strike"] - t.px, 0.0)
            else:
                ge = pe_by.get((d_out, t.name))
                iv_out = r["iv"]
                if ge is not None:
                    m = ge[(ge["strike"] == r["strike"]) & (ge["expiry"] == r["expiry"])]
                    if len(m):
                        iv_out = m["iv"].iat[0]
                Tout = max((r["expiry"] - t.t_out).total_seconds() / 86400 / 365, 1 / 365 / 6.25)
                p_out = price(t.px, r["strike"], Tout, iv_out, RATE, "PE")
            if not p_in > 0.5:
                continue
            pnl = p_out - p_in - OPT_COST * p_in
            out.append(dict(name=t.name, hours=t.hours, time=t.time, target=tg, delta=abs(r["delta"]), prem=p_in, ret=pnl / p_in,
                            opt_rs=pnl * t.lot, fut_rs=t.fut_rs, prem_rs=p_in * t.lot, fut_risk=t.R * t.lot, r2=t.r2))
    O = pd.DataFrame(out)
    O["split"] = np.where(O.time < T1, "train", np.where(O.time < T2, "valid", "test"))
    O.to_csv(OUT / "delta_trades.csv.gz", index=False)
    pd.set_option("display.width", 220)
    print("\nA. WHICH DELTA TO BUY (put, for the live stock SELL calls) – per trade averages, ₹ per lot")
    A = O.groupby(["hours", "target"]).agg(n=("ret", "size"), win=("opt_rs", lambda s: (s > 0).mean()), ret_on_prem=("ret", "mean"),
                                         opt_rs=("opt_rs", "mean"), fut_rs=("fut_rs", "mean"), premium_rs=("prem_rs", "mean"),
                                         fut_risk_rs=("fut_risk", "mean"))
    A = A.join(O.pivot_table(index=["hours", "target"], columns="split", values="opt_rs", aggfunc="mean")[["train", "valid", "test"]])
    A["opt_per_rs_risked"] = A["opt_rs"] / A["premium_rs"]
    A["fut_per_rs_risked"] = A["fut_rs"] / A["fut_risk_rs"]
    print(A.round(3).to_string())

    # B. delta filter
    print("\nB. OPTION-CHAIN NET DELTA (previous close) AS A FILTER on the futures SELL trades (R per trade, 2x costs)")
    T["d0"] = T["t_in"].dt.normalize()
    pos = {}
    for sym, s in net.groupby(level=0):
        s = s.droplevel(0)
        pos[sym] = s
    f1, f2 = [], []
    for t in T.itertuples():
        s = pos.get(t.name)
        if s is None:
            f1.append(np.nan); f2.append(np.nan); continue
        prev = s[s.index < t.d0]
        f1.append(prev.iat[-1] if len(prev) else np.nan)
        f2.append(prev.iat[-1] - prev.iat[-2] if len(prev) >= 2 else np.nan)
    T["net"], T["dnet"] = f1, f2
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    for col in ("net", "dnet"):
        x = T.dropna(subset=[col]).copy()
        x["bucket"] = pd.qcut(x[col], 3, labels=["low", "mid", "high"])
        B = x.groupby(["hours", "bucket"], observed=True).agg(n=("r2", "size"), R=("r2", "mean"), win=("r2", lambda s: (s > 0).mean()))
        B = B.join(x.pivot_table(index=["hours", "bucket"], columns="split", values="r2", aggfunc="mean", observed=True)[["train", "valid", "test"]])
        print(f"\n{col} ({'net delta of OI, −1…+1' if col == 'net' else '1-day change of net delta'}):")
        print(B.round(3).to_string())
    T.to_csv(OUT / "delta_futtrades.csv.gz", index=False)


if __name__ == "__main__":
    main()

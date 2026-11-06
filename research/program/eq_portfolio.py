"""EQ-PORT-001 – daily mark-to-market portfolio simulation of the positional cash BUY strategy (EQ-TREND-001).

Capital ₹1 (normalised). `slots` equal positions: each new position gets 1/slots of current equity (cash permitting).
Entry at the signal's next open, exit at the simulated exit (stop / EMA50 close / max hold) – the trade list of
eq_trend.py, so execution prices are identical. Delivery costs (0.393 % round trip) charged half at entry, half at exit.
Daily equity = cash + Σ shares × adjusted close (open positions marked every session) -> drawdown includes open losses.
Selection when more signals than free slots: 'rs' (highest 63-day RS first) or 'random' (seeded; ranking value check).
Max 2 positions per sector when the sector is known; no stock twice. Benchmarks: equal-weight liquid universe (monthly)
and momentum baseline (eq_momentum.py results).
python research/program/eq_portfolio.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_bhav as EB, eq_data as ED  # noqa: E402

OUT = ROOT / "research/program/results"
CF = ED.cost_frac("delivery")


def close_panel():
    A = EB.adjusted_cached()
    C, O = {}, {}
    for k, d in A.items():
        s = d.symbol.iat[-1]
        if s in C:                                    # keep the longer history for a reused symbol
            if len(d) <= C[s].notna().sum():
                continue
        C[s] = pd.Series(d.close.values, d.time.values); O[s] = pd.Series(d.open.values, d.time.values)
    return pd.concat(C, axis=1).sort_index().ffill(limit=10), pd.concat(O, axis=1).sort_index()


def simulate(T, C, O, slots=10, order="rs", sector=None, seed=0, sector_cap=2):
    rng = np.random.default_rng(seed)
    T = T.copy()
    T["key"] = rng.random(len(T)) if order == "random" else -T.rs
    by_day = {d: g.sort_values("key") for d, g in T.groupby("time")}
    days = C.index[(C.index >= T.time.min())]
    cash, pos, eq_curve, expo, taken = 1.0, {}, [], [], []
    sig_days = sorted(by_day)
    pending = {}                                          # entry day -> list of trades (signal day + 1 session)
    nxt = {d: days[i + 1] for i, d in enumerate(days[:-1])}
    for d in sig_days:
        if d in nxt:
            pending.setdefault(nxt[d], []).append(by_day[d])
    for day in days:
        # exits first (exit at the open of exit day for EMA50 rule / stop price approximated by the trade's net return)
        for s in [s for s, p in pos.items() if p["exit_time"] <= day]:
            p = pos.pop(s)
            cash += p["alloc"] * (1 + p["ret"] + CF / 2)       # trade ret is net of the full round trip; entry half paid at entry
            taken.append(p)
        # entries
        for g in pending.get(day, []):
            for _, r in g.iterrows():
                if len(pos) >= slots or r.sym in pos:
                    continue
                sc = (sector or {}).get(r.sym)
                if sc and sum(1 for p in pos.values() if p.get("sector") == sc) >= sector_cap:
                    continue
                equity = cash + sum(p["alloc"] * C.at[day, p["sym"]] / p["px0"] if p["sym"] in C.columns and C.at[day, p["sym"]] == C.at[day, p["sym"]] else p["alloc"] for p in pos.values())
                alloc = min(equity / slots, cash)
                if alloc <= 0:
                    break
                px0 = O.at[day, r.sym] if r.sym in O.columns else np.nan
                if not px0 == px0:
                    continue
                cash -= alloc
                pos[r.sym] = dict(sym=r.sym, alloc=alloc * (1 - CF / 2), px0=px0, exit_time=r.exit_time, ret=r.ret, R=r.R,
                                  time=day, sector=sc)
        mv = 0.0
        for p in pos.values():
            c = C.at[day, p["sym"]] if p["sym"] in C.columns else np.nan
            mv += p["alloc"] * (c / p["px0"]) if c == c else p["alloc"]
        eq_curve.append((day, cash + mv)); expo.append(mv / (cash + mv))
    E = pd.Series(dict(eq_curve)); X = pd.Series(expo, index=E.index)
    return E, X, pd.DataFrame(taken)


def perf(E, X, lab, taken=None):
    yrs = (E.index[-1] - E.index[0]).days / 365.25
    r = E.pct_change().dropna()
    m = E.resample("ME").last().pct_change().dropna()
    out = dict(set=lab, CAGR=round(100 * ((E.iloc[-1] / E.iloc[0]) ** (1 / yrs) - 1), 1),
               maxDD=round(100 * (E / E.cummax() - 1).min(), 1), sharpe=round(r.mean() / r.std() * np.sqrt(250), 2),
               months_pos=round(100 * (m > 0).mean(), 0), exposure=round(100 * X.mean(), 0))
    if taken is not None and len(taken):
        out.update(trades=len(taken), win=round(100 * (taken.ret > 0).mean(), 1), avg_ret=round(100 * taken.ret.mean(), 2))
    return out


def main():
    T = pd.read_csv(OUT / "eqtrend_trades.csv.gz", parse_dates=["time", "exit_time"])
    C, O = close_panel()
    uf = ED.EQ / "universe.csv"
    sector = dict(zip(*pd.read_csv(uf)[["symbol", "industry"]].fillna("").values.T)) if uf.exists() else {}
    rows = []
    for N in (126, 250):
        g = T[(T.N == N) & (T.exit == "EMA50") & (T.rs_filter == 0) & (T.mkt_filter == 0)]
        for slots in (5, 10):
            for order in ("rs", "random"):
                E, X, tk = simulate(g, C, O, slots, order, sector)
                for lab, a, b in (("2006-15", "2005", "2016"), ("2016-26 OOS", "2016", "2030")):
                    e = E[(E.index >= a) & (E.index < b)]; x = X[(X.index >= a) & (X.index < b)]
                    t_ = tk[(tk.time >= a) & (tk.time < b)] if len(tk) else tk
                    rows.append(dict(N=N, slots=slots, order=order, period=lab, **perf(e / e.iloc[0], x, "", t_)))
                if N == 126 and slots == 5 and order == "rs":
                    E.to_csv(OUT / "eqport_equity_N126_s5.csv"); tk.to_csv(OUT / "eqport_trades_N126_s5.csv", index=False)
                    yr = E.resample("YE").last().pct_change()
                    print("N126 · 5 slots · RS order – calendar-year returns:", {d.year: round(100 * v, 1) for d, v in yr.dropna().items()})
    R = pd.DataFrame(rows).drop(columns="set")
    R.to_csv(OUT / "eqport_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()

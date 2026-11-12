"""Cycle 2 · 1 – RSI CONTINUATION BUY: which filters add genuine out-of-sample edge, per market and timeframe.
Base events (fixed): B1 = RSI(14) crosses to >= 75; B2 = S10 (RSI >= 75 + ADX >= 25 + close > EMA50 + 20-bar breakout).
Entry next open, structure stop (5-bar low - 0.1 ATR, 0.5–3 ATR), target 2R (3R reported as robustness), max hold per
timeframe, costs as in research/rsidiv. Filters (one at a time, pre-registered): adx25 · adx35 · adx_rising · ema_stack ·
rvol1.5 · rvol2 · breakout20 · close_top_quarter · vwap · htf_up · confirm (entry after a close above the signal high)
+ market context: stocks / cash: mkt_up (EW market > EMA200) · breadth50 (> 50 % of eligible stocks above EMA50) ·
sector_up (sector index > EMA50) · sector_rs_top (sector 63-day return in the top half) · rs_top30 (stock 63-day RS top
30 %); index: mkt_up · breadth50; MCX: mcx_breadth (>= 4 of 7 commodities above their daily EMA50) · group_up (metals /
energy equal-weight index above its EMA50). Intraday bars use the PREVIOUS day's daily values.
python -m research.cycle2.cont_buy [market ...]  ->  results/cont_buy_filters.csv"""
import sys
import time
import numpy as np
import pandas as pd

from research.cycle2 import common as C
from research.rsidiv import engine as E
from research.rsirev import run as RR

TFS = {"mcx": (("1h", 45), ("3h", 40), ("1d", 15)), "stockfut": (("1d", 15), ("1w", 10)), "index": (("1d", 15), ("1h", 21)), "cash": (("1d", 15), ("1w", 10))}
MKT = {"mcx": "MCX", "stockfut": "NSE_STOCK_FUT", "index": "NSE_INDEX_FUT", "cash": "NSE_CASH"}


def stock_ctx(name, times, tf, cs):
    t = pd.DatetimeIndex(pd.to_datetime(times))
    reg = cs["reg"] if tf != "1w" else cs["reg"].resample("W-FRI").last()
    al = lambda s: s.reindex(t, method="ffill").fillna(False).astype(bool).values
    out = dict(mkt_up=al(reg["mkt_up"]), breadth50=al(reg["breadth"] > 0.5))
    sec = cs["sector_of"].get(name, "")
    if sec and sec in cs["s_up"]:
        su, sr = cs["s_up"][sec], cs["s_rs"][sec] >= 0.5
        if tf == "1w":
            su, sr = su.resample("W-FRI").last(), sr.resample("W-FRI").last()
        out.update(sector_up=al(su), sector_rs_top=al(sr))
    else:
        out.update(sector_up=np.zeros(len(t), bool), sector_rs_top=np.zeros(len(t), bool))
    rs = cs["rs"].get(name)
    if rs is not None:
        rs = rs >= 0.7
        out["rs_top30"] = al(rs.resample("W-FRI").last() if tf == "1w" else rs)
    else:
        out["rs_top30"] = np.zeros(len(t), bool)
    return out


def index_ctx(times, tf, cs):
    t = pd.to_datetime(pd.Series(times))
    reg = cs["reg"]
    if tf == "1h":                                            # previous day's close values
        key = t.dt.normalize() - pd.Timedelta(days=1)
        al = lambda s: s.reindex(pd.DatetimeIndex(key), method="ffill").fillna(False).astype(bool).values
    else:
        al = lambda s: s.reindex(pd.DatetimeIndex(t), method="ffill").fillna(False).astype(bool).values
    return dict(mkt_up=al(reg["mkt_up"]), breadth50=al(reg["breadth"] > 0.5))


def mcx_ctx(frames, tf):
    daily = {}
    for f in frames:
        b = f["b"]; t = pd.to_datetime(b["time"]); d = pd.Series(b["close"].astype(float).values, index=t).groupby(t.dt.normalize().values).last()
        daily[f["name"]] = d
    D = pd.DataFrame(daily).sort_index().ffill()
    above = (D > D.ewm(span=50, adjust=False).mean()).sum(axis=1) >= 4
    grp = {}
    for g, names in (("metals", [n for n in D if n in C.METALS]), ("energy", [n for n in D if n not in C.METALS])):
        ix = D[names].pct_change(fill_method=None).mean(axis=1).fillna(0).add(1).cumprod(); grp[g] = ix > ix.ewm(span=50, adjust=False).mean()
    out = []
    for f in frames:
        t = pd.to_datetime(f["b"]["time"]).dt.normalize()
        key = t - pd.Timedelta(days=1) if tf != "1d" else t
        al = lambda s: s.reindex(pd.DatetimeIndex(key), method="ffill").fillna(False).astype(bool).values
        if tf != "1d":
            al = (lambda s: s.shift(1).reindex(pd.DatetimeIndex(t), method="ffill").fillna(False).astype(bool).values)
        g = "metals" if f["name"] in C.METALS else "energy"
        out.append(dict(mcx_breadth=al(above), group_up=al(grp[g])))
    return out


def cash_frames(tf, cs):
    from research.cashq import data as D
    W = cs["W"] if tf == "1d" else D.weekly(cs["W"])
    idx = W["close"].index; out = []
    for g, k in enumerate(W["close"].columns):
        cl = W["close"][k]; ok = cl.notna().values
        if ok.sum() < (60 if tf == "1w" else 300) or not W["elig"][k].fillna(False).astype(bool).any():
            continue
        b = pd.DataFrame(dict(time=idx[ok], **{f: W[f][k].values[ok] for f in ("open", "high", "low", "close", "volume")}))
        for col in ("open", "high", "low"):
            b[col] = b[col].where(b[col] > 0).fillna(b["close"])
        out.append(dict(b=b, live=W["elig"][k].fillna(False).astype(bool).values[ok], costf=np.full(len(b), 0.00393),
                        expid=np.zeros(len(b), np.int64), grp=g, name=str(W["symbol"][k])))
    return out


def run_market(m):
    rows, t0 = [], time.time()
    cs = C.cash_context() if m in ("stockfut", "cash", "index") else None
    for tf, hold in TFS[m]:
        frames = cash_frames(tf, cs) if m == "cash" else getattr(RR, m)(tf)
        ctxs = mcx_ctx(frames, tf) if m == "mcx" else None
        cuts = RR.MARKETS[m][2].get(tf, RR.MARKETS[m][2].get("*"))
        pool = E.Pool(); fkeys = None
        for i, f in enumerate(frames):
            b = f["b"].reset_index(drop=True)
            ev, risk, _ = C.base_events(b)
            ctx = ctxs[i] if m == "mcx" else (index_ctx(b["time"].values, tf, cs) if m == "index" else stock_ctx(f["name"], b["time"].values, tf, cs))
            F = C.filters(b, tf, ctx)
            live = np.asarray(f["live"], bool)
            S = {}
            for bn, e in ev.items():
                e = e & live
                S[(bn, "next_open", "all", 1)] = e
                for fn, fm in F.items():
                    S[(bn + "+" + fn, "next_open", "all", 1)] = e & fm
                S[(bn + "+confirm", "next_open", "all", 1)] = C.confirm_of(e, b) & live
            fkeys = list(F) + ["confirm"]
            pool.add(b, S, risk["structure"], f["grp"], f["costf"], f["expid"], f["name"])
        pool.freeze()
        for bn in ("B1", "B2"):
            for R in (2.0, 3.0):
                r, Tb = C.test_filters(pool, (bn, "next_open", "all", 1), fkeys, cuts, hold, R, dict(market=MKT[m], tf=tf, base=bn, target_R=R))
                pb = C.per_period(Tb, cuts) if len(Tb) else {}
                rows += r
                print(f"{m} {tf} {bn} {R}R base n={len(Tb)} " + " ".join(f"{p}={v[1]:+.3f}({v[0]})" for p, v in pb.items()), flush=True)
        B = E.baselines(pool, cuts, hold, tf, MKT[m], sides=(1,))
        for rr in B.to_dict("records"):
            rows.append(dict(market=MKT[m], tf=tf, base="every_10th_bar", target_R=rr["target_R"], filter="(benchmark)", n=rr["all_n"],
                             **{f"{p}_R": rr[f"{p}_R"] for p, _ in cuts}, **{f"{p}_n": rr[f"{p}_n"] for p, _ in cuts}))
        del pool, frames
        print(f"{m} {tf} done {time.time() - t0:.0f}s", flush=True)
    return rows


def main(ms):
    rows = []
    for m in ms:
        rows += run_market(m)
        pd.DataFrame(rows).to_csv(C.OUT / f"cont_buy_filters_{'_'.join(ms)}.csv", index=False)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main(sys.argv[1:] or ["mcx", "index", "stockfut", "cash"])

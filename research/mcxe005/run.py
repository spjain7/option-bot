"""MCXE-005 experiment runner (pre-registered grid, PREREGISTRATION.md). For every frame of a market cell: all families x
sides x filters x exits are simulated with the MCXE-003 numba execution engine (next-bar entry, stop first, gap fills at
the open, one position at a time per (instrument, cell, family, side, filter, exit)), costs at 1x and 2x.
python research/mcxe005/run.py mcx_intraday|mcx_positional|eq_intraday|fut_intraday|fut_daily|eq_daily
-> results/trades_<cell>.parquet (one row per executed trade) and results/signals_<cell>.csv (signal counts per stream)."""
import sys
import time
import traceback
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import execution as EX, cost_model as CM  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402
from research.mcxe005 import frames as FR, signals as SG  # noqa: E402

OUT = ROOT / "research/mcxe005/results"
WARMUP = 60
EXITS = {"intraday": {"X1": (1.5, 2.0, 0.0), "X2": (1.0, 0.0, 0.0)},          # (stop ATR, target R, trail ATR)
         "positional": {"X1": (2.0, 3.0, 0.0), "X2": (1.5, 0.0, 2.5)},
         "overnight": {"X1": "next_open", "X2": "next_close"}}
WKEY = {"MCX": "MCX", "NSE_EQ_I": "NSE_EQ_INTRADAY", "NSE_EQ_D": "NSE_EQ", "NSE_FUT_I": "NSE_FUT_INTRADAY", "NSE_FUT_D": "NSE_FUT"}


def cost_frac_or_points(market, name, px, kind):
    if market == "MCX":
        return np.array([CM.cost_points("MCX", name, p) for p in px])
    if market == "NSE_EQ":
        return CM.cost_points("NSE_EQ", name, px, kind=kind)
    return CM.cost_points("NSE_FUT", name, px)


def iend_intraday(f, square_off=None):
    dl = f.dlast.values.astype(np.int64)
    if square_off is None:
        return dl
    endm = (f.end.dt.hour * 60 + f.end.dt.minute).values
    ok = endm <= square_off
    idx = np.arange(len(f))
    last_ok = pd.Series(np.where(ok, idx, np.nan)).groupby(f.day.values).transform("max").values
    return np.where(np.isfinite(last_ok), last_ok, dl).astype(np.int64)


def iend_positional(f, maxh=20):
    n = len(f); roll = np.asarray(f["roll"].values, bool)
    nxt = np.full(n, n, np.int64)
    r = np.where(roll)[0]
    j = len(r) - 1
    for i in range(n - 1, -1, -1):
        while j >= 0 and r[j] > i:
            j -= 1
        nxt[i] = r[j + 1] if j + 1 < len(r) else n
    return np.minimum(np.minimum(np.arange(n) + maxh, nxt - 1), n - 1).astype(np.int64)


def run_frame(f, horizon, wkey, buy_only=False, square_off=None, dtrend=None):
    """-> trades DataFrame, signal-count rows"""
    if f is None or len(f) < WARMUP + 40:
        return None, []
    market, name, tf = f.attrs["market"], f.attrs["name"], f.attrs["tf"]
    fam = SG.families(f)
    flt = SG.filters(f, dtrend)
    reg = SG.regime(f)
    o, h, l, c, a = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close", "atr"))
    n = len(c); idx = np.arange(n)
    base_ok = f.sig_ok.values.astype(bool) & (idx >= WARMUP) & np.isfinite(a) & (a > 0) & (idx < n - 1)
    per = W.period(f.time, wkey)
    if horizon == "intraday":
        IE = iend_intraday(f, square_off)
        base_ok &= IE > idx
    elif horizon == "positional":
        IE = iend_positional(f)
        base_ok &= IE > idx
    else:
        IE = None
        nxt_roll = np.r_[np.asarray(f["roll"].values, bool)[1:], True]
        base_ok &= ~nxt_roll
    kind = "intraday" if horizon == "intraday" else "delivery"
    cost_all = None
    rows, sigrows = [], []
    for fname, (fb, fs) in fam.items():
        for side, fsig in ((1, fb), (-1, fs)):
            if buy_only and side < 0:
                continue
            for flt_name, (ob, os_) in flt.items():
                ok = fsig & (ob if side > 0 else os_) & base_ok
                I_ = np.flatnonzero(ok).astype(np.int64)
                sigrows.append(dict(market=market, inst=name, tf=tf, fam=fname, side=side, filt=flt_name, signals=int(len(I_)),
                                    sig_DEV=int((per[I_] == "DEV").sum()), sig_VALID=int((per[I_] == "VALID").sum()), sig_OOS=int((per[I_] == "OOS").sum())))
                if not len(I_):
                    continue
                if cost_all is None:
                    cost_all = np.asarray(cost_frac_or_points(market, name, c, kind), float)
                for xname, spec in EXITS[horizon].items():
                    if horizon == "overnight":
                        j = I_ + 1
                        ex_px = o[j] if spec == "next_open" else c[j]
                        g = side * (ex_px - c[I_]) / a[I_]
                        cr = cost_all[I_] / a[I_]
                        res = np.c_[g - cr, g, j, I_, np.full(len(I_), np.nan), np.full(len(I_), np.nan)]
                        cost_r = cr
                    else:
                        k, tg, tr = spec
                        S = np.full(len(I_), side, np.int64)
                        ent = o[np.minimum(I_ + 1, n - 1)]
                        stop = ent - side * k * a[I_]
                        res = EX.run_stream(o, h, l, c, I_, S, stop, IE[I_], cost_all[I_], a[I_], np.full(len(I_), np.nan),
                                            np.full(len(I_), np.nan), tg, tr, 0, 1.0)
                        cost_r = cost_all[I_] / (k * a[I_])
                    m = ~np.isnan(res[:, 0])
                    if not m.any():
                        continue
                    ii = I_[m]; r = res[m]
                    tg_ = 0.0 if horizon == "overnight" else EXITS[horizon][xname][1]
                    etype = np.where((tg_ > 0) & (r[:, 1] >= tg_ - 1e-6), "target",
                                     np.where(r[:, 1] <= -0.999, "stop", "time/trail/session"))
                    if horizon == "overnight":
                        etype = np.full(len(ii), "overnight")
                    rows.append(pd.DataFrame(dict(
                        market=market, inst=name, tf=tf, fam=fname, side=side, filt=flt_name, exit=xname,
                        date=f.time.values[ii], period=per[ii], r1=r[:, 0], r2=r[:, 0] - cost_r[m], gross=r[:, 1],
                        etype=etype, regime=reg[ii], hold=(r[:, 2] - r[:, 3]).astype(np.int64))))
    T = pd.concat(rows, ignore_index=True) if rows else None
    return T, sigrows


def _job(args):
    cell, key = args
    t0 = time.time()
    try:
        if cell == "mcx_intraday":
            base = FR.mcx_base(key); out = []
            for tf in (15, 30):
                f = FR.mcx_intraday(key, tf, base)
                out.append(run_frame(f, "intraday", "MCX", dtrend=SG.daily_trend_for_intraday(f)))
        elif cell == "mcx_positional":
            base = FR.mcx_base(key); out = []
            for tf in (60, 240, 1440):
                f = FR.mcx_positional(key, tf, base)
                out.append(run_frame(f, "positional", "MCX", dtrend=SG.daily_trend_for_intraday(f) if tf < 1440 else None))
                if tf == 1440:
                    out.append(run_frame(f, "overnight", "MCX"))
        elif cell == "eq_intraday":
            out = []
            for tf in (15, 60):
                f = FR.eq_intraday(key, tf)
                out.append(run_frame(f, "intraday", "NSE_EQ_INTRADAY", buy_only=False, square_off=15 * 60 + 15,
                                     dtrend=SG.daily_trend_for_intraday(f)))
        elif cell == "fut_intraday":
            f = FR.fut_intraday(key)
            out = [run_frame(f, "intraday", "NSE_FUT_INTRADAY", square_off=15 * 60 + 15,
                             dtrend=SG.daily_trend_for_intraday(f) if f is not None else None)]
        else:
            f, horizon_list, wk, bo = key
            out = [run_frame(f, hz, wk, buy_only=bo) for hz in horizon_list]
        Ts = [x[0] for x in out if x[0] is not None]
        Ss = [r for x in out for r in x[1]]
        T = pd.concat(Ts, ignore_index=True) if Ts else None
        return T, Ss, None, time.time() - t0
    except Exception as e:                                        # noqa: BLE001
        return None, [], f"{cell} {key if isinstance(key, str) else key[0].attrs.get('name')}: {type(e).__name__}: {e} | {traceback.format_exc(limit=3)[-400:]}", time.time() - t0


def horizon_tag(cell, T):
    if cell in ("mcx_intraday", "eq_intraday", "fut_intraday"):
        return np.full(len(T), "intraday")
    if cell == "mcx_positional":
        return np.where(T.exit.isin(["X1", "X2"]) & (T.etype == "overnight"), "overnight", "positional")
    return np.where(T.etype == "overnight", "overnight", "positional")


def main(cell):
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if cell == "mcx_intraday" or cell == "mcx_positional":
        jobs = [(cell, n) for n in FR.MCX7]
    elif cell == "eq_intraday":
        jobs = [(cell, s) for s in __import__("research.mcxe003.bars", fromlist=["x"]).nse_eq_symbols()]
    elif cell == "fut_intraday":
        jobs = [(cell, p.name.split("_ONE_HOUR")[0]) for p in sorted((ROOT / "research/data/angel/NFO_STK").glob("*_ONE_HOUR.csv"))]
    elif cell == "fut_daily":
        jobs = [(cell, (f, ("positional", "overnight"), "NSE_FUT", False)) for f in FR.fut_daily()]
    elif cell == "eq_daily":
        jobs = [(cell, (f, ("positional", "overnight"), "NSE_EQ", True)) for f in FR.eq_daily()]
    else:
        raise SystemExit(cell)
    print(cell, "jobs", len(jobs), f"{time.time() - t0:.0f}s", flush=True)
    Ts, Ss, errs = [], [], []
    with Pool(2) as P:
        for k, (T, S, err, dt) in enumerate(P.imap_unordered(_job, jobs, chunksize=1 if len(jobs) < 50 else 4), 1):
            if T is not None:
                Ts.append(T)
            Ss += S
            if err:
                errs.append(err); print("ERROR", err, flush=True)
            if k % 50 == 0:
                print(k, f"{time.time() - t0:.0f}s", flush=True)
    T = pd.concat(Ts, ignore_index=True) if Ts else pd.DataFrame()
    if len(T):
        T["horizon"] = horizon_tag(cell, T)
        T["cell"] = cell
        for col in ("market", "inst", "fam", "filt", "exit", "period", "etype", "regime", "horizon", "cell"):
            T[col] = T[col].astype("category")
        for col in ("r1", "r2", "gross"):
            T[col] = T[col].astype("float32")
    T.to_parquet(OUT / f"trades_{cell}.parquet", index=False)
    pd.DataFrame(Ss).to_csv(OUT / f"signals_{cell}.csv.gz", index=False)
    (OUT / f"errors_{cell}.txt").write_text("\n".join(errs))
    print(cell, "trades", len(T), "errors", len(errs), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])

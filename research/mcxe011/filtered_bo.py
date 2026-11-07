"""MCXE-011b: breakout / breakdown + confirmation filters (volume, OI, ADX, VWAP) on 15m / 1h. Exploratory: DEV + VALID only,
OOS masked; VALID is not fresh. All filters are known at the signal close:
  vol  : volume >= 1.5 x its 20-bar average (previous bars)
  vwap : close above (BUY) / below (SELL) the session VWAP
  adx  : ADX(14) >= 20 and DI+ > DI- (BUY) / DI- > DI+ (SELL)
  oi   : PREVIOUS session's exchange OI change of the front contract > 0 with the price change in the trade direction
         (long build-up for BUY, short build-up for SELL) – intraday OI history does not exist, so the last known daily OI
  all  : vol + vwap + adx + oi
Bases (same exits as MCXE-011): MCX 1h Donchian-20 (BUY side = live H1.12L entry), MCX 15m Donchian-80, stock futures 1h
Donchian-20; 2 ATR stop, 4 ATR trail. Freeze bar + random control as in MCXE-011.
python research/mcxe011/filtered_bo.py -> research/mcxe011/FILTERED_RESULTS.csv"""
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402
from research.mcxe005 import frames as FR  # noqa: E402
from research.mcxe006 import engine as EN6  # noqa: E402
from research.mcxe007 import engine7 as E7, data7 as DA7  # noqa: E402
from research.mcxe011 import intraday_bo as IB  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

OUT = ROOT / "research/mcxe011"
VARIANTS = {"base": (), "vol": ("vol",), "vwap": ("vwap",), "adx": ("adx",), "oi": ("oi",), "all": ("vol", "vwap", "adx", "oi")}


def mcx_daily_oi():
    """front (highest-OI) MCX futures contract per commodity and day -> (OI change vs previous day of the SAME contract,
    price change). In-window rows only."""
    w = W.get("MCX"); rows = []
    for p in sorted(glob.glob(str(ROOT / "research/data/mcx_bhav/days/*.csv"))):
        d = pd.Timestamp(Path(p).stem)
        if d < w["start"] - pd.Timedelta(days=7) or d > w["reference"]:
            continue
        x = pd.read_csv(p)
        x = x[(x.instrument == "FUTCOM") & x.symbol.isin(FR.MCX7)][["date", "symbol", "expiry", "close", "oi_lots"]]
        rows.append(x)
    X = pd.concat(rows); X["date"] = pd.to_datetime(X.date)
    X = X[X.date >= w["start"]]
    out = {}
    for n, g in X.groupby("symbol"):
        g = g.sort_values("date"); res = {}
        prev = None
        for d, gd in g.groupby("date"):
            fr = gd.loc[gd.oi_lots.idxmax()]
            if prev is not None:
                p = prev[prev.expiry == fr.expiry]
                if len(p) and p.oi_lots.iat[0] > 0:
                    res[d] = (fr.oi_lots / p.oi_lots.iat[0] - 1, fr.close / p.close.iat[0] - 1)
            prev = gd
        out[n] = res
    return out


def stk_daily_oi():
    out = {}
    for f in DA7.frames("STK"):
        c = f.close.astype(float)
        out[f.attrs["name"]] = {t: (o, r) for t, o, r in zip(f.time.dt.normalize(), f.doi.values, (c / c.shift(1) - 1).values)}
    return out


def prev_session(f, daily):
    """map each bar to the OI / price change of the PREVIOUS trading session (known before this session opens)."""
    days = sorted(daily); s = pd.Series(range(len(days)), index=pd.DatetimeIndex(days))
    out_oi = np.full(len(f), np.nan); out_pr = np.full(len(f), np.nan)
    dd = f.time.dt.normalize().values
    for j, d in enumerate(dd):
        k = s.index.searchsorted(d) - 1                  # last session strictly before this bar's day
        if k >= 0:
            out_oi[j], out_pr[j] = daily[days[k]]
    return out_oi, out_pr


def make_fn(N, flt, oimap):
    def fn(f, side, extra=None, **kw):
        o, h, l, c, v = (f[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
        lvl = h.shift(1).rolling(N).max() if side > 0 else l.shift(1).rolling(N).min()
        sig = ((side * (c - lvl) > 0) & (side * (c.shift(1) - lvl.shift(1)) <= 0)).fillna(False).values.copy()
        if "vol" in flt:
            sig &= (v > 1.5 * v.rolling(20).mean().shift(1)).fillna(False).values
        if "vwap" in flt:
            sig &= np.nan_to_num(side * (c.values - f.vwap.values.astype(float)), nan=-1) > 0
        if "adx" in flt:
            up, dn = h.diff(), -l.diff()
            pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0)); ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0))
            tr = I.true_range(f).ewm(alpha=1 / 14, adjust=False).mean().values
            di = (pdm.ewm(alpha=1 / 14, adjust=False).mean().values - ndm.ewm(alpha=1 / 14, adjust=False).mean().values) / tr
            sig &= (I.adx(f, 14).values >= 20) & (np.nan_to_num(side * di, nan=-1) > 0)
        if "oi" in flt:
            d = oimap.get(f.attrs["name"])
            if not d:
                sig[:] = False
            else:
                oi, pr = prev_session(f, d)
                sig &= np.nan_to_num(oi, nan=-1) > 0
                sig &= np.nan_to_num(side * pr, nan=-1) > 0
        return dict(sig=sig, warm=N + 30, entry="open")
    return fn


def main():
    from research.program import mcx_disc as MD
    mcx1h = EN6.frames("MCX", 60)
    for f in mcx1h:
        f.attrs.update(kind="MCX", wkey="MCX", mult=MD.REG[f.attrs["name"]]["mult"])
    moi, soi = mcx_daily_oi(), stk_daily_oi()
    markets = [("MCX_1h", mcx1h, 20, dict(k=2.0, trail=4.0, maxbars=240), moi),
               ("MCX_15m", IB.mcx15(), 80, dict(k=2.0, trail=4.0, maxbars=960), moi),
               ("STK_1h", IB.stk1h(), 20, dict(k=2.0, trail=4.0, maxbars=112), soi)]
    rows = []
    for mk, fs, N, exitp, oimap in markets:
        for side in (1, -1):
            for vn, flt in VARIANTS.items():
                T = E7.run(fs, make_fn(N, flt, oimap), {}, exitp, side)
                r = dict(market=mk, side="BUY" if side > 0 else "SELL", N=N, filters=vn, **(IB.summ(T) if len(T) else {}))
                if r.get("eligible"):
                    r["random_2x"], r["random_p95"] = IB.control(fs, T, exitp, side)
                    r["beats_random_p95"] = bool(T[T.period.isin(["DEV", "VALID"])].r2.mean() > r["random_p95"])
                rows.append(r)
                print(mk, r["side"], vn, {k: r.get(k) for k in ("DEV_n", "DEV_exp2", "VALID_n", "VALID_exp2", "VALID_win", "DV_ci_lo", "eligible", "beats_random_p95")}, flush=True)
        pd.DataFrame(rows).to_csv(OUT / "FILTERED_RESULTS.csv", index=False)


if __name__ == "__main__":
    main()

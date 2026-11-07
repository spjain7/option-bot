"""Forward-move measurement and MATCHED controls for intraday frames (MCXE-003 stage 1).

For every bar i (as if it were a BUY signal):
  fe_h   = (close[min(i+h, dlast)] - open[i+1]) / atr[i]     entry at the next bar's open (executable), h in HORIZ
  fd_h   = (close[min(i+h, dlast)] - close[i]) / atr[i]       from the signal close (diagnostic: is information spent?)
  fe_eod = close[dlast] - open[i+1] in ATR ;  mfe / mae over 12 bars after entry (same session)
Bars whose next bar is in another session have no entry (NaN). Horizons never cross a session -> never cross a roll.
Control expectation of each measure = the mean over ALL signal-eligible bars of the same instrument with the same bar
start time (minute of day) and the same calendar quarter ("time-of-day x quarter matched control"). For a SELL the
control is the negative of that mean. excess = side * (measure - control).
"""
import numpy as np
import pandas as pd

HORIZ = (1, 3, 6, 12)


def forward(f):
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    dl = f.dlast.values.astype(np.int64); n = len(c); idx = np.arange(n)
    ok = (idx + 1 <= dl)
    ent = np.where(ok, o[np.minimum(idx + 1, n - 1)], np.nan)
    out = {}
    for hz in HORIZ:
        j = np.minimum(idx + hz, dl)
        out[f"fe{hz}"] = (c[j] - ent) / a
        out[f"fd{hz}"] = (c[j] - c) / a
    out["feEOD"] = (c[dl] - ent) / a
    # MFE / MAE over 12 bars
    hi = pd.Series(h[::-1]).rolling(12, min_periods=1).max().values[::-1]           # max of h[k .. k+11]
    lo = pd.Series(l[::-1]).rolling(12, min_periods=1).min().values[::-1]
    # restrict to the session: recompute exactly where the 12-bar window crosses the session end
    k1 = np.minimum(idx + 1, n - 1)
    mfe = hi[k1]; mae = lo[k1]
    cross = (idx + 12 > dl)
    for i in np.where(cross & ok)[0]:
        mfe[i] = h[i + 1:dl[i] + 1].max(); mae[i] = l[i + 1:dl[i] + 1].min()
    out["mfe"] = (mfe - ent) / a; out["mae"] = (mae - ent) / a
    F = pd.DataFrame(out)
    F.loc[~ok, :] = np.nan
    return F


def control_means(f, F):
    q = f.time.dt.to_period("Q").astype(str).values
    key = pd.Series(q).str.cat(f.m.astype(str).values, sep="|")
    elig = f.sig_ok.values & F.fe1.notna().values
    G = F[elig].groupby(key[elig].values).mean()
    return key, G


def event_measures(f, E, F, key, G):
    """returns DataFrame aligned with E: raw measures (side-signed) and excess vs control."""
    if E.empty:
        return pd.DataFrame()
    i = E.i.values; sd = E.side.values.astype(float)
    R = F.iloc[i].reset_index(drop=True)
    C = G.reindex(key.iloc[i].values).reset_index(drop=True)
    out = pd.DataFrame(index=R.index)
    for col in F.columns:
        if col in ("mfe", "mae"):
            continue
        out[col] = R[col].values * sd
        out["x_" + col] = (R[col].values - C[col].values) * sd
    out["mfe"] = np.where(sd > 0, R.mfe.values, -R.mae.values)
    out["mae"] = np.where(sd > 0, R.mae.values, -R.mfe.values)
    return out

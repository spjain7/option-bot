import numpy as np
import pandas as pd

RNG = np.random.default_rng(12345)


def max_consec_losses(r):
    m = c = 0
    for x in r:
        c = c + 1 if x <= 0 else 0; m = max(m, c)
    return m


def boot_p5(r, n=5000):
    r = np.asarray(r, float)
    if len(r) < 5:
        return np.nan
    idx = RNG.integers(0, len(r), size=(n, len(r)))
    return float(np.percentile(r[idx].mean(axis=1), 5))


def stats(t, col="net_R", capital=None):
    if t is None or t.empty:
        return dict(trades=0)
    t = t.sort_values("exit_time")
    r = t[col].values; eq = np.cumsum(r)
    w, l = r[r > 0], r[r <= 0]
    yrs = pd.to_datetime(t["exit_time"]).dt.year
    by_year = t.groupby(yrs)[col].sum()
    out = dict(trades=len(r), win_pct=round((r > 0).mean() * 100, 1), expectancy_R=round(r.mean(), 3),
               gross_expectancy_R=round(t["gross_R"].mean(), 3), total_R=round(r.sum(), 1),
               pf=round(w.sum() / -l.sum(), 2) if l.sum() < 0 else np.inf,
               max_dd_R=round(float((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()), 1),
               max_consec_losses=max_consec_losses(r), avg_days=round(t["days"].mean(), 1),
               avg_mae_R=round(t["mae_R"].mean(), 2), avg_mfe_R=round(t["mfe_R"].mean(), 2),
               boot_p5_R=round(boot_p5(r), 3), years_pos_pct=round((by_year > 0).mean() * 100) if len(by_year) else np.nan,
               long_n=int((t["side"] == "LONG").sum()), long_exp_R=round(t.loc[t.side == "LONG", col].mean(), 3) if (t.side == "LONG").any() else np.nan,
               short_n=int((t["side"] == "SHORT").sum()), short_exp_R=round(t.loc[t.side == "SHORT", col].mean(), 3) if (t.side == "SHORT").any() else np.nan)
    if "pnl_rs_1lot" in t:
        pnl = t["pnl_rs_1lot"].values; eqr = np.cumsum(pnl)
        out.update(total_rs_1lot=round(pnl.sum()), max_dd_rs_1lot=round(float((eqr - np.maximum.accumulate(np.r_[0, eqr])[1:]).min())))
        if capital:
            out.update(total_pct_1lot=round(pnl.sum() / capital * 100, 1),
                       max_dd_pct_1lot=round(out["max_dd_rs_1lot"] / capital * 100, 1))
    return out


def period(t, start, end=None, col="entry_time"):
    if t is None or t.empty:
        return t
    x = pd.to_datetime(t[col])
    m = x >= pd.Timestamp(start)
    if end:
        m &= x <= pd.Timestamp(end)
    return t[m]

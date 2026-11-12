"""Unit tests for the MCX institutional BUY research engine.  python -m pytest research/mcx_institutional_buy/tests -q"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.mcx_institutional_buy.feature_engineering import ind as I  # noqa: E402
from research.mcx_institutional_buy.feature_engineering import build as B  # noqa: E402
from research.mcx_institutional_buy.backtesting import sim as S, costs as K, metrics as M, runner as RN  # noqa: E402


def _sim(o, h, l, c, sig, stop, kind=0, Rm=2.0, elev=None, seg=None, maxhold=50, ntime=10, tgt=None, cost=0.0):
    n = len(c); a = np.ones(n)
    return S.simulate(np.asarray(o, float), np.asarray(h, float), np.asarray(l, float), np.asarray(c, float), a,
                      np.zeros(n, np.int64) if seg is None else np.asarray(seg, np.int64), np.full(n, cost),
                      np.asarray(sig, bool), np.asarray(stop, float), np.full(n, np.nan) if elev is None else np.asarray(elev, float),
                      np.full(n, np.nan) if tgt is None else np.asarray(tgt, float), kind, Rm, maxhold, ntime, 3.0, 3, 0.25, 4.0, 1.5)


def test_rsi_bounds_and_no_loss_is_100():
    c = np.arange(1, 60, dtype=float)
    r = I.rsi(c, 14)
    assert np.nanmin(r) == 100.0
    x = np.r_[np.linspace(100, 80, 30), np.linspace(80, 90, 30)]
    r = I.rsi(x, 14); assert np.nanmax(r) <= 100 and np.nanmin(r) >= 0


def test_pivot_known_only_after_right_bars():
    lo = np.array([5, 4, 3, 2, 3, 4, 5, 6, 7, 8], float); hi = lo + 1
    pl, _ = I.pivots(lo, hi, 2, 2)
    assert pl[3] and pl.sum() == 1
    lv, ix = I.known_levels(pl, lo, 2, 2)
    assert np.isnan(lv[4, 0]) and lv[5, 0] == 2.0 and ix[5, 0] == 3     # known at p+R = 5, not before


def test_pivot_no_lookahead_future_change():
    rng = np.random.default_rng(1); lo = rng.normal(100, 1, 200); hi = lo + 1
    pl, _ = I.pivots(lo, hi, 3, 3); lv, _ = I.known_levels(pl, lo, 3, 1)
    lo2 = lo.copy(); lo2[150:] -= 50                                         # change the future after bar 149
    pl2, _ = I.pivots(lo2, lo2 + 1, 3, 3); lv2, _ = I.known_levels(pl2, lo2, 3, 1)
    assert np.allclose(lv[:150], lv2[:150], equal_nan=True)


def test_regular_divergence_signal_time():
    lo = np.array([10, 9, 8, 9, 10, 11, 10, 9, 7.5, 9, 10, 11, 12], float)
    ind = np.array([50, 40, 30, 40, 50, 55, 50, 45, 35, 45, 50, 55, 60], float)  # higher indicator low at the lower price low
    pl, _ = I.pivots(lo, lo + 1, 2, 2)
    sig, p2 = I.divergence(lo, ind, pl, 2, 3, 60, False)
    assert sig.sum() == 1 and np.where(sig)[0][0] == 10 and p2[10] == 8   # known 2 bars after the second low
    hsig, _ = I.divergence(lo, ind, pl, 2, 3, 60, True)
    assert hsig.sum() == 0


def test_stop_first_and_gap_through():
    o = [10, 10, 10, 8.0, 9]; h = [10, 10.5, 10.2, 8.5, 9]; l = [9.5, 9.6, 9.6, 7.5, 9]; c = [10, 10, 10, 8, 9]
    sig = [True, False, False, False, False]; stop = [9.5, 0, 0, 0, 0]
    s, e, x, g, nr, *_ = _sim(o, h, l, c, sig, stop)
    assert e[0] == 1 and x[0] == 3 and abs(g[0] - (8.0 - 10) / 0.5) < 1e-9   # gap below the stop fills at the open (-4R)


def test_target_and_same_bar_stop_priority():
    o = [10, 10, 10]; h = [10, 12, 12]; l = [10, 9.0, 9]; c = [10, 11, 11]
    s, e, x, g, *_ = _sim(o, h, l, c, [True, False, False], [9.5, 0, 0])
    assert g[0] == -1.0                                                     # stop and target in one bar -> stop
    o = [10, 10, 10, 10]; h = [10, 10.4, 11.2, 11]; l = [10, 9.8, 9.9, 10]; c = [10, 10.2, 11, 10.5]
    s, e, x, g, *_ = _sim(o, h, l, c, [True, False, False, False], [9.5, 0, 0, 0])
    assert abs(g[0] - 2.0) < 1e-9 and x[0] == 2


def test_no_trade_across_contract_switch():
    n = 10; o = np.full(n, 10.0); h = o + 0.1; l = o - 0.1; c = o.copy(); seg = [0] * 5 + [1] * 5
    sig = np.zeros(n, bool); sig[3] = True; stop = np.full(n, 9.0)
    s, e, x, g, nr, mfe, mae, why, rej = _sim(o, h, l, c, sig, stop, seg=seg)
    assert x[0] == 4 and why[0] == 4                                        # closed on the last bar before the switch
    sig = np.zeros(n, bool); sig[4] = True
    s, *_ = _sim(o, h, l, c, sig, stop, seg=seg)
    assert len(s) == 0                                                      # signal on the last bar of a segment: no entry


def test_entry_after_signal_and_no_overlap():
    n = 30; o = np.full(n, 10.0); h = o + 0.2; l = o - 0.2; c = o.copy()
    sig = np.ones(n, bool); stop = np.full(n, 9.0)
    s, e, x, *_ = _sim(o, h, l, c, sig, stop, kind=3, ntime=5)
    assert (e > s).all() and (e[1:] > x[:-1]).all()                        # one position at a time


def test_stop_entry_mode():
    o = [10, 10, 10.1, 10.6, 11]; h = [10, 10.2, 10.7, 11.0, 11]; l = [9.8, 9.9, 10.0, 10.5, 11]; c = [10, 10.1, 10.6, 10.9, 11]
    elev = [10.5, np.nan, np.nan, np.nan, np.nan]
    s, e, x, g, *_ = _sim(o, h, l, c, [True, 0, 0, 0, 0], [9.5, 0, 0, 0, 0], elev=elev, kind=3, ntime=2)
    assert e[0] == 2                                                        # filled on the bar that reached 10.5


def test_structural_target_rejects_low_rr():
    o = [10, 10, 10]; h = [10, 10.4, 10.4]; l = [10, 9.9, 9.9]; c = [10, 10.2, 10.2]
    s, e, x, g, nr, mfe, mae, why, rej = _sim(o, h, l, c, [True, 0, 0], [9.5, 0, 0], kind=1, tgt=[10.6, np.nan, np.nan])
    assert len(s) == 0 and rej == 1                                         # reward 0.6 / risk 0.5 = 1.2 < 1.5


def test_costs_ctt_history_and_positive():
    p = np.array([60000.0, 60000.0]); t = pd.to_datetime(["2012-01-02", "2020-01-02"])
    f = K.cost_frac("GOLD", p, t)
    assert f[1] > f[0] > 0 and abs((f[1] - f[0]) * p[0] - 60000 * 0.0001) < 1e-6


def test_net_r_subtracts_cost():
    o = [10, 10, 10, 10]; h = [10, 10.4, 11.2, 11]; l = [10, 9.8, 9.9, 10]; c = [10, 10.2, 11, 10.5]
    s, e, x, g, nr, *_ = _sim(o, h, l, c, [True, 0, 0, 0], [9.5, 0, 0, 0], cost=0.005)
    assert abs((g[0] - nr[0]) - 0.005 * 10 / 0.5) < 1e-9


def test_period_levels_previous_day_only():
    t = pd.Series(pd.to_datetime(["2024-01-01 10:00", "2024-01-01 11:00", "2024-01-02 10:00", "2024-01-02 11:00"]))
    h = np.array([5, 6, 7, 8.0]); l = np.array([1, 2, 3, 0.5])
    ph, pl = B._period_levels(t, h, l, "D")
    assert np.isnan(pl[0]) and pl[2] == 1 and pl[3] == 1 and ph[3] == 6


def test_map_prev_day_shift():
    day = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-02"]))
    s = pd.Series([10.0, 20.0], index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    m = B._map_prev_day(day, s)
    assert np.isnan(m[0]) and m[1] == 10 and m[2] == 10                     # day-2 bars see day-1's value only


def test_first_and_cross_and_runlen():
    x = np.array([0, 1, 1, 0, 1], bool)
    assert I.first(x).tolist() == [False, True, False, False, True]
    assert I.cross_up(np.array([20, 24, 26, 30.0]), 25).tolist() == [False, False, True, False]
    assert I.run_len(x).tolist() == [0, 1, 2, 0, 1]


def test_rvol_uses_prior_bars_only():
    v = np.r_[np.full(30, 100.0), 1000.0]
    avg = pd.Series(v).rolling(20, min_periods=10).mean().shift(1).values
    assert abs(v[-1] / avg[-1] - 10) < 1e-9


def test_bh_and_summary():
    assert M.bh([0.001, 0.5, 0.02], 0.1).tolist() == [True, False, True]
    T = pd.DataFrame(dict(netR=[1.0, -1, 2, -1], exit_t=pd.date_range("2024", periods=4), entry=pd.date_range("2024", periods=4),
                          mfeR=0.0, maeR=0.0, bars=1, name="X"))
    s = M.summary(T); assert s["n"] == 4 and s["PF"] == 1.5 and s["max_consec_loss"] == 1


def test_period_split():
    p = RN.period_of("1h", pd.to_datetime(["2023-01-01", "2024-08-01", "2025-08-01"]))
    assert p.tolist() == ["TRAIN", "VAL", "OOS"]
    p = RN.period_of("1d", pd.to_datetime(["2010-01-01", "2018-01-01", "2023-01-01"]))
    assert p.tolist() == ["TRAIN", "VAL", "OOS"]


def test_integration_every_commodity_builds():
    from research.mcx_institutional_buy.backtesting import data as D
    for name in D.INTRA:
        F = RN.features(name, "1h")
        assert F is not None and len(F["TRIG"]) > 150
        for k, (sig, stop, elev, fam, mod) in F["TRIG"].items():
            ok = sig & np.isfinite(stop)
            assert (stop[ok] < F["c"][ok] + 10 * F["atr"][ok]).all()
    F = RN.features("LEAD", "1d"); assert F is not None

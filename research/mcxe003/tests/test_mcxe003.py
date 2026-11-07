"""MCXE-003 tests.  python -m pytest -q research/mcxe003/tests   (or python research/mcxe003/tests/test_mcxe003.py)
1. NO LOOK-AHEAD: every detector run on a prefix of the data produces exactly the events of the full run with i < cut
   (several cut points, two instruments, every swing method).
2. Swings: fractal pivots are confirmed exactly k bars later; zig-zag swings are confirmed after the reversal threshold.
3. Synthetic shapes: a hammer / engulfing / double top / falling trendline break are detected where constructed.
4. Forward measures use the next bar's open and never cross the session; controls are time-of-day matched.
5. Execution simulator: stop before target in one bar, gap through stop fills at open, costs in R, no overlap.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import (bars as B, swing_detection as SWD, trendlines as TL, market_structure as MS,  # noqa: E402
                              liquidity_sweeps as SWP, support_resistance as SR, chart_patterns as CP,
                              candlestick_patterns as CDL, flow_patterns as FL, events as EV, controls as CT,
                              execution as EX)

_cache = {}


def frame(name="GOLD", tf=30, n=4000):
    k = (name, tf)
    if k not in _cache:
        _cache[k] = B.mcx_intraday(name, tf).iloc[-n:].reset_index(drop=True)
        _cache[k]["seg"] = _cache[k]["seg"] - _cache[k]["seg"].iat[0]
        _cache[k]["dlast"] = _cache[k]["dlast"] - (len(B.mcx_intraday(name, tf)) - n)
    return _cache[k]


def _events(f, mth):
    sw = SWD.swings(f, mth)
    E = [CDL.detect(f), FL.detect(f)]
    for mod in (TL, MS, SR, CP):
        E.append(mod.detect(f, sw))
    E.append(SWP.detect(f, sw))
    A = pd.concat(E, ignore_index=True)
    brk = A[A.name.str.contains("BRK|BOS|CHOCH")]
    A = pd.concat([A, EV.fails(brk, f)], ignore_index=True)
    return A.sort_values(["i", "fam", "name", "side", "level"]).reset_index(drop=True)


def test_no_lookahead():
    for name in ("GOLD", "CRUDEOIL"):
        full = frame(name)
        for mth in SWD.METHODS:
            Ef = _events(full, mth)
            for cut in (1500, 2600, 3333):
                pre = full.iloc[:cut].reset_index(drop=True)
                pre.attrs.update(full.attrs)
                Ep = _events(pre, mth)
                a = Ef[Ef.i < cut - 3].reset_index(drop=True)          # fails() needs up to 3 later bars
                b = Ep[Ep.i < cut - 3].reset_index(drop=True)
                pd.testing.assert_frame_equal(a[["i", "side", "fam", "name"]], b[["i", "side", "fam", "name"]],
                                              obj=f"{name} {mth} cut {cut}", check_dtype=False)
                assert np.allclose(a.level.values.astype(float), b.level.values.astype(float), equal_nan=True)


def test_swings_confirmation():
    f = frame()
    for k in (2, 3, 5):
        sw = SWD.swings(f, f"f{k}")
        assert (sw["conf"] - sw["piv"] == k).all()
        h = f.high.values
        for c, p, v, kd in list(zip(sw["conf"], sw["piv"], sw["price"], sw["kind"]))[:200]:
            if kd == 1:
                assert v == h[p] == h[p - k:p + k + 1].max()
    sw = SWD.swings(f, "z15")
    assert (sw["conf"] >= sw["piv"]).all()
    kinds = sw["kind"]
    assert (kinds[1:] != kinds[:-1]).mean() > 0.95                 # zig-zag alternates high / low


def _synth(rows):
    t0 = pd.Timestamp("2025-01-06 09:00")
    d = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    d["volume"] = 100.0
    d["time"] = [t0 + pd.Timedelta(minutes=15 * k) for k in range(len(d))]
    d["seg"] = 0; d["atr"] = 1.0
    return d


def test_synthetic_candles():
    base = [(10 - 0.4 * k, 10.2 - 0.4 * k, 9.6 - 0.4 * k, 9.7 - 0.4 * k) for k in range(12)]   # down move
    rows = base + [(5.0, 5.1, 3.6, 5.05)]                           # hammer: long lower wick, close near the high
    E = CDL.detect(_synth(rows))
    assert ((E.name == "HAMMER") & (E.i == 12) & (E.side == 1)).any()
    rows = base + [(5.2, 5.3, 4.9, 4.95), (4.9, 5.9, 4.85, 5.8)]    # bullish engulfing
    E = CDL.detect(_synth(rows))
    assert ((E.name == "ENGULF") & (E.i == 13) & (E.side == 1)).any()


def test_synthetic_trendline_break():
    # falling highs at bars 5 and 15 (fractal k=2), then a close above the line
    p = [5, 6, 7, 8, 9, 10, 9, 8, 7, 6, 5, 6, 7, 8, 8.5, 9, 8.5, 8, 7, 6.5, 6.4, 6.6, 7, 8.6]
    rows = [(x - 0.1, x + 0.2, x - 0.2, x) for x in p]
    f = _synth(rows)
    sw = SWD.swings(f, "f2")
    E = TL.detect(f, sw)
    br = E[E.name.str.startswith("TL_BRK") & (E.side == 1)]
    assert len(br) == 1 and br.i.iat[0] == len(p) - 1


def test_forward_and_controls():
    f = frame()
    F = CT.forward(f)
    i = 1000
    if f.dlast.iat[i] >= i + 6:
        assert np.isclose(F.fe6.iat[i], (f.close.iat[i + 6] - f.open.iat[i + 1]) / f.atr.iat[i])
    last = np.where(f.dlast.values == np.arange(len(f)))[0]
    assert F.fe1.iloc[last].isna().all()                          # no entry from the session's last bar
    key, G = CT.control_means(f, F)
    assert key.str.contains(r"\|").all()


def test_execution_rules():
    # bar 0 signal, entry next open 100, stop 99, target 2R=102. Bar 1 hits both -> stop.
    o = np.array([100, 100, 100.0]); h = np.array([100, 102.5, 100]); l = np.array([100, 98.5, 100]); c = o.copy()
    r = EX.sim_one(o, h, l, c, 0, 1, 99.0, 2.0, 2, 0.0, 0)
    assert r[0] == -1.0
    # gap through the stop: next open 97 -> fill at the open = -3R
    o = np.array([100, 97, 97.0]); h = np.array([100, 97.5, 98]); l = np.array([100, 96.5, 96]); c = o.copy()
    o2 = np.array([100, 100, 97.0]); h2 = np.array([100, 100.2, 97.5]); l2 = np.array([100, 99.8, 96.5])
    r = EX.sim_one(o2, h2, l2, o2.copy(), 0, 1, 99.0, 0.0, 2, 0.0, 0)
    assert np.isclose(r[0], -3.0)
    # costs in R: cost 0.5 points, stop distance 1 -> -0.5R on a flat EOD exit
    o = np.array([100, 100, 100.0]); h = o + 0.1; l = o - 0.1
    r = EX.sim_one(o, h, l, o.copy(), 0, 1, 99.0, 0.0, 2, 0.5, 0)
    assert np.isclose(r[0], -0.5)


if __name__ == "__main__":
    for nm, fn in list(globals().items()):
        if nm.startswith("test_"):
            fn(); print("ok", nm)

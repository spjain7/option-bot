"""MCXE-009 weighted indicator scoring – EXPLORATORY research only (DEV + VALID of the approved windows; OOS masked and
never read; VALID is not fresh – it was seen in earlier programs – so nothing here is validation evidence).

Components (all causal, value at bar i uses bars <= i, each in [-1, +1], NaN when the input is missing – never filled):
  ema     clip((EMA20 - EMA50) / ATR)                    trend
  price   clip((close - EMA50) / (2 ATR))                trend
  adx     (DI+ - DI-) / (DI+ + DI-) x min(ADX / 25, 1)   trend strength with direction
  macd    clip(MACD histogram / (0.5 ATR))               momentum
  rsi     clip((RSI14 - 50) / 25)                        momentum (strength)
  rsirev  -clip((RSI14 - 50) / 20) only when RSI > 70 or < 30, else 0   reversal
  bb      clip((close - SMA20) / (2 sd20))               position in Bollinger band (momentum sense)
  brk     +1 close > prior 20-bar high, -1 close < prior 20-bar low, else channel position x 0.5
  vol     sign(close - open) x clip(volume / avg20 - 1, 0, 1)   directional participation
  candle  (close - open) / (high - low)                  candle body direction
  oi      sign(close change) x clip(OI change / 5 %)     build-up (+) / short build-up (-); futures daily only
Model score = sum(w_i s_i) / sum(w_i over components that are not NaN). BUY when the score crosses above +theta, SELL when
it crosses below -theta; theta in {0.4, 0.6}. Exit for every model: 2 ATR stop, 4 ATR trail, time cap (MCXE-006/007 X0).
Weight families: equal, trend, momentum, breakout/volume, RSI-reversal, data-driven (DEV information coefficients).
Selection: per market and side, theta and model are chosen on DEV 2x expectancy only; VALID is reported once.
python research/mcxe009/weighted.py  -> research/mcxe009/RESULTS.csv, results_weights.json"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402
from research.mcxe006 import engine as EN6  # noqa: E402
from research.mcxe007 import engine7 as E7, data7 as DA7, lab7 as L7  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

OUT = ROOT / "research/mcxe009"
COMP = ["ema", "price", "adx", "macd", "rsi", "rsirev", "bb", "brk", "vol", "candle", "oi"]
FAMILIES = {
    "equal": {c: 1.0 for c in COMP},
    "trend": dict(ema=3, price=2, adx=2, macd=1, rsi=0.5, bb=0.5, brk=0.5, vol=0.5, candle=0.5, oi=0.5),
    "momentum": dict(macd=3, rsi=3, candle=1, bb=1, ema=0.5, price=0.5, adx=0.5, brk=0.5, vol=0.5, oi=0.5),
    "breakout_vol": dict(brk=3, vol=2, oi=2, bb=1, ema=0.5, price=0.5, adx=0.5, macd=0.5, rsi=0.5, candle=0.5),
    "rsi_reversal": dict(rsirev=3, candle=1, ema=0.5, price=0.5, adx=0.5),
}
THETAS = (0.4, 0.6)


def clip(x):
    return np.clip(np.asarray(x, float), -1, 1)


def components(f):
    o, h, l, c, v = (f[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    a = f.atr.astype(float).replace(0, np.nan)
    e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    S = {"ema": clip((e20 - e50) / a), "price": clip((c - e50) / (2 * a))}
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0)); ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0))
    tr = I.true_range(f).ewm(alpha=1 / 14, adjust=False).mean().values
    pdi = pdm.ewm(alpha=1 / 14, adjust=False).mean().values / tr; ndi = ndm.ewm(alpha=1 / 14, adjust=False).mean().values / tr
    adx = I.adx(f, 14).values
    S["adx"] = clip((pdi - ndi) / (pdi + ndi) * np.minimum(adx / 25, 1))
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    S["macd"] = clip((macd - macd.ewm(span=9, adjust=False).mean()) / (0.5 * a))
    r = I.rsi(c, 14).values
    S["rsi"] = clip((r - 50) / 25)
    S["rsirev"] = np.where((r > 70) | (r < 30), -clip((r - 50) / 20), np.where(np.isnan(r), np.nan, 0.0))
    sd = c.rolling(20).std()
    S["bb"] = clip((c - c.rolling(20).mean()) / (2 * sd.replace(0, np.nan)))
    hh, ll = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    pos = ((c - (hh + ll) / 2) / ((hh - ll) / 2).replace(0, np.nan)).values
    S["brk"] = np.where(c.values > hh.values, 1.0, np.where(c.values < ll.values, -1.0, 0.5 * clip(pos)))
    S["brk"] = np.where(np.isnan(hh.values), np.nan, S["brk"])
    va = v.rolling(20).mean().shift(1)
    vr = (v / va.replace(0, np.nan)).values
    S["vol"] = np.where(np.isfinite(vr) & (v.values > 0), np.sign(c - o).values * np.clip(vr - 1, 0, 1), np.nan)
    S["candle"] = clip(((c - o) / (h - l).replace(0, np.nan)).values)
    if "doi" in f:
        d = f["doi"].values.astype(float)
        S["oi"] = np.where(np.isfinite(d), np.sign(c.diff().values) * clip(d / 0.05), np.nan)
    else:
        S["oi"] = np.full(len(f), np.nan)
    return S


def score(S, w):
    num = np.zeros(len(S["ema"])); den = np.zeros(len(S["ema"]))
    for k, wk in w.items():
        if not wk:
            continue
        x = S[k]; ok = np.isfinite(x)
        num += np.where(ok, wk * x, 0); den += np.where(ok, abs(wk), 0)
    return np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)


def markets():
    def mcx(tf):
        from research.program import mcx_disc as MD
        fs = EN6.frames("MCX", tf)
        for f in fs:
            f.attrs.update(kind="MCX", wkey="MCX", mult=MD.REG[f.attrs["name"]]["mult"])
        return fs
    from research.mcxe008 import lab8 as L8
    return {"MCX_1h": (lambda: mcx(60), dict(k=2.0, trail=4.0, maxbars=240), 20),
            "MCX_4h": (lambda: mcx(240), dict(k=2.0, trail=4.0, maxbars=120), 10),
            "MCX_1d": (lambda: DA7.frames("MCX"), dict(k=2.0, trail=4.0, maxbars=40), 10),
            "STK_1d": (lambda: DA7.frames("STK"), dict(k=2.0, trail=4.0, maxbars=40), 10),
            "IDX_1d": (lambda: DA7.frames("IDX"), dict(k=2.0, trail=4.0, maxbars=40), 10),
            "IDX_1h": (L8.idx1h, dict(k=2.0, trail=4.0, maxbars=240), 20)}


def dev_ic(fs, comps, H):
    """information coefficient of each component vs the forward H-bar return / ATR, DEV bars only, with the forward
    window also ending inside DEV (no VALID / OOS prices touched)."""
    xs = {k: [] for k in COMP}; ys = []
    for f, S in zip(fs, comps):
        per = np.asarray(W.period(f.time, f.attrs["wkey"]))
        c = f.close.values.astype(float); a = f.atr.values.astype(float)
        fwd = (np.r_[c[H:], np.full(H, np.nan)] - c) / a
        dev = per == "DEV"
        ok = dev & np.r_[dev[H:], np.zeros(H, bool)] & np.isfinite(fwd) & ~np.asarray(f.roll.values, bool)
        ys.append(fwd[ok])
        for k in COMP:
            xs[k].append(S[k][ok])
    y = np.concatenate(ys); w = {}
    for k in COMP:
        x = np.concatenate(xs[k]); m = np.isfinite(x) & np.isfinite(y)
        w[k] = float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman")) if m.sum() > 200 and np.nanstd(x[m]) > 0 else 0.0
    tot = sum(abs(v) for v in w.values() if np.isfinite(v)) or 1
    return {k: (v / tot if np.isfinite(v) else 0.0) for k, v in w.items()}


def run_model(fs, comps, w, theta, side, exitp):
    cache = {id(f): score(S, w) for f, S in zip(fs, comps)}

    def fn(f, side, extra=None, **kw):
        s = cache[id(f)]; p = np.r_[np.nan, s[:-1]]
        sig = (s >= theta) & ~(p >= theta) if side > 0 else (s <= -theta) & ~(p <= -theta)
        return dict(sig=np.nan_to_num(sig, nan=0).astype(bool), warm=60, entry="open")
    return E7.run(fs, fn, {}, exitp, side, extra=None)


def row(T):
    out = {}
    for P in ("DEV", "VALID"):
        x = T[T.period == P] if len(T) else T
        m1, m2 = E7.metrics(x, "r1", B=1000), E7.metrics(x, "r2", B=1000)
        out.update({f"{P}_n": m1.get("n", 0), f"{P}_dates": m1.get("dates", 0), f"{P}_win": m1.get("win"), f"{P}_avg_win": m1.get("avg_win"),
                    f"{P}_avg_loss": m1.get("avg_loss"), f"{P}_exp1": m1.get("exp"), f"{P}_exp2": m2.get("exp"), f"{P}_pf": m1.get("pf"),
                    f"{P}_dd": m1.get("dd"), f"{P}_ci_lo": m1.get("ci_lo"), f"{P}_ci_hi": m1.get("ci_hi"), f"{P}_wo_top5": m2.get("wo_top5")})
    return out


def main():
    rows, weights = [], {}
    for mk, (load, exitp, H) in markets().items():
        fs = [f for f in load() if f is not None and len(f) > 80]
        comps = [components(f) for f in fs]
        fams = dict(FAMILIES)
        fams["data_driven"] = dev_ic(fs, comps, H)
        weights[mk] = fams["data_driven"]
        for c in COMP:                                            # individual indicators (single-weight models)
            fams[f"single_{c}"] = {c: 1.0}
        for name, w in fams.items():
            for side in (1, -1):
                for th in THETAS:
                    T = run_model(fs, comps, w, th, side, exitp)
                    rows.append(dict(market=mk, model=name, side="BUY" if side > 0 else "SELL", theta=th, **row(T)))
        # simple baseline: Donchian-20 close breakout (same exit)
        from research.mcxe007 import strat7 as S7
        for side in (1, -1):
            T = E7.run(fs, S7.dc, dict(n=20), exitp, side)
            rows.append(dict(market=mk, model="baseline_donchian20", side="BUY" if side > 0 else "SELL", theta=np.nan, **row(T)))
        print(mk, len(fs), "instruments done", flush=True)
        pd.DataFrame(rows).to_csv(OUT / "RESULTS.csv", index=False)
    (OUT / "results_weights.json").write_text(json.dumps(weights, indent=1))


if __name__ == "__main__":
    main()

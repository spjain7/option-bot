"""CRUDE-V1 (1-Nov-2026, owner: ChatGPT's "Crude Oil Research Model V1" – CVD/order flow, realized semivariance, KAMA,
volume profile / POC, Ehlers MESA – "do only for crude oil and find results").
Data: MCX CRUDEOIL near-month futures, 1-hour candles Jul-2022 → Oct-2026 (Angel), stitched at contract changes.
IMPORTANT – order flow: no tick history with buyer/seller side exists for MCX, so CVD here is a PROXY:
  bar delta = volume × (2·close − high − low) / (high − low)  (close-location volume); CVD = its running sum.
Tools (all from completed bars, no look-ahead):
  KAMA   Kaufman adaptive MA (ER 10, fast 2, slow 30) – trend up: close > KAMA and KAMA rising over 3 bars
  RSV    realized semivariance over the last 20 hours: RS+ = Σ r² (r>0), RS− = Σ r² (r<0); bullish when RS+ > RS−
  CVD    20-bar CVD slope > 0 (proxy buyers in control) / < 0
  POC    5-day (≈ 70 bars) volume profile from 1-hour bars (price bins of 0.25 ATR): POC = most-traded bin;
         'at POC' = the bar's low (BUY) / high (SELL) within 0.5 ATR of the POC
  MESA   Ehlers MAMA / FAMA (fast 0.5, slow 0.05): MAMA above FAMA = up
Strategies tested (entry next bar open, stop 2 ATR, 2R target and 1R, max 40 bars, 2x costs, one trade at a time):
  each tool alone (enter when it turns on, both sides) · model V1 = KAMA up + RS+ > RS− (regime) → pull-back to POC (location)
  → CVD slope up (confirmation) [mirror for SELL] · V1 without each component · V1 + MESA.
  Also: each tool as a FILTER on the live MCX breakout rule applied to crude (3h BUY N=10 vol 1.5 2ATR/2R; SELL N=20).
python research/program/crude_v1.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"


def kama(c, n=10, fast=2, slow=30):
    c = np.asarray(c, float); out = np.full(len(c), np.nan)
    fsc, ssc = 2 / (fast + 1), 2 / (slow + 1)
    out[n] = c[n]
    for i in range(n + 1, len(c)):
        ch = abs(c[i] - c[i - n]); vol = np.abs(np.diff(c[i - n:i + 1])).sum()
        er = ch / vol if vol > 0 else 0
        sc = (er * (fsc - ssc) + ssc) ** 2
        out[i] = out[i - 1] + sc * (c[i] - out[i - 1])
    return out


def mama(price, fast=0.5, slow=0.05):
    """Ehlers MESA adaptive MA (MAMA) and following MA (FAMA)."""
    p = np.asarray(price, float); n = len(p)
    sm, dt, i1, q1, ji, jq, i2, q2, re, im, per, sp, ph, ma, fa = (np.zeros(n) for _ in range(15))
    for t in range(6, n):
        sm[t] = (4 * p[t] + 3 * p[t - 1] + 2 * p[t - 2] + p[t - 3]) / 10
        adj = 0.075 * per[t - 1] + 0.54
        dt[t] = (0.0962 * sm[t] + 0.5769 * sm[t - 2] - 0.5769 * sm[t - 4] - 0.0962 * sm[t - 6]) * adj
        q1[t] = (0.0962 * dt[t] + 0.5769 * dt[t - 2] - 0.5769 * dt[t - 4] - 0.0962 * dt[t - 6]) * adj
        i1[t] = dt[t - 3]
        ji[t] = (0.0962 * i1[t] + 0.5769 * i1[t - 2] - 0.5769 * i1[t - 4] - 0.0962 * i1[t - 6]) * adj
        jq[t] = (0.0962 * q1[t] + 0.5769 * q1[t - 2] - 0.5769 * q1[t - 4] - 0.0962 * q1[t - 6]) * adj
        i2[t] = i1[t] - jq[t]; q2[t] = q1[t] + ji[t]
        i2[t] = 0.2 * i2[t] + 0.8 * i2[t - 1]; q2[t] = 0.2 * q2[t] + 0.8 * q2[t - 1]
        re[t] = i2[t] * i2[t - 1] + q2[t] * q2[t - 1]; im[t] = i2[t] * q2[t - 1] - q2[t] * i2[t - 1]
        re[t] = 0.2 * re[t] + 0.8 * re[t - 1]; im[t] = 0.2 * im[t] + 0.8 * im[t - 1]
        pr = 2 * np.pi / np.arctan(im[t] / re[t]) if im[t] != 0 and re[t] != 0 else per[t - 1]
        pr = min(max(pr, 0.67 * per[t - 1] if per[t - 1] else pr, 6), 1.5 * per[t - 1] if per[t - 1] else 50, 50)
        per[t] = 0.2 * pr + 0.8 * per[t - 1]; sp[t] = 0.33 * per[t] + 0.67 * sp[t - 1]
        ph[t] = np.degrees(np.arctan(q1[t] / i1[t])) if i1[t] != 0 else ph[t - 1]
        dph = max(ph[t - 1] - ph[t], 1)
        a = max(min(fast / dph, fast), slow)
        ma[t] = a * p[t] + (1 - a) * (ma[t - 1] if ma[t - 1] else p[t])
        fa[t] = 0.5 * a * ma[t] + (1 - 0.5 * a) * (fa[t - 1] if fa[t - 1] else p[t])
    return ma, fa


def poc_dist(f, look=70, binf=0.25):
    h, l, c, v, a = (f[x].values.astype(float) for x in ("high", "low", "close", "volume", "atr"))
    poc = np.full(len(c), np.nan)
    for i in range(look, len(c)):
        if not a[i] > 0:
            continue
        b = binf * a[i]
        lo, hi = l[i - look:i].min(), h[i - look:i].max()
        nb = int((hi - lo) / b) + 1
        if nb < 2 or nb > 2000:
            continue
        hist = np.zeros(nb)
        mid = (h[i - look:i] + l[i - look:i]) / 2
        idx = np.clip(((mid - lo) / b).astype(int), 0, nb - 1)
        np.add.at(hist, idx, v[i - look:i])
        poc[i] = lo + (hist.argmax() + 0.5) * b
    return poc


def build():
    fr = EX.frames(("mi", "CRUDEOIL", "MCX"))
    f1, cost1 = [(f, c) for s, f, o, c in fr if s == "MCX 1h"][0]
    f1 = f1.reset_index(drop=True).copy(); f1["volume"] = f1["volume"].clip(lower=0)
    f = H.features(f1); f["switch"] = f1["switch"].values
    c, h, l, v = f.close.values, f.high.values, f.low.values, f.volume.values.astype(float)
    f["kama"] = kama(c)
    f["kama_up"] = (c > f.kama) & (f.kama > f.kama.shift(3)); f["kama_dn"] = (c < f.kama) & (f.kama < f.kama.shift(3))
    r = pd.Series(np.log(c)).diff().where(~f["switch"])
    rsp, rsn = (r.clip(lower=0) ** 2).rolling(20).sum(), (r.clip(upper=0) ** 2).rolling(20).sum()
    f["rs_bull"], f["rs_bear"] = (rsp > rsn).values, (rsn > rsp).values
    rng = np.where(h - l > 0, h - l, np.nan)
    delta = np.nan_to_num(v * (2 * c - h - l) / rng)
    cvd = pd.Series(delta).cumsum()
    f["cvd_up"], f["cvd_dn"] = (cvd - cvd.shift(20) > 0).values, (cvd - cvd.shift(20) < 0).values
    f["cvd_up3"], f["cvd_dn3"] = (cvd.diff(3) > 0).values, (cvd.diff(3) < 0).values
    poc = poc_dist(f)
    a = f.atr.values
    f["at_poc_b"] = np.abs(l - poc) <= 0.5 * a
    f["at_poc_s"] = np.abs(h - poc) <= 0.5 * a
    f["above_poc"], f["below_poc"] = c > poc, c < poc
    ma, fa = mama((h + l) / 2)
    f["mesa_up"], f["mesa_dn"] = ma > fa, ma < fa
    return f, cost1


def onset(x):
    x = np.asarray(x, bool)
    return x & ~np.r_[False, x[:-1]]


def run(f, cost, sig_b, sig_s, k=2.0, r=2.0, maxh=40, start=300):
    out = []
    for side, s in ((1, sig_b), (-1, sig_s)):
        if s is None:
            continue
        sig = np.where(np.asarray(s, bool), side, 0)
        for x in H.simulate(f, sig, side, k, r, maxh, 2.5, cost, start=start):
            if x["status"] == "trade":
                out.append(("BUY" if side > 0 else "SELL", x["time"], x["r2"]))
    return out


def summarise(rows):
    T = pd.DataFrame(rows, columns=["test", "target", "side", "time", "r2"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    K = ["test", "target", "side"]
    S = T.groupby(K).agg(n=("r2", "size"), win=("r2", lambda s: (s > 0).mean()), R=("r2", "mean"), totalR=("r2", "sum")) \
        .join(T.pivot_table(index=K, columns="split", values="r2", aggfunc="mean")[["train", "valid", "test"]])
    S["all3"] = (S[["train", "valid", "test"]] > 0).all(axis=1)
    return T, S


def main():
    f, cost = build()
    rows = []
    B = lambda *cols: np.logical_and.reduce([f[c].values.astype(bool) for c in cols])  # noqa: E731
    tests = {
        "KAMA alone (turns up/down)": (onset(B("kama_up")), onset(B("kama_dn"))),
        "Semivariance alone (RS+>RS− turns on)": (onset(B("rs_bull")), onset(B("rs_bear"))),
        "CVD proxy alone (20-bar slope flips)": (onset(B("cvd_up")), onset(B("cvd_dn"))),
        "MESA alone (MAMA/FAMA cross)": (onset(B("mesa_up")), onset(B("mesa_dn"))),
        "POC alone (touch POC from above/below)": (onset(B("at_poc_b", "above_poc")), onset(B("at_poc_s", "below_poc"))),
        "V1 full: KAMA+RSV → POC → CVD": (onset(B("kama_up", "rs_bull", "at_poc_b", "cvd_up3")), onset(B("kama_dn", "rs_bear", "at_poc_s", "cvd_dn3"))),
        "V1 without CVD": (onset(B("kama_up", "rs_bull", "at_poc_b")), onset(B("kama_dn", "rs_bear", "at_poc_s"))),
        "V1 without POC": (onset(B("kama_up", "rs_bull", "cvd_up3")), onset(B("kama_dn", "rs_bear", "cvd_dn3"))),
        "V1 without RSV": (onset(B("kama_up", "at_poc_b", "cvd_up3")), onset(B("kama_dn", "at_poc_s", "cvd_dn3"))),
        "V1 without KAMA": (onset(B("rs_bull", "at_poc_b", "cvd_up3")), onset(B("rs_bear", "at_poc_s", "cvd_dn3"))),
        "V1 + MESA": (onset(B("kama_up", "rs_bull", "at_poc_b", "cvd_up3", "mesa_up")),
                      onset(B("kama_dn", "rs_bear", "at_poc_s", "cvd_dn3", "mesa_dn"))),
    }
    for nm, (sb, ss) in tests.items():
        for r in (1.0, 2.0):
            rows += [(nm, f"{r:g}R") + x for x in run(f, cost, sb, ss, r=r)]
    # filters on the live-style breakout (1-hour bars aggregated logic kept simple: 1h N=20 high/low, vol 1.5x, EMA200)
    c = f.close.values
    up = (c > f.high.shift(1).rolling(20).max()) & (f.volx > 1.5) & (c > f.ema200)
    dn = (c < f.low.shift(1).rolling(20).min()) & (f.volx > 1.5) & (c < f.ema200)
    base = {"BRK base (1h, 20-bar, vol 1.5x)": (up.values, dn.values)}
    for fl_b, fl_s, nm in (("kama_up", "kama_dn", "KAMA"), ("rs_bull", "rs_bear", "RSV"), ("cvd_up", "cvd_dn", "CVD"),
                           ("mesa_up", "mesa_dn", "MESA"), ("above_poc", "below_poc", "POC side")):
        base[f"BRK + {nm}"] = (up.values & f[fl_b].values.astype(bool), dn.values & f[fl_s].values.astype(bool))
    for nm, (sb, ss) in base.items():
        rows += [(nm, "2R") + x for x in run(f, cost, sb, ss, r=2.0)]
    T, S = summarise(rows)
    T.to_csv(OUT / "crude_v1_trades.csv.gz", index=False)
    S.reset_index().to_csv(OUT / "crude_v1_summary.csv", index=False)
    pd.set_option("display.width", 230); pd.set_option("display.max_rows", 200)
    print(f"CRUDEOIL 1h bars {len(f):,} ({f.time.min():%Y-%m-%d} → {f.time.max():%Y-%m-%d})")
    print(S.round(3).to_string())


if __name__ == "__main__":
    main()

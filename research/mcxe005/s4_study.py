"""MCXE-005 S4 (live stock-futures OI breakout BUY/SELL, the strategy behind PETRONET / GLENMARK / TITAN) – research-only
baseline vs improvement variants inside the approved NSE futures window (point-in-time F&O bhavcopy, front month, daily OI
of the contract used; nothing older than the window start).

The production rule needs EMA200 on daily bars: inside a 1-year window only bars >= 204 can signal (from about Sep-2026),
so the EXACT rule is evaluable only at the end of the window. To study variants with DEV coverage a PROXY baseline with
EMA50 (everything else identical) is used and labelled as such – it is NOT the live rule.
Variants (each = proxy baseline + one change, judged on DEV + VALID against the identical baseline signal set):
  +ADX>=20 · RSI<75 · extension <= 1 ATR above the 20-day high · OI build-up >= 4 % · entry-zone check OFF (what the
  0.5-ATR no-chase cancellation costs or saves)
python research/mcxe005/s4_study.py -> results/s4_study.csv, results/s4_trades.csv.gz"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import cost_model as CM  # noqa: E402
from research.mcxe004 import window as W, register as RG  # noqa: E402
from research.mcxe005 import frames as FR, s4_research as R4  # noqa: E402

RES = ROOT / "research/mcxe005/results"


def main():
    frames = FR.fut_daily()
    rows, sig_count = [], {}
    for f in frames:
        if len(f) < 80:
            continue
        f = f.copy(); f["volume"] = f["volume"].astype(float)
        exp = pd.to_datetime(f["expiry"]).values
        for base_name, ema_n in (("S4_exact_EMA200", 200), ("S4_proxy_EMA50", 50)):
            sig, X = R4.signals_vectorised(f, ema_n=ema_n)
            sig = np.where(f["sig_ok"].values, sig, 0)
            variants = {"baseline": sig}
            if base_name == "S4_proxy_EMA50":
                ext = (f.close - np.where(sig > 0, X["hh"], X["ll"])).abs() / X["atr"]
                variants.update({"+ADX>=20": np.where(X["adx"] >= 20, sig, 0),
                                 "RSI<75 (BUY) / >25 (SELL)": np.where(((sig > 0) & (X["rsi"] < 75)) | ((sig < 0) & (X["rsi"] > 25)), sig, 0),
                                 "extension<=1ATR": np.where(ext <= 1.0, sig, 0),
                                 "OI>=4%": np.where(X["doi"] >= 0.04, sig, 0),
                                 "entry-zone check OFF": sig})
            for vname, s in variants.items():
                key = (base_name, vname)
                sig_count[key] = sig_count.get(key, 0) + int((s != 0).sum())
                tr = R4.simulate(f, s, CM.FUT_FRAC, expiry=exp, entry_check=(vname != "entry-zone check OFF"))
                for t in tr:
                    rows.append(dict(base=base_name, variant=vname, inst=f.attrs["name"], **{k: v for k, v in t.items() if k != "i"}))
    T = pd.DataFrame(rows)
    T["date"] = pd.to_datetime(T.date)
    T["period"] = W.period(T.date, "NSE_FUT")
    T.to_csv(RES / "s4_trades.csv.gz", index=False)
    out = []
    for (b, v), G in T.groupby(["base", "variant"]):
        tr = G[G.status == "trade"]
        rec = dict(base=b, variant=v, signals=sig_count[(b, v)], cancelled=int((G.status == "cancelled").sum()))
        for P in ("DEV", "VALID", "OOS"):
            x = tr[tr.period == P]
            m = RG.metrics(x.assign(date=x.date), "r1")
            m2 = RG.metrics(x.assign(date=x.date), "r2")
            rec.update({f"{P}_trades": m["trades"], f"{P}_dates": m["unique_dates"], f"{P}_win": m["win_rate"], f"{P}_exp1": m["expectancy_R"],
                        f"{P}_exp2": m2["expectancy_R"], f"{P}_pf": m["profit_factor"], f"{P}_maxdd": m["max_drawdown_R"], f"{P}_ci": m["ci95"],
                        f"{P}_buy": int((x.side > 0).sum()), f"{P}_sell": int((x.side < 0).sum()),
                        f"{P}_stop%": round(100 * x.why.isin(["stop", "stop-gap"]).mean(), 1) if len(x) else None})
        out.append(rec)
    S = pd.DataFrame(out)
    S.to_csv(RES / "s4_study.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)
    print(S[["base", "variant", "signals", "cancelled", "DEV_trades", "DEV_exp1", "VALID_trades", "VALID_exp1", "OOS_trades", "OOS_win", "OOS_exp1", "OOS_exp2", "OOS_ci"]].to_string(index=False))
    for b, v in [(r.base, r.variant) for r in S.itertuples()]:
        x = S[(S.base == b) & (S.variant == v)].iloc[0]
        st, why = RG.classify(dict(trades=x.OOS_trades, unique_dates=x.OOS_dates, expectancy_R=x.OOS_exp1, ci95=x.OOS_ci),
                              dict(expectancy_R=x.OOS_exp2), "positional", selection_overlaps_window=False, controls_run=False)
        with RG.Execution(script_id="MCXE005-s4_study", strategy_name=f"{b} · {v}", market="NSE futures positional",
                          instrument="point-in-time F&O stocks", timeframe="1d") as ex:
            ex.finish("INSUFFICIENT_DATA" if st == "INSUFFICIENT_DATA" else "COMPLETED", total_signals=int(x.signals),
                      rejected_signals=int(x.cancelled), rejection_reasons={"cancelled at next open (entry zone)": int(x.cancelled)},
                      executed_backtest_trades=int(x.DEV_trades + x.VALID_trades + x.OOS_trades), win_rate=x.OOS_win,
                      net_expectancy_R=x.OOS_exp1, profit_factor=x.OOS_pf, confidence_interval={"OOS_1x": x.OOS_ci},
                      sample_dates={"DEV": int(x.DEV_dates), "VALID": int(x.VALID_dates), "OOS": int(x.OOS_dates)},
                      validation_status=st, conclusion=why, artifact_paths=["research/mcxe005/results/s4_study.csv"])


if __name__ == "__main__":
    main()

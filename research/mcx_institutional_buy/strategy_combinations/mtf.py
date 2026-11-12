"""MODULE H – multi-timeframe configurations (HTF values only from COMPLETED HTF bars; see backtesting/context.map_htf).
EARLY   context: daily support (AT_DSUP or AT_WSUP on the daily chart) and/or 4h / 1h exhaustion (EXHAUST or RSI_OS)
        trigger: 15m / 30m sweep reclaim, divergence, reversal candle (with buy-stop above the candle high)
CONF    context: 4h or daily structure turning up (BOS_RECENT / HL_RECENT / TRANSITION / UPTREND)
        trigger: 1h break of the lower high (MS_BOS_LH) or 15m / 30m retest of the broken level (MS_BOS_RETEST, LHBREAK_RETEST)
Alternatives compared: same-timeframe-only trigger, 1h context instead of 4h / daily, daily context on 1h.
python -m research.mcx_institutional_buy.strategy_combinations.mtf -> reports/mtf.csv"""
import warnings
import numpy as np
import pandas as pd
from ..backtesting import runner as RN, context as CX
from . import run as CB

warnings.filterwarnings("ignore")

EARLY_TRIG = ["SWEEP_PDL_RECLAIM", "SWEEP_PDL_HIGHBO", "SWEEP_SWING_HIGHBO", "SWEEP_FBVWAP_HIGHBO", "DIV_ANY_REG_R3", "DIV_RSI14_REG_R3",
              "CANDLE_HAMMER_HIGHBO", "CANDLE_ENGULF_HIGHBO", "RSI14_CROSSUP25"]
CONF_TRIG = ["MS_BOS_LH", "MS_MSS_HL_BREAK_LH", "MS_BOS_RETEST", "SWEEP_PDL_LHBREAK_RETEST", "MS_VWAP_RECLAIM"]
CTX = {  # name -> list of (htf, condition) all required
    "NONE": [],
    "D_SUP": [("1d", "AT_DSUP")], "D_WSUP": [("1d", "AT_WSUP")],
    "D_SUP+4H_EXH": [("1d", "AT_DSUP"), ("4h", "EXHAUST")], "D_SUP+1H_EXH": [("1d", "AT_DSUP"), ("1h", "EXHAUST")],
    "D_SUP+1H_RSIOS": [("1d", "AT_DSUP"), ("1h", "RSI_OS")], "4H_RSIOS": [("4h", "RSI_OS")], "1H_RSIOS": [("1h", "RSI_OS")],
    "4H_BOS": [("4h", "BOS_RECENT")], "D_BOS": [("1d", "BOS_RECENT")], "4H_HL": [("4h", "HL_RECENT")],
    "D_TRANSITION": [("1d", "TRANSITION")], "D_UPTREND": [("1d", "UPTREND")], "4H_UPTREND": [("4h", "UPTREND")],
    "1H_BOS": [("1h", "BOS_RECENT")], "D_UPTREND+4H_BOS": [("1d", "UPTREND"), ("4h", "BOS_RECENT")],
}
PLAN = {"15m": (EARLY_TRIG + CONF_TRIG, list(CTX)), "30m": (EARLY_TRIG + CONF_TRIG, list(CTX)),
        "1h": (EARLY_TRIG + CONF_TRIG, [k for k in CTX if "1H" not in k])}
EXITS = ["2R", "3R", "TRAIL3ATR"]


def main():
    rows = []
    for tf, (trigs, ctxs) in PLAN.items():
        out = []
        for name in RN.universe(tf):
            F = RN.features(name, tf)
            H = {h: RN.features(name, h) for h in ("1h", "4h", "1d") if h != tf}
            maps = {}
            for cn in ctxs:
                m = np.ones(len(F["c"]), bool)
                for h, k in CTX[cn]:
                    if (h, k) not in maps:
                        maps[(h, k)] = np.nan_to_num(CX.map_htf(F, H[h], H[h]["COND"][k])) > 0
                    m &= maps[(h, k)]
                for tr in trigs:
                    if tr not in F["TRIG"]:
                        continue
                    s, st, el = F["TRIG"][tr][:3]
                    for ex in EXITS:
                        T, _ = RN.run_one(F, f"{tr}@{cn}", s & m, st, el, ex)
                        if len(T):
                            T["anchor"] = tr; out.append(T)
        T = pd.concat(out, ignore_index=True); T["period"] = RN.period_of(tf, T.entry)
        L = RN.table(T); L["anchor"] = L.rule.str.split("@").str[0]; L["context"] = L.rule.str.split("@").str[1]
        S1 = pd.read_csv(RN.REPORTS / f"stage1_{tf}.csv")
        L = CB.add_excess(L, S1); L["tf"] = tf
        rows.append(L)
        print(tf, "tests", len(L), "FINAL", int(L.FINAL_PASS.sum()), flush=True)
    L = pd.concat(rows, ignore_index=True)
    L.to_csv(RN.REPORTS / "mtf.csv", index=False)
    RN.experiment_record("MCXIB-MTF", "strategy_combinations.mtf", "15m/30m/1h", dict(contexts=list(CTX), triggers=EARLY_TRIG + CONF_TRIG), L)
    # does any context improve its trigger vs the same trigger without context? (TRAIN-selected, then VAL / OOS)
    base = L[L.context == "NONE"].set_index(["tf", "anchor", "exit"])
    imp = []
    for _, r in L[L.context != "NONE"].iterrows():
        b = base.loc[(r.tf, r.anchor, r.exit)] if (r.tf, r.anchor, r.exit) in base.index else None
        if b is None:
            continue
        imp.append(dict(tf=r.tf, anchor=r.anchor, context=r.context, exit=r.exit,
                        **{f"{p}_n": r[f"{p}_n"] for p in ("TRAIN", "VAL", "OOS")},
                        **{f"{p}_gain": round(r[f"{p}_R"] - b[f"{p}_R"], 3) for p in ("TRAIN", "VAL", "OOS")}))
    I = pd.DataFrame(imp)
    I["gain_all3"] = (I.TRAIN_gain > 0) & (I.VAL_gain > 0) & (I.OOS_gain > 0) & (I.OOS_n >= 30)
    I.to_csv(RN.REPORTS / "mtf_context_gain.csv", index=False)
    print(I.groupby(["tf", "context"]).gain_all3.mean().unstack(0).round(2).to_string())


if __name__ == "__main__":
    main()


def trades(tf, rule, ex):
    """regenerate the trades of one MTF rule 'TRIGGER@CONTEXT' (for validation)."""
    tr, cn = rule.split("@")
    out = []
    for name in RN.universe(tf):
        F = RN.features(name, tf)
        m = np.ones(len(F["c"]), bool)
        for h, k in CTX[cn]:
            H = RN.features(name, h)
            m &= np.nan_to_num(CX.map_htf(F, H, H["COND"][k])) > 0
        s, st, el = F["TRIG"][tr][:3]
        T, _ = RN.run_one(F, rule, s & m, st, el, ex)
        if len(T):
            out.append(T)
    T = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    if len(T):
        T["period"] = RN.period_of(tf, T.entry)
    return T

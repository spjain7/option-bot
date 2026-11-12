"""STAGES 2-5 – combinations, pre-registered hypotheses, score model, multi-timeframe configurations.
All selection uses TRAIN only:
  anchors     per family (EARLY / CONF), the rules whose best TRAIN exit beats the matched random baseline on TRAIN
              (n >= 30), top 12 by TRAIN excess R. Exit frozen to that TRAIN-best exit.
  conditions  pooled TRAIN trades of the anchors: conditions with lift >= +0.05R and >= 30 trades -> top 8.
  stage 2     anchor AND one condition          stage 3   anchor AND two of the top-6 conditions
  stage 4     anchor AND three of the top-4 conditions, plus the owner's pre-registered hypotheses A-J
  stage 5     logistic score on TRAIN trades (all anchors, every condition), keep the top 20 % (threshold set on TRAIN)
  MTF         15m / 30m triggers with 1h / 4h / 1d context (HTF values from COMPLETED HTF bars only)
Matched baseline: random every-10th-bar BUY with the same stop construction and the same exit (open-entry rules) or
the same buy-stop-above-the-bar-high entry (HIGHBO rules). A result counts only if it beats its baseline in every period.
python -m research.mcx_institutional_buy.strategy_combinations.run [tf ...] -> reports/combos_<tf>.csv"""
import itertools
import sys
import warnings
import numpy as np
import pandas as pd
from ..backtesting import runner as RN, context as CX, metrics as M, data as D

warnings.filterwarnings("ignore")
P3 = ("TRAIN", "VAL", "OOS")


def baseline_of(rule):
    return "BASE_RANDOM10_HIGHBO" if "HIGHBO" in rule else "BASE_RANDOM_EVERY10_SAMESTOP"


def add_excess(L, S1):
    b = S1.set_index(["rule", "exit"])
    for p in P3:
        L[f"{p}_base_R"] = [b[f"{p}_R"].get((baseline_of(a), e), np.nan) for a, e in zip(L.anchor if "anchor" in L else L.rule, L.exit)]
        L[f"{p}_excess"] = L[f"{p}_R"] - L[f"{p}_base_R"]
    L["BEATS_BASELINE_ALL3"] = np.all([L[f"{p}_excess"] > 0 for p in P3], axis=0)
    L["FINAL_PASS"] = L.OOS_PASS & L.BEATS_BASELINE_ALL3
    return L


def anchors(S1):
    S1 = S1[~S1.rule.str.startswith("BASE")].copy()
    S1 = add_excess(S1.assign(anchor=S1.rule), pd.read_csv(RN.REPORTS / f"stage1_{S1.tf.iloc[0]}.csv"))
    S1 = S1[(S1.TRAIN_n >= 30) & (S1.TRAIN_excess > 0)]
    best = S1.sort_values("TRAIN_excess", ascending=False).groupby("rule").head(1)
    out = []
    for fam in ("EARLY", "CONF"):
        out.append(best[best.family == fam].head(12))
    return pd.concat(out)[["rule", "exit", "family", "module", "TRAIN_R", "TRAIN_excess"]]


def _trig(F, rule, mask):
    s, st, el = F["TRIG"][rule][:3]
    return s & np.asarray(mask, bool), st, el


def run_combos(tf, combos, label):
    """combos: list of (combo_name, anchor_rule, exit, [cond names]) -> table."""
    out = []
    for name in RN.universe(tf):
        F = RN.features(name, tf)
        if F is None:
            continue
        for cname, rule, ex, conds in combos:
            if rule not in F["TRIG"]:
                continue
            m = np.ones(len(F["c"]), bool)
            ok = True
            for k in conds:
                if callable(k):
                    m &= np.asarray(k(F), bool)
                elif k in F["COND"]:
                    m &= F["COND"][k]
                else:
                    ok = False
            if not ok:
                continue
            T, _ = RN.run_one(F, cname, *_trig(F, rule, m), ex)
            if len(T):
                T["anchor"] = rule
                out.append(T)
    if not out:
        return pd.DataFrame(), pd.DataFrame()
    T = pd.concat(out, ignore_index=True); T["period"] = RN.period_of(tf, T.entry)
    L = RN.table(T, by=("tf", "rule", "exit"))
    L["anchor"] = L.rule.map(dict(zip([c[0] for c in combos], [c[1] for c in combos])))
    L["stage"] = label
    return L, T


PREREG = {  # owner's examples A-J (section 12), fixed definitions, no tuning
    "A_RSIOS_SWEEP": [("SWEEP_PDL_RECLAIM", ["RSI_OS"]), ("SWEEP_SWING_RECLAIM", ["RSI_OS"])],
    "B_DIV_WEEKLYSUP": [("DIV_ANY_REG_R3", ["AT_WSUP"])],
    "C_VOLEXH_OIDECLINE": [("VOL_EXHAUST_BULLBAR", ["OI_H3_PDN_VDN_OIDN"])],
    "D_ABSORBPROXY_VWAP": [("MS_VWAP_RECLAIM", ["LOWIMPACT_PROXY"])],
    "E_SWEEP_DIV_VOL": [("SWEEP_PDL_RECLAIM", ["DIV_RECENT", "RVOL15"]), ("SWEEP_SWING_RECLAIM", ["DIV_RECENT", "RVOL15"])],
    "F_SUP_ABSORB_BOS": [("MS_BOS_LH", ["AT_DSUP", "LOWIMPACT_PROXY"])],
    "G_DIV_GLOBALREV": [("DIV_ANY_REG_R3", ["GLB_REV"])],
    "H_SWEEP_ABSORB_VWAP_HL": [("MS_VWAP_RECLAIM", ["SWEPT_RECENT", "LOWIMPACT_PROXY", "HL_RECENT"])],
    "I_RSIOS_BULLCANDLE_BOS": [("MS_BOS_LH", ["RSI_OS", "BULL_CANDLE"])],
    "J_TRANSITION_VOL": [("MS_MSS_HL_BREAK_LH", ["TRANSITION", "RVOL15"])],
}


def main(tfs):
    for tf in tfs:
        S1 = pd.read_csv(RN.REPORTS / f"stage1_{tf}.csv")
        A = anchors(S1)
        A.to_csv(RN.REPORTS / f"anchors_{tf}.csv", index=False)
        # condition lift on TRAIN trades of the anchors
        tr = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet")
        key = set(zip(A.rule, A.exit))
        tr = tr[[k in key for k in zip(tr.rule, tr.exit)]]
        tr = CX.attach(tr, tf)
        cc = [c for c in tr.columns if c.startswith("c_") and not c.endswith("_KNOWN")]
        LIFT = CX.cond_lift(tr, cc); LIFT.to_csv(RN.REPORTS / f"cond_lift_{tf}.csv", index=False)
        good = LIFT[(LIFT.TRAIN_lift >= 0.05) & (LIFT.TRAIN_n_with >= 30)].sort_values("TRAIN_lift", ascending=False).condition.tolist()[:8]
        combos2 = [(f"{a}&{c}", a, e, [c]) for a, e in zip(A.rule, A.exit) for c in good]
        combos3 = [(f"{a}&{c1}&{c2}", a, e, [c1, c2]) for a, e in zip(A.rule, A.exit) for c1, c2 in itertools.combinations(good[:6], 2)]
        combos4 = [(f"{a}&{'&'.join(cs)}", a, e, list(cs)) for a, e in zip(A.rule, A.exit) for cs in itertools.combinations(good[:4], 3)]
        pre = []
        S1i = S1.set_index(["rule", "exit"])
        for hname, items in PREREG.items():
            for rule, conds in items:
                for ex in ("2R", "3R", "TRAIL3ATR", "STRUCT_SWING"):
                    pre.append((f"{hname}|{rule}&{'&'.join(conds)}", rule, ex, conds))
        tabs = []
        for lab, cb in (("S2", combos2), ("S3", combos3), ("S4", combos4), ("PREREG", pre)):
            L, _ = run_combos(tf, cb, lab)
            if len(L):
                tabs.append(L)
            print(tf, lab, len(cb), "combos", flush=True)
        L = pd.concat(tabs, ignore_index=True) if tabs else pd.DataFrame()
        # anchors alone, for the comparison
        A0 = S1.merge(A[["rule", "exit"]], on=["rule", "exit"]).assign(anchor=lambda x: x.rule, stage="S1_anchor")
        L = pd.concat([A0, L], ignore_index=True)
        L = add_excess(L, S1)
        L["p_train"] = [M.p_from_t(x) for x in L.TRAIN_t_day]
        L["FDR10_train"] = M.bh(L.p_train.values, 0.10)
        L.to_csv(RN.REPORTS / f"combos_{tf}.csv", index=False)
        RN.experiment_record(f"MCXIB-COMBO-{tf}", "strategy_combinations", tf, dict(conditions=good, anchors=len(A)),
                             L.rename(columns={}), extra=dict(final_pass=int(L.FINAL_PASS.sum())))
        print(tf, "tests", len(L), "OOS_PASS", int(L.OOS_PASS.sum()), "FINAL_PASS (beats baseline all 3)", int(L.FINAL_PASS.sum()),
              "conditions", good, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or RN.TFS)

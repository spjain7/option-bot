"""STAGE 1 – every individual trigger x every exit x every timeframe, BUY only, costs included.
python -m research.mcx_institutional_buy.backtesting.stage1 [tf ...]
  -> reports/stage1_<tf>.csv (one row per rule x exit) and research/data/mcxib_cache/trades_stage1_<tf>.parquet"""
import sys
import time
import warnings
import numpy as np
import pandas as pd
from . import runner as RN, data as D

warnings.filterwarnings("ignore")


def main(tfs):
    for tf in tfs:
        t0 = time.time()
        T, rej = RN.run(tf)
        meta = {}
        F0 = RN.features(RN.universe(tf)[0], tf)
        for k, v in F0["TRIG"].items():
            meta[k] = (v[3], v[4])
        L = RN.table(T)
        L["family"] = L.rule.map(lambda r: meta.get(r, ("?", "?"))[0]); L["module"] = L.rule.map(lambda r: meta.get(r, ("?", "?"))[1])
        L["rejected_low_rr_or_risk"] = [rej.get((r, e), 0) for r, e in zip(L.rule, L.exit)]
        L.to_csv(RN.REPORTS / f"stage1_{tf}.csv", index=False)
        T.to_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", index=False)
        RN.experiment_record(f"MCXIB-S1-{tf}", "backtesting.stage1", tf, dict(rules=int(L.rule.nunique()), exits=list(RN.EXITS)), L,
                             extra=dict(trades=int(len(T))))
        print(f"{tf}: {len(L)} tests, {len(T)} trades, TRAIN pass {int(L.TRAIN_PASS.sum())}, VAL pass {int(L.VAL_PASS.sum())}, "
              f"OOS pass {int(L.OOS_PASS.sum())}  ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or RN.TFS)

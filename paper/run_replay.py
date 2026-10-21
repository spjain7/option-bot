"""Historical REPLAY of the paper engine (same code path as live paper) -> paper/reports/.

  python -m paper.run_replay            # needs research/data/angel (see research/README.md)

Replays the out-of-sample window (from 2021-08-08) on Angel's unadjusted front-month series - what the live
engine would actually see - for long/short and long-only, at 0.25%, 0.5% and 1% risk per trade.
This is a replay of history, NOT forward paper trading.
"""
import copy, json
from pathlib import Path
import pandas as pd
from research import roll_adjust as RA
from paper import mcx_daily as P

OUT = Path(__file__).resolve().parent / "reports"
START = "2021-08-08"


def main():
    base_cfg = copy.deepcopy(P.CFG)
    fr = {n: RA.load_mcx(n, adjusted=False)[0][["time", "open", "high", "low", "close", "volume"]] for n in base_cfg["instruments"]}
    rows, samples = [], {}
    for sides, sl in (((1, -1), "long_short"), ((1,), "long_only")):
        for rp in (0.0025, 0.005, 0.01):
            P.CFG.clear(); P.CFG.update(copy.deepcopy(base_cfg))
            P.CFG.update(sides=sides, risk_pct=rp, max_open_risk_pct=4 * rp, group_risk_pct=2 * rp)
            label = f"replay_{sl}_risk{rp * 100:g}"
            book, eng = P.replay(fr, START, sides=sides, state_dir=OUT / "state" / label)
            res = P.report(book, OUT, label)
            rows.append(dict(variant=sl, risk_per_trade_pct=rp * 100, **{k: v for k, v in res.items()
                                                                          if not isinstance(v, dict)},
                             alerts_by_state=json.dumps(res.get("alerts_by_state", {}))))
            for a in eng.alerts:
                samples.setdefault(a["state"], a["text"])
                for b in a.get("blocks") or []:                       # one example per kind of block
                    kind = "NO TRADE – " + ("RSI rule" if "RSI" in b else "chase" if "chase" in b else
                                            "risk/size" if "risks more" in b else "exposure" if "exceed" in b or "max" in b
                                            else "data" if "data" in b else "other")
                    samples.setdefault(kind, a["text"])
            print(label, {k: res.get(k) for k in ("closed_trades", "net_pnl_rs", "return_pct", "max_dd_pct", "avg_R")}, flush=True)
    P.CFG.clear(); P.CFG.update(base_cfg)
    pd.DataFrame(rows).to_csv(OUT / "replay_summary.csv", index=False)
    (OUT / "SAMPLE_ALERTS.md").write_text("# Sample paper alerts (from the replay)\n\n" + "\n\n".join(
        f"## {k}\n```\n{v}\n```" for k, v in samples.items()) + "\n")


if __name__ == "__main__":
    main()

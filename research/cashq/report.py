"""Leaderboard + category reports from results/*_leaderboard.csv.  python -m research.cashq.report"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "results"
COLS = ["exp_id", "status", "n_all", "DEV_n", "DEV_avgR", "VALID_n", "VALID_avgR", "VALID_PF", "OOS_n", "OOS_win", "OOS_avgR", "OOS_grossR",
        "OOS_costR", "OOS_PF", "OOS_lo95", "OOS_maxDD_R", "OOS_max_consec_loss", "OOS_hold", "OOS_per_day", "OOS_top5_share", "OOS_q"]


def load():
    L = []
    for f, kind in (("daily_leaderboard.csv", "positional/swing (daily)"), ("intra_leaderboard.csv", "intraday"), ("oi_leaderboard.csv", "F&O OI (daily)"), ("weekly_leaderboard.csv", "positional (weekly)")):
        p = OUT / f
        if p.exists():
            d = pd.read_csv(p); d["engine"] = kind
            fix = ~d["exp_id"].astype(str).str.endswith("R")
            d.loc[fix, "exp_id"] = d.loc[fix, "exp_id"] + "-" + d.loc[fix, "R"].map(lambda r: f"{r:g}R")
            L.append(d)
    L = pd.concat(L, ignore_index=True)
    L["n_all"] = L[["DEV_n", "VALID_n", "OOS_n"]].fillna(0).sum(axis=1).astype(int)
    return L


def table(d, k=12):
    c = [x for x in COLS if x in d.columns]
    d = d.sort_values(["VALID_avgR"], ascending=False).head(k)
    return d[c].to_markdown(index=False, floatfmt=".3f") if len(d) else "_none_"


def main():
    L = load()
    L.to_csv(OUT / "LEADERBOARD.csv", index=False)
    md = ["# CASHQ – NSE cash-equity research leaderboard", "",
          f"Variants: **{len(L)}** · completed trades (all splits, all variants): **{int(L['n_all'].sum()):,}**", "",
          "Status counts: " + ", ".join(f"{k} {v}" for k, v in L["status"].value_counts().items()), "",
          "Protocol: SELECTED only if DEV and VALID both positive after costs (VALID PF ≥ 1.1, n ≥ 50 each); the OOS then decides "
          "(PASS = OOS n ≥ 100, mean R > 0 with day-block bootstrap 95 % lower bound > 0, PF ≥ 1.30, top-5 stocks < 50 % of profit, "
          "BH-FDR q < 0.10 among the selected). Sorted by VALID (never by OOS).", ""]
    cats = [("1. Best intraday", L["engine"] == "intraday"),
            ("2. Best positional / swing (daily + weekly)", L["engine"].str.startswith("positional")),
            ("3. Best divergence", L["family"] == "DIVERGENCE"),
            ("4. Best RSI reversal", L["family"] == "RSI"),
            ("5. Best volume", L["family"] == "VOLUME"),
            ("6. Best price action", L["family"] == "PRICE_ACTION"),
            ("7. Best combined / confluence", L["family"] == "COMBINED"),
            ("7b. Positional trend", L["family"] == "POSITIONAL"),
            ("7c. F&O open interest", L["family"] == "OPEN_INTEREST")]
    for title, m in cats:
        d = L[m]
        md += [f"## {title} ({len(d)} variants; selected {int((d.status != 'NOT_SELECTED').sum())}, PASS {int((d.status == 'PASS').sum())})", "",
               table(d[d.status != "NOT_SELECTED"]) if (d.status != "NOT_SELECTED").any() else "_no variant was positive in both DEV and VALID_", ""]
    md += ["## 8. Failed strategies – reasons", ""]
    f = L.copy()
    f["reason"] = np.select([f["status"] == "NOT_SELECTED", f["status"] == "INSUFFICIENT_EVIDENCE", f["status"] == "FAIL_OOS"],
                            ["negative after costs in DEV and/or VALID", "too few OOS trades", "selected but failed OOS"], "")
    g = f.groupby(["engine", "family", "status"]).agg(variants=("exp_id", "size"), mean_DEV_R=("DEV_avgR", "mean"),
                                                       mean_gross_R=("DEV_grossR", "mean"), mean_cost_R=("DEV_costR", "mean")).reset_index()
    md += [g.to_markdown(index=False, floatfmt=".3f"), ""]
    (OUT / "REPORT.md").write_text("\n".join(md))
    print("\n".join(md[:8]))


if __name__ == "__main__":
    main()

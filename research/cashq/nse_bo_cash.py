"""CASH-ONLY view of the NSE breakout calls (owner 18-Nov-2026: "why are all calls F&O, no cash calls?").
Re-runs research/cashq/nse_bo_trades.py + bo_confirm.py with a LOWER liquidity floor (₹5 cr 60-day median turnover instead of
₹25 cr; price >= ₹50 and >= 250 sessions unchanged) so small / mid caps enter, then tags every call:
  segment   F&O / Cash-only (stock had / had no NSE stock futures on the signal date; F&O lists 2018+ from
            research/data/nse_fut_pit) / unknown (before 2018)
  liquidity ₹25 cr+ (the old universe) or ₹5-25 cr (new, smaller stocks), by 60-day median turnover on the signal day
Confirmed setups re-applied with the same fixed thresholds as before:
  M_ATH_C1  ext200 <= 30 % and 20-day return <= 5 %      M_ATH_C2  ADX >= 30 and ext200 <= 20 %
  W_MARU_C  ATR% <= 2.5 % and weekly all-time high the same day
python -m research.cashq.nse_bo_cash [cm_pickle] -> results/cash5/{nse_bo_trades.json, bo_confirm_trades.csv.gz, calls_tagged.json}"""
import glob
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D  # noqa: E402

D.MIN_TURNOVER = 5e7
if len(sys.argv) > 1:
    D.CM_PKL = Path(sys.argv[1])
from research.cashq import nse_bo_tf as T, nse_bo_trades as NT, bo_confirm as BC  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "cash5"
IDX = {"BANKNIFTY", "NIFTYNXT50", "NIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYFPI"}


def fo_by_month():
    """{YYYY-MM: set of symbols with stock futures that month} from the point-in-time futures bhavcopies (2018+)."""
    M = {}
    for p in sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz"))):
        m = Path(p).name[:4] + "-" + Path(p).name[4:6]
        if m not in M:
            M[m] = set(pd.read_csv(p, usecols=["symbol"]).symbol.astype(str)) - IDX
    return M


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    T.OUT = OUT; BC.OUT = OUT
    NT.main()
    BC.main()
    X = pd.read_csv(OUT / "bo_confirm_trades.csv.gz")
    conf = {"M_ATH_C1": ("M_ATH", "Monthly ATH + not extended + no run-up (confirmed)", (X.ext200 <= .30) & (X.ret20 <= .05)),
            "M_ATH_C2": ("M_ATH", "Monthly ATH + ADX>=30 + not extended (confirmed)", (X.adx >= 30) & (X.ext200 <= .20)),
            "W_MARU_C": ("W_MARU", "Weekly strong-candle + calm + weekly ATH (confirmed)", (X.vol_pct <= .025) & (X.wk_ath.astype(str) == "True"))}
    allr = json.loads((OUT / "nse_bo_trades.json").read_text())
    R = pd.DataFrame(allr["rows"])
    to = X.set_index("id").to_cr
    extra = []
    for cid, (base, label, m) in conf.items():
        S = X[m.fillna(False) & (X.setup_id == base)].copy()
        S["id"] = cid + "_" + S["id"].astype(str); S["setup_id"] = cid; S["setup"] = label
        extra.append(S[R.columns])
    R = pd.concat([R] + extra, ignore_index=True)
    # turnover on the signal day for every call (open calls are not in bo_confirm_trades -> recompute from the panel)
    W = D.daily_panel(); c, v = W["close"].astype("float64"), W["volume"].astype("float64")
    to_cr = (c * v).rolling(60, min_periods=40).median().shift(1) / 1e7
    key_of = {s: k for k, s in W["symbol"].items()}
    idx = c.index
    def turn(sym, d):
        k = key_of.get(sym); d = pd.Timestamp(d)
        if k is None:
            return None
        i = idx.searchsorted(d, side="right") - 1
        x = to_cr[k].iloc[i]
        return None if pd.isna(x) else float(x)
    R["turnover_cr"] = [round(t, 1) if t is not None else None for t in (turn(s, d) for s, d in zip(R.symbol, R.signal_date))]
    R["liquidity"] = ["₹25 cr+" if (t or 0) >= 25 else "₹5-25 cr" for t in R.turnover_cr]
    FO = fo_by_month(); first = min(FO)
    def seg(sym, d):
        m = str(d)[:7]
        if m < first:
            return "unknown (pre-2018)"
        s = FO.get(m) or FO[max(k for k in FO if k <= m)]
        return "F&O" if sym in s else "Cash-only"
    R["segment"] = [seg(s, d) for s, d in zip(R.symbol, R.signal_date)]
    R = R.astype(object).where(R.notna(), None)
    meta = allr["meta"] + [{"label": "Universe (18-Nov, v4)", "value": "₹5 cr+ 60-day median turnover (was ₹25 cr+), ≥ ₹50, ≥ 250 sessions. "
                            "Each call is tagged by liquidity band (₹25 cr+ = old universe, ₹5-25 cr = newly added smaller stocks) and by segment "
                            "(F&O if NSE stock futures existed in that month, else Cash-only; unknown before 2018)."}]
    (OUT / "calls_tagged.json").write_text(json.dumps(dict(rows=R.to_dict("records"), meta=meta), allow_nan=False, default=str))
    C = R[R.status == "closed"].copy(); C["win"] = C.pnl_100 > 0
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(C.groupby(["setup_id", "segment", "liquidity"]).agg(n=("id", "size"), win=("win", lambda x: round(100 * x.mean(), 1)),
                                                             avg_pct=("pnl_pct", lambda x: round(x.mean(), 2))).to_string())
    for p in ("2005-14", "2015-19", "2020-26"):
        G = C[(C.period == p) & (C.liquidity == "₹5-25 cr")]
        print(p, "₹5-25 cr", G.groupby("setup_id").agg(n=("id", "size"), win=("win", lambda x: round(100 * x.mean(), 1)),
                                                       avg=("pnl_pct", lambda x: round(x.mean(), 2))).to_dict("index"))


if __name__ == "__main__":
    main()

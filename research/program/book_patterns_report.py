"""Summary of BOOK-PAT-001 (book_patterns.py). PASS = average R > 0 and above the random baseline (same side, target)
in all three periods, with >= 30 trades in each.   python research/program/book_patterns_report.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
OUT = ROOT / "research/program/results"
CLAIM = {"Ascending triangle": 83, "Descending triangle": 87, "Symmetric triangle (break up)": 81, "Symmetric triangle (break down)": 62,
         "Bull flag": 85, "Bear flag": 50, "Pennant (up)": 46, "Pennant (down)": 46, "Ascending channel (break up)": 73,
         "Descending channel (break down)": 73, "Bearish rectangle": 78, "Bullish rectangle": 78, "Double top": 75, "Double bottom": 89,
         "Head & shoulders": 81, "Inverse head & shoulders": 89, "Rising wedge (break down)": 81, "Rising wedge (break up)": 51,
         "Falling wedge (break up)": 81, "Falling wedge (break down)": 51}


def per(T):
    t = pd.to_datetime(T.t)
    p = np.where(T.seg == "STK 1d", np.where(t < "2017-01-01", "P1", np.where(t < "2022-01-01", "P2", "P3")),
                 np.where(T.seg == "STK 1h", np.where(t < "2025-04-01", "P1", np.where(t < "2025-11-01", "P2", "P3")),
                          np.where(t < "2024-01-01", "P1", np.where(t < "2025-04-01", "P2", "P3"))))
    return p


def main():
    T = pd.read_parquet(OUT / "book_patterns_trades.parquet")
    T["per"] = per(T)
    base = T[T.kind == "base"].groupby(["seg", "side", "tgt", "per"]).R.mean()
    baseall = T[T.kind == "base"].groupby(["seg", "side", "tgt"]).agg(bn=("R", "size"), bwin=("R", lambda x: (x > 0).mean() * 100), bR=("R", "mean"))
    rows = []
    for (seg, kind, pat, ctx, tgt), g in T[T.kind != "base"].groupby(["seg", "kind", "pat", "ctx", "tgt"]):
        side = int(g.side.iat[0])
        r = dict(seg=seg, kind=kind, pat=pat, ctx=ctx, side="BUY" if side > 0 else "SELL", tgt=tgt, n=len(g),
                 win=round(100 * (g.R > 0).mean(), 1), R=round(g.R.mean(), 3), claim=CLAIM.get(pat) if kind == "chart" else None)
        b = baseall.loc[(seg, side, tgt if tgt != "book" else "1R")]
        r["base_win"], r["base_R"] = round(b.bwin, 1), round(b.bR, 3)
        ok = True
        for p in ("P1", "P2", "P3"):
            h = g[g.per == p]; r[p + "n"] = len(h); r[p + "R"] = round(h.R.mean(), 3) if len(h) else None
            bb = base.get((seg, side, tgt if tgt != "book" else "1R", p), 0)
            ok &= len(h) >= 30 and h.R.mean() > 0 and h.R.mean() > bb
        r["PASS"] = ok
        rows.append(r)
    S = pd.DataFrame(rows)
    S.to_csv(OUT / "book_patterns_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print("BASELINE\n", baseall.round(3).to_string())
    print("\nPASS\n", S[S.PASS].sort_values("R", ascending=False).to_string(index=False))
    for seg in ("STK 1d", "STK 1h", "MCX 1d"):
        x = S[(S.seg == seg) & ((S.kind == "chart") & (S.tgt == "book") | (S.kind == "candle") & (S.ctx == "book") & (S.tgt == "1R"))]
        print(f"\n{seg}\n", x[["kind", "pat", "side", "tgt", "n", "win", "claim", "R", "base_R", "P1R", "P2R", "P3R", "PASS"]].sort_values(["kind", "R"]).to_string(index=False))


if __name__ == "__main__":
    main()

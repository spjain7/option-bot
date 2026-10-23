"""RESEARCH ONLY (no alerts, no orders): would BUYING options on the selling bot's own calls have worked?

For every closed single-leg sell call in state/state.json:
  * the bot's direction is kept: "Single PE Sell" (bullish) -> BUY an at-the-money CE; "Single CE Sell" (bearish) -> BUY an ATM PE;
  * entry at the same time and underlying price as the sell call; the underlying's real path comes from Angel One candles;
  * the option is priced with Black-76 at the IV recorded on the sell call (IV kept constant: a MODEL estimate, real buyers
    usually also lose some IV after events, so real results would be a little worse);
  * buyer costs: bid-ask spread on both sides + ₹40 brokerage per lot + ~0.1% taxes on the sell value.
Two exit versions: (A) exit when the sell call exited; (B) buyer rules: +50% target / -30% stop on 15-min closes, else (A).
Also shown, exactly: buying the SAME option the bot sold = the opposite of the bot's real P&L.
Usage (GitHub Actions, needs the Angel secrets): python -m research.buy_check > report.md
"""
import json, math, sys
from pathlib import Path
import pandas as pd
import config as C
import greeks as G
import market as M
from angel import Angel, load_master

ROOT = Path(__file__).resolve().parents[1]
SPREAD = {"index": 0.005, "stock": 0.015, "mcx": 0.01}      # each side, share of the premium
BROKER_LOT, TAX = 40.0, 0.001
EXP_T = {"NFO": (15, 30), "BFO": (15, 30), "MCX": (23, 30)}


def kind(c):
    return "mcx" if c["exch"] == "MCX" else "index" if c["name"] in C.INDEX_TOKENS else "stock"


def years(ts, expiry, exch):
    h, m = EXP_T.get(exch, (15, 30))
    e = pd.Timestamp(expiry).normalize() + pd.Timedelta(hours=h, minutes=m)
    return max((e - ts).total_seconds() / 60, 1) / M.MIN_PER_YEAR


def underlying(api, master, c, cache):
    """15-min candles of the underlying from entry to exit, scaled so the first price = spot_at_entry."""
    t0, t1 = pd.Timestamp(c["opened"]), pd.Timestamp(c["closed"])
    if c["exch"] == "MCX":
        cands = [("MCX", c.get("fut_token"))]
        nf = M.near_future(master, c["name"], "MCX")
        if nf is not None:
            cands.append(("MCX", str(nf["token"])))                       # expired contract -> current one (same moves)
    else:
        cands = [(M.spot_seg(c["name"]), M.spot_token(master, c["name"]))]
    for ex, tok in cands:
        if not tok:
            continue
        key = (ex, tok)
        if key not in cache:
            cache[key] = api.candles(ex, tok, "FIFTEEN_MINUTE", pd.Timestamp("2026-09-15"), pd.Timestamp.now() + pd.Timedelta(days=1))
        df = cache[key]
        if df is None or df.empty:
            continue
        seg = df[(df["time"] >= t0 - pd.Timedelta(minutes=15)) & (df["time"] <= t1)]
        if len(seg) < 2:
            continue
        scale = c["spot_at_entry"] / float(seg.iloc[0]["close"])
        return [(row.time + pd.Timedelta(minutes=15), float(row.close) * scale) for row in seg.itertuples()]
    return None


def simulate(c, path):
    typ = "CE" if c["strategy"] == "Single PE Sell" else "PE"
    s0, t0, iv = c["spot_at_entry"], pd.Timestamp(c["opened"]), c["legs"][0]["iv"] / 100
    k = kind(c)
    if not iv or iv <= 0:
        return None
    px = lambda S, t: G.price(S, s0, years(t, c["expiry"], c["exch"]), iv, C.RISK_FREE, typ)
    p0 = px(s0, t0) * (1 + SPREAD[k])
    if p0 <= 0:
        return None
    lot = c["lot"]
    def pnl(v):
        sell = v * (1 - SPREAD[k])
        return (sell - p0) * lot - BROKER_LOT - TAX * sell * lot
    end_t, end_s = path[-1]
    a = pnl(px(end_s, end_t))
    b = None
    for t, s in path:
        if t <= t0:
            continue
        v = px(s, t)
        if v >= 1.5 * p0 or v <= 0.7 * p0:
            b = pnl(v); break
    if b is None:
        b = a
    move = (end_s / s0 - 1) * 100 * (1 if typ == "CE" else -1)
    # model check on the option the bot really sold: model exit price vs the real recorded exit price
    leg = c["legs"][0]
    m_exit = G.price(end_s, leg["K"], years(end_t, c["expiry"], c["exch"]), iv, C.RISK_FREE, leg["typ"])
    m_entry = G.price(s0, leg["K"], years(t0, c["expiry"], c["exch"]), iv, C.RISK_FREE, leg["typ"])
    return {"ret": b / (p0 * lot) * 100, "t0": t0, "m_chg": m_exit - m_entry, "real_chg": c["exit_value"] - leg["entry"], "lot_prem": p0 * lot,
            "id": c["id"], "name": c["name"], "kind": k, "mode": c["mode"], "typ": typ, "premium": p0, "A": a, "B": b,
            "dir_ok": move > 0, "move_pct": move, "sell_pnl": c["pnl_rs_per_lot"], "sell_exit": c["exit_reason"]}


def stats(xs):
    if not xs:
        return "0 trades"
    w = [x for x in xs if x > 0]; l = [x for x in xs if x <= 0]
    pf = sum(w) / abs(sum(l)) if l and sum(l) else float("inf")
    return (f"{len(xs)} trades | win {len(w) / len(xs) * 100:.0f}% | net ₹{sum(xs):,.0f}/lot | avg win ₹{(sum(w) / len(w) if w else 0):,.0f} "
            f"| avg loss ₹{(sum(l) / len(l) if l else 0):,.0f} | profit factor {pf:.2f} | per trade ₹{sum(xs) / len(xs):,.0f}")


def main():
    st = json.loads((ROOT / "state" / "state.json").read_text())
    closed = [c for c in st["closed"] if c["strategy"] in ("Single PE Sell", "Single CE Sell") and c.get("spot_at_entry")]
    api, master, cache = Angel(), load_master(), {}
    rows, skipped = [], 0
    for c in closed:
        try:
            path = underlying(api, master, c, cache)
            r = simulate(c, path) if path else None
        except Exception as e:  # noqa: BLE001
            print("skip", c["id"], e, file=sys.stderr); r = None
        if r: rows.append(r)
        else: skipped += 1
    sold = [c["pnl_rs_per_lot"] for c in closed]
    L = ["# Option BUYING on the selling bot's calls (research estimate)", "",
         f"Calls checked: {len(rows)} of {len(closed)} closed single-leg sell calls ({skipped} skipped: no underlying candles). "
         f"Period {closed[0]['opened'][:10]} to {closed[-1]['closed'][:10]}. Per 1 lot, after costs. Model prices (Black-76, IV fixed at the sell call's IV).", "",
         "## Results", "",
         f"- **The selling bot itself (real records):** {stats(sold)}",
         f"- **Buying the same option the bot sold (exact mirror):** about the opposite: net ₹{-sum(sold):,.0f}/lot before extra buyer costs.",
         f"- **Buy ATM in the bot's direction, exit with the sell call (A):** {stats([r['A'] for r in rows])}",
         f"- **Buy ATM in the bot's direction, +50% target / -30% stop (B):** {stats([r['B'] for r in rows])}",
         f"- **Direction right by the exit time:** {sum(r['dir_ok'] for r in rows)} of {len(rows)} ({sum(r['dir_ok'] for r in rows) / max(len(rows), 1) * 100:.0f}%)", "",
         "## By type (version B)", ""]
    for key, lab in (("kind", "Market"), ("mode", "Call type")):
        for v in sorted({r[key] for r in rows}):
            L.append(f"- {lab} {v}: {stats([r['B'] for r in rows if r[key] == v])}")
    L += ["", "## By how the sell call ended (version B)", ""]
    for v in sorted({r["sell_exit"] for r in rows}):
        L.append(f"- Sell exit {v}: {stats([r['B'] for r in rows if r['sell_exit'] == v])}")
    rows.sort(key=lambda r: r["t0"])
    half = len(rows) // 2
    top = sorted(rows, key=lambda r: r["B"], reverse=True)
    agree = sum((r["m_chg"] > 0) == (r["real_chg"] > 0) for r in rows)
    err = sorted(abs(r["m_chg"] - r["real_chg"]) / max(abs(r["real_chg"]), 1e-9) for r in rows)
    L += ["", "## Robustness (version B)", "",
          f"- First half of the calls: {stats([r['B'] for r in rows[:half]])}",
          f"- Second half of the calls: {stats([r['B'] for r in rows[half:]])}",
          f"- Without MCX: {stats([r['B'] for r in rows if r['kind'] != 'mcx'])}",
          f"- Without the 10 best trades: {stats([r['B'] for r in top[10:]])} (the 10 best made ₹{sum(r['B'] for r in top[:10]):,.0f})",
          f"- Average return on the premium paid: {sum(r['ret'] for r in rows) / len(rows):+.1f}% per trade; median premium per lot ₹{sorted(r['lot_prem'] for r in rows)[len(rows)//2]:,.0f}",
          f"- Model check on the options the bot really sold: model and real price moved the same way in {agree} of {len(rows)} trades; "
          f"median size error {err[len(err)//2] * 100:.0f}%", ""]
    for name in sorted({r["name"] for r in rows if r["kind"] == "mcx"}):
        L.append(f"- {name}: {stats([r['B'] for r in rows if r['name'] == name])}")
    L += ["", "Notes: a model estimate on one month of calls, not a guarantee. Selling wins when the market stays still or moves "
          "slowly; buying needs a fast move in the right direction before time decay eats the premium.", ""]
    print("\n".join(L))


if __name__ == "__main__":
    main()

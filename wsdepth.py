"""Best-5 market depth from the Angel WebSocket – recorded for research only (owner 11-Nov: "verify whether 5-level or
20-level depth is genuinely available ... if available, start persisting live depth data for future research").

Facts this is built on (checked 11-Nov-2026):
  * SmartAPI announced the 20-level depth feed (WebSocket mode 4) deprecated from 25-Apr-2025; "best 5-depth will continue
    to be available for all users". smartapi-python 1.5.5 still has the mode-4 parser but caps it at 50 tokens.
  * Best-5 depth arrives inside the SNAP_QUOTE packets the collector ALREADY subscribes to (fields best_5_buy_data /
    best_5_sell_data: price, quantity, no of orders). So recording it costs no extra login, connection or API request.
  * The SDK assigns the packets by a flag and then swaps the two lists (smartWebSocketV2.py: best_5_buy_data =
    parsed "sell"). Which side is the bid is therefore NOT assumed here: both lists are stored as sent (side "A" =
    SDK best_5_buy_data, side "B" = SDK best_5_sell_data) and the daily diagnostics count, per exchange, how often
    A1 < B1 (A is the bid) versus A1 > B1. Research reads the sides from those counts.

Recorded: one snapshot per token per minute (the first packet of each minute) -> .cache/ws/depth_<YYYYMMDD>.csv, plus
depth_status.json (per exchange: packets, packets with depth, filled levels, A1<B1 / A1>B1 / crossed / one-sided counts,
exchange-timestamp lag). A packet without depth fields is counted, never filled in. Times IST. No orders, no REST calls.
"""
import json
from pathlib import Path
import pandas as pd

LEVELS = 5
COLS = (["time", "recv", "exch", "token", "ltp", "ltq", "tbq", "tsq"] +
        [f"{s}{i}{k}" for s in ("A", "B") for i in range(1, LEVELS + 1) for k in ("p", "q", "o")])


def _lv(x, i):
    try:
        d = x[i]
        return d.get("price", 0) / 100.0, d.get("quantity", 0), d.get("no of orders", d.get("num_of_orders", 0))
    except Exception:
        return 0.0, 0, 0


class Recorder:
    def __init__(self, d):
        self.d = Path(d); self.d.mkdir(parents=True, exist_ok=True)
        self.last_min, self.buf, self.diag = {}, [], {}

    def _dg(self, ex):
        return self.diag.setdefault(ex, dict(packets=0, with_depth=0, rows=0, levels={}, a_below_b=0, a_above_b=0, equal=0,
                                             one_sided=0, empty=0, lag_s_max=0.0, lag_s_sum=0.0, lag_n=0))

    def on_msg(self, msg, ex, t, recv):
        """msg: parsed SNAP_QUOTE packet · ex: 'NFO' / 'MCX' / 'NSE' · t: exchange time (IST, naive) · recv: local IST."""
        g = self._dg(ex); g["packets"] += 1
        A, B = msg.get("best_5_buy_data"), msg.get("best_5_sell_data")
        if A is None and B is None:
            return False
        g["with_depth"] += 1
        lag = (pd.Timestamp(recv) - pd.Timestamp(t)).total_seconds()
        g["lag_s_max"] = max(g["lag_s_max"], lag); g["lag_s_sum"] += lag; g["lag_n"] += 1
        tok = str(msg.get("token")); m = pd.Timestamp(t).floor("min")
        if self.last_min.get(tok) == m:
            return False
        self.last_min[tok] = m
        A, B = A or [], B or []
        nA = sum(1 for x in A if x.get("price")); nB = sum(1 for x in B if x.get("price"))
        k = f"{nA}x{nB}"; g["levels"][k] = g["levels"].get(k, 0) + 1
        a1, b1 = _lv(A, 0)[0], _lv(B, 0)[0]
        if not nA and not nB:
            g["empty"] += 1
        elif not nA or not nB:
            g["one_sided"] += 1
        elif a1 < b1:
            g["a_below_b"] += 1
        elif a1 > b1:
            g["a_above_b"] += 1
        else:
            g["equal"] += 1
        row = [f"{pd.Timestamp(t):%Y-%m-%d %H:%M:%S}", f"{pd.Timestamp(recv):%H:%M:%S}", ex, tok,
               (msg.get("last_traded_price") or 0) / 100.0, msg.get("last_traded_quantity", ""),
               msg.get("total_buy_quantity", ""), msg.get("total_sell_quantity", "")]
        for side in (A, B):
            for i in range(LEVELS):
                row.extend(_lv(side, i))
        self.buf.append(row); g["rows"] += 1
        return True

    def flush(self, day):
        if self.buf:
            f = self.d / f"depth_{pd.Timestamp(day):%Y%m%d}.csv"
            new = not f.exists()
            with open(f, "a") as fh:
                if new:
                    fh.write(",".join(COLS) + "\n")
                for r in self.buf:
                    fh.write(",".join("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)) for v in r) + "\n")
            self.buf = []
        out = {}
        for ex, g in self.diag.items():
            out[ex] = dict(g, lag_s_mean=round(g["lag_s_sum"] / g["lag_n"], 2) if g["lag_n"] else None)
            out[ex].pop("lag_s_sum", None)
        p = self.d / "depth_status.tmp"
        p.write_text(json.dumps(out, default=str)); p.replace(self.d / "depth_status.json")
        return out


def export(out, d):
    """all depth_<day>.csv of the folder -> one gzip CSV for the ws-depth branch; returns rows (0 = nothing)."""
    parts = [pd.read_csv(p, dtype={"token": str}) for p in sorted(Path(d).glob("depth_*.csv")) if p.stat().st_size > 0]
    if not parts:
        return 0
    df = pd.concat(parts, ignore_index=True)
    if df.empty:
        return 0
    try:
        info = pd.read_csv(Path(d) / "tokens.csv", dtype=str)[["token", "name", "symbol"]].drop_duplicates("token")
        df = df.merge(info, on="token", how="left")
    except Exception:
        pass
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, compression="gzip")
    st = Path(d) / "depth_status.json"
    if st.exists():
        Path(str(out).replace(".csv.gz", "_status.json")).write_text(st.read_text())
    return len(df)

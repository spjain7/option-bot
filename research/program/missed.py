"""MISSED-001 – which big MCX moves did the live engine call, which did it miss, and why (owner directive H).

Big move = daily zig-zag swing of at least SWING_ATR × ATR(14) (close to close), 2022-08 .. 2026-10, 7 commodities, both
directions. A rule "caught" a move if it signalled in the move's direction between the swing start and the moment half
the move was done (so an entry at the next open still had >= half the move ahead). For caught moves the realistic trade
is simulated with the rule's own stop / target / time exit (entry next open, stop first, 2x costs).
Live rules use the PRODUCTION code (alerts/rulebook.py raw + filters) on the research candles (day-anchored 1h/2h/4h).
Misses are classified; then every signal family in rulebook.raw (no filter, both sides) is checked: would it have been
early on the missed moves – and what is its precision on ALL its signals (so this is not cherry-picking).
python research/program/missed.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MAIN = Path("/home/claude/ob-main")
import importlib.util  # noqa: E402
import types  # noqa: E402
import alerts as _al  # noqa: E402
for _m in ("tradeplan", "report", "signals"):                # stubs: only raw/features/daily_trend_map are used here
    if not hasattr(_al, _m):
        sys.modules[f"alerts.{_m}"] = types.ModuleType(_m); setattr(_al, _m, sys.modules[f"alerts.{_m}"])
_sp = importlib.util.spec_from_file_location("rulebook_main", MAIN / "alerts/rulebook.py")   # production code, main branch
RB = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(RB)
from research.program import rsix as RX  # noqa: E402
from research import instruments as INS  # noqa: E402

OUT = ROOT / "research/program/results"
SWING_ATR = 6.0
START = pd.Timestamp("2022-08-01")
# live MCX rules = rulebook MCX rules + the engine's own MCX rules written in rulebook terms
LIVE = {rid: r for rid, r in RB.RULES.items() if r["mkt"] == "MCX" and r["status"] == "LIVE"}
LIVE["BO_1d_MCX (20d high, ADX>=25)"] = dict(tf="1d", fam="BO", par="N20 vol0", filt="ADX25", side="BUY", k=1.5, r=2.0, maxh=20, mode="next_open")
LIVE["FH_MCX_4h (10-candle high, vol 1.5x, daily up)"] = dict(tf="4h", fam="BO", par="N10 vol1.5", filt="DT", side="BUY", k=2.0, r=3.0, maxh=40, mode="next_open")
FAMS = [("BO", "N10 vol0"), ("BO", "N20 vol0"), ("BO", "N55 vol0"), ("PB", "EMA20/50"), ("NR7", ""), ("RSIREV", "30/70"),
        ("RSICONT", "70/30"), ("RSIDIV", ""), ("MACD", "zero"), ("MACD", "signal"), ("ST", ""), ("EMAX", "9/21"), ("EMAX", "20/50"),
        ("INSIDE", ""), ("PIN", ""), ("MOMO", ""), ("FAIL", ""), ("RETEST", ""), ("SQZ", ""), ("RSIX", "7/30")]


def swings(d, k=SWING_ATR):
    """zig-zag on closes with an ATR threshold -> list of (i0, i1, dir)."""
    c = d.close.values; a = RB.features(d)["atr"].values
    piv, dirn, ext = [0], 0, 0
    for i in range(1, len(c)):
        if not a[i] > 0:
            continue
        if (dirn == 1 and c[i] > c[ext]) or (dirn == -1 and c[i] < c[ext]):
            ext = i
        if dirn == 0:
            if c[i] - c[piv[-1]] >= k * a[i]:
                dirn, ext = 1, i
            elif c[piv[-1]] - c[i] >= k * a[i]:
                dirn, ext = -1, i
        elif dirn == 1 and c[ext] - c[i] >= k * a[i]:
            piv.append(ext); dirn, ext = -1, i
        elif dirn == -1 and c[i] - c[ext] >= k * a[i]:
            piv.append(ext); dirn, ext = 1, i
    piv.append(ext)
    return [(piv[j], piv[j + 1], 1 if c[piv[j + 1]] > c[piv[j]] else -1) for j in range(len(piv) - 1)]


def masks(f, fam, par, filt, side, dtr):
    ff = RB.features(f)
    b, s = RB.raw(ff, fam, par)
    m = (b if side > 0 else s).copy()
    if filt == "ADX25":
        m &= np.nan_to_num(ff["adx"].values) >= 25
    if filt.startswith("DT"):
        day = pd.to_datetime(f["time"]).dt.normalize()
        t = dtr.reindex(day.values).fillna(0).values if len(dtr) else np.zeros(len(f))
        m &= t == side
    return m, ff


def trade(f, ff, i, side, k, r, maxh, cost, stop_entry=False):
    o, h, l, c = (f[x].values for x in ("open", "high", "low", "close")); a = ff["atr"].values
    if i + 1 >= len(f):
        return np.nan, None
    if stop_entry:
        lvl, inv, j = h[i], l[i], None
        for t in range(i + 1, min(i + 4, len(f))):
            if o[t] < inv or (l[t] < inv and not h[t] > lvl):
                break
            if h[t] > lvl:
                j, e = t, max(lvl, o[t]); break
        if j is None:
            return np.nan, None
    else:
        j, e = i + 1, o[i + 1]
    st = e - side * k * a[i]; R = k * a[i]; tg = e + side * r * R
    for t in range(j, min(j + maxh + 1, len(f))):
        if (side > 0 and l[t] <= st) or (side < 0 and h[t] >= st):
            return (-R - 2 * cost) / R, t
        if (side > 0 and h[t] >= tg) or (side < 0 and l[t] <= tg):
            return (r * R - 2 * cost) / R, t
    t = min(j + maxh, len(f) - 1)
    return (side * (c[t] - e) - 2 * cost) / R, t


def main():
    rows, alt = [], []
    for name in RX.NAMES:
        fr = dict(RX.frames(name))
        d = fr["1d"].reset_index(drop=True)
        dtr = RB.daily_trend_map(d)
        cost = INS.cost_points(name, float(d.close.iloc[-1]), 1.0)
        sw = [s for s in swings(d) if d.time.iloc[s[0]] >= START]
        sig = {}
        for rid, ru in LIVE.items():
            f = fr[ru["tf"]].reset_index(drop=True)
            m, ff = masks(f, ru["fam"], ru["par"], ru["filt"], 1 if ru["side"] == "BUY" else -1, dtr)
            sig[rid] = (f, ff, m, ru)
        for i0, i1, dr in sw:
            t0, t1 = d.time.iloc[i0], d.time.iloc[i1]
            p0, p1 = d.close.iloc[i0], d.close.iloc[i1]
            half = p0 + 0.5 * (p1 - p0)
            seg = d.iloc[i0:i1 + 1]
            th = seg.time[(dr * (seg.close - half)) >= 0].iloc[0] + pd.Timedelta(hours=23, minutes=59)
            atr0 = RB.features(d)["atr"].iloc[i0]
            hit = []
            for rid, (f, ff, m, ru) in sig.items():
                s_ = 1 if ru["side"] == "BUY" else -1
                if s_ != dr:
                    continue
                tt = pd.to_datetime(f["time"])
                end_t = tt + pd.Timedelta(minutes={"1h": 60, "2h": 120, "4h": 240, "1d": 1440}[ru["tf"]])
                idx = np.flatnonzero(m & (end_t > t0).values & (end_t <= th).values)
                if len(idx):
                    R, _ = trade(f, ff, idx[0], s_, ru["k"], ru["r"], ru["maxh"], cost, ru.get("mode") == "stop")
                    hit.append((rid, str(tt.iloc[idx[0]])[:16], R))
            # why missed
            why = ""
            if not hit:
                if dr < 0:
                    why = "DOWN move – engine has no live MCX SELL rule (all MCX SELL failed research)"
                else:
                    t_prev = dtr.reindex([t0.normalize()]).fillna(0).iloc[0]
                    why = ("UP move started with the daily trend NOT up (reversal) – trend-filtered rules wait"
                           if t_prev != 1 else "UP move in a daily uptrend but no rule fired before half the move")
            rows.append(dict(name=name, dir="UP" if dr > 0 else "DOWN", start=str(t0.date()), end=str(t1.date()),
                             days=(t1 - t0).days, move_pct=round(100 * (p1 / p0 - 1), 1), move_atr=round(abs(p1 - p0) / atr0, 1),
                             caught=bool(hit), first=hit[0][0] if hit else "", first_time=hit[0][1] if hit else "",
                             first_R=round(hit[0][2], 2) if hit and hit[0][2] == hit[0][2] else np.nan,
                             n_rules=len(hit), why=why))
        # alternatives: every family, no filter, on 1d / 4h – early on which moves, and precision overall
        for tf in ("4h", "1d"):
            f = fr[tf].reset_index(drop=True); ff = RB.features(f); tt = pd.to_datetime(f["time"])
            ok_t = (tt >= START).values
            for fam, par in FAMS:
                b, s = RB.raw(ff, fam, par)
                for s_, m in ((1, b), (-1, s)):
                    idx = np.flatnonzero(m & ok_t)
                    if not len(idx):
                        continue
                    k_, r_, mh = (1.5, 3.0, 20 if tf == "1d" else 40)
                    Rs = [trade(f, ff, i, s_, k_, r_, mh, cost, fam == "RSIX")[0] for i in idx]
                    Rs = np.array([x for x in Rs if x == x])
                    early = 0
                    for i0, i1, dr in sw:
                        if dr != s_:
                            continue
                        t0 = d.time.iloc[i0]; p0, p1 = d.close.iloc[i0], d.close.iloc[i1]
                        seg = d.iloc[i0:i1 + 1]; half = p0 + 0.5 * (p1 - p0)
                        th = seg.time[(dr * (seg.close - half)) >= 0].iloc[0] + pd.Timedelta(hours=23, minutes=59)
                        early += bool(((tt > t0) & (tt <= th) & pd.Series(m)).any())
                    alt.append(dict(name=name, tf=tf, fam=f"{fam} {par}".strip(), side="BUY" if s_ > 0 else "SELL",
                                    signals=len(Rs), win=(Rs > 0).mean() * 100 if len(Rs) else np.nan,
                                    R=Rs.mean() if len(Rs) else np.nan, moves_early=early,
                                    moves=sum(1 for x in sw if x[2] == s_)))
        print(f"{name}: {len(sw)} big moves")
    M = pd.DataFrame(rows); A = pd.DataFrame(alt)
    M.to_csv(OUT / "missed_moves.csv", index=False); A.to_csv(OUT / "missed_alternatives.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 70)
    print(f"\nBig moves (≥ {SWING_ATR} ATR daily swing) since {START.date()}: {len(M)}")
    print(M.groupby("dir").agg(moves=("caught", "size"), caught=("caught", "sum"), avg_move_pct=("move_pct", "mean")).round(1))
    print("\nwhy missed:"); print(M[~M.caught].why.value_counts())
    print("\nper commodity:"); print(M.groupby(["name", "dir"]).caught.agg(["size", "sum"]).unstack())
    print("\nfirst rule to catch (count, mean R of the realistic trade):")
    print(M[M.caught].groupby("first").first_R.agg(["size", "mean"]).round(2).sort_values("size", ascending=False))
    g = A.groupby(["tf", "fam", "side"]).agg(signals=("signals", "sum"), R=("R", "mean"), win=("win", "mean"),
                                             early=("moves_early", "sum"), moves=("moves", "sum")).reset_index()
    g["early_%"] = 100 * g.early / g.moves; g["sig_per_move"] = g.signals / g.moves
    print("\nALTERNATIVES – share of big moves signalled early vs precision on ALL signals (1.5 ATR stop, 3R, 2x costs):")
    print(g.sort_values(["side", "early_%"], ascending=[True, False]).round(2).to_string(index=False))
    print("\nlist of missed moves:"); print(M[~M.caught][["name", "dir", "start", "end", "move_pct", "move_atr", "why"]].to_string(index=False))
    print("\ncaught moves:"); print(M[M.caught][["name", "dir", "start", "end", "move_pct", "first", "first_time", "first_R", "n_rules"]].to_string(index=False))


if __name__ == "__main__":
    main()

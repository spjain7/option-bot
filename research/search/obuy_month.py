"""OBUY-MONTH-001 – option BUYING setups on NSE index + stock futures, last month, with REAL option prices.
Research only: no alerts, no orders, live bot untouched.

Stage 1 (fetch, needs Angel secrets):  python -m research.search.obuy_month fetch
  * universe: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY + the 40 most active stock futures (today's OI x price)
  * current-month futures 15-min candles + 15-min OI from 20 Aug (warm-up) to the last full session
  * then, for every signal of every strategy, the ATM option of the current monthly expiry: its real 15-min candles
Stage 2 (analyse, offline):            python -m research.search.obuy_month analyse
Data is cached in research/data/obuy/ (saved to the research-obuy branch by the workflow).
"""
import json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "research" / "data" / "obuy"
OUT = ROOT / "research" / "search" / "results_obuy"
START, WARM = pd.Timestamp("2026-09-23"), pd.Timestamp("2026-08-20")
INDICES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
TOP_STOCKS = 40

# costs per round trip as a share of premium: bid-ask (each side) + STT 0.1% on the sell + exchange/GST ~0.06%
HALF_SPREAD = {"index": 0.003, "stock": 0.01, "mcx": 0.015}
FEES = 0.0016
BROKER_LOT = 40.0


# ─────────────── indicators (15-min bars, one symbol) ───────────────
def rsi(c, n=14):
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def features(df):
    """df: time, open, high, low, close, volume, oi (15-min, NSE session)."""
    df = df.copy()
    df["day"] = df["time"].dt.normalize()
    df["slot"] = df["time"].dt.strftime("%H:%M")
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (tp * df["volume"]).groupby(df["day"]).cumsum() / df["volume"].groupby(df["day"]).cumsum().replace(0, np.nan)
    df["rsi"] = rsi(df["close"])
    df["ema20"], df["ema50"] = df["close"].ewm(span=20, adjust=False).mean(), df["close"].ewm(span=50, adjust=False).mean()
    # relative volume vs the same slot over the previous 10 sessions
    df["relvol"] = df["volume"] / df.groupby("slot")["volume"].transform(lambda v: v.shift(1).rolling(10, min_periods=5).mean())
    df["dhi"] = df.groupby("day")["high"].cummax().groupby(df["day"]).shift(1)          # day high BEFORE this bar
    df["dlo"] = df.groupby("day")["low"].cummin().groupby(df["day"]).shift(1)
    first2 = df.groupby("day").head(2)
    orb = first2.groupby("day").agg(orh=("high", "max"), orl=("low", "min"))
    df = df.join(orb, on="day")
    df["bar_no"] = df.groupby("day").cumcount()
    df["oi_open"] = df.groupby("day")["oi"].transform("first")
    df["oi_1h"] = df["oi"] / df["oi"].shift(4) - 1
    df["px_1h"] = df["close"] / df["close"].shift(4) - 1
    df["oi_day"] = df["oi"] / df["oi_open"] - 1
    # 1-hour trend (EMA on hourly closes, carried to 15-min) and daily bars
    df["ema20h"], df["ema50h"] = df["close"].ewm(span=80, adjust=False).mean(), df["close"].ewm(span=200, adjust=False).mean()
    df["rsih"] = rsi(df["close"], 56)
    return df


def daily(df):
    g = df.groupby("day")
    d = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum"), oi=("oi", "last")).reset_index()
    d["hh20"], d["vol20"] = d["high"].rolling(20).max().shift(1), d["volume"].rolling(20).mean().shift(1)
    d["ll20"] = d["low"].rolling(20).min().shift(1)
    d["chg"], d["oichg"] = d["close"].pct_change(), d["oi"].pct_change()
    d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["rsi2"] = rsi(d["close"], 2)
    return d


# ─────────────── strategies → signals (bar index i = completed signal bar, dir ±1, kind) ───────────────
def intraday_signals(df, kind):
    S = {k: [] for k in ("I1_orb_oi", "I2_vwap_rsi_oi", "I3_dayhigh_vol_oi", "I4_rsi_ema_oi", "I5_coil_break", "I0_random")}
    rng = np.random.default_rng(abs(hash(kind + str(len(df)))) % 2**32)
    quiet = 0.0015 if kind == "index" else 0.004
    oi_min = 0.0075 if kind == "index" else 0.015
    used = set()
    for i in range(60, len(df) - 1):
        r, p = df.iloc[i], df.iloc[i - 1]
        if r["time"] < START or r["day"] != df.iloc[i + 1]["day"]:
            continue
        t = r["time"].strftime("%H:%M")
        if not ("09:30" <= t <= "14:30"):
            continue
        rv = r["relvol"] if np.isfinite(r["relvol"]) else 0
        oiu = r["oi_1h"] > 0 if np.isfinite(r["oi_1h"]) else False
        def add(k, d):
            key = (k, r["day"])
            if key not in used:
                used.add(key); S[k].append((i, d))
        if r["bar_no"] >= 2 and np.isfinite(r["orh"]):
            if r["close"] > r["orh"] and p["close"] <= r["orh"] and rv >= 1.5 and r["oi_day"] > 0:
                add("I1_orb_oi", 1)
            elif r["close"] < r["orl"] and p["close"] >= r["orl"] and rv >= 1.5 and r["oi_day"] > 0:
                add("I1_orb_oi", -1)
        if np.isfinite(r["vwap"]) and np.isfinite(p["vwap"]):
            if p["close"] <= p["vwap"] < r["close"] and r["rsi"] >= 60 and oiu and r["px_1h"] > 0:
                add("I2_vwap_rsi_oi", 1)
            elif p["close"] >= p["vwap"] > r["close"] and r["rsi"] <= 40 and oiu and r["px_1h"] < 0:
                add("I2_vwap_rsi_oi", -1)
        if t >= "10:15" and np.isfinite(r["dhi"]):
            if r["close"] > r["dhi"] and rv >= 2 and oiu:
                add("I3_dayhigh_vol_oi", 1)
            elif r["close"] < r["dlo"] and rv >= 2 and oiu:
                add("I3_dayhigh_vol_oi", -1)
        if p["rsi"] < 60 <= r["rsi"] and r["close"] > r["ema20"] > r["ema50"] and oiu:
            add("I4_rsi_ema_oi", 1)
        elif p["rsi"] > 40 >= r["rsi"] and r["close"] < r["ema20"] < r["ema50"] and oiu:
            add("I4_rsi_ema_oi", -1)
        w = df.iloc[i - 4:i]
        if len(w) == 4 and (w["high"].max() - w["low"].min()) / r["close"] <= quiet and w["oi"].iloc[-1] / w["oi"].iloc[0] - 1 >= oi_min and rv >= 1.5:
            if r["close"] > w["high"].max():
                add("I5_coil_break", 1)
            elif r["close"] < w["low"].min():
                add("I5_coil_break", -1)
        if rng.random() < 0.02:
            add("I0_random", int(rng.choice([-1, 1])))
    return S


def positional_signals(df, kind):
    d = daily(df)
    S = {k: [] for k in ("P1_daily_vol_breakout_oi", "P2_buildup_day", "P3_hourly_trend_rsi_oi", "P4_rsi2_pullback", "P0_random")}
    first_after = {}                                                # day -> index of the 9:30 bar (entry = next bar)
    for i, r in df.iterrows():
        if r["time"].strftime("%H:%M") == "09:15" and r["day"] not in first_after:
            first_after[r["day"]] = i
    days = list(d["day"])
    rng = np.random.default_rng(abs(hash("P" + kind + str(len(df)))) % 2**32)
    for j in range(1, len(d) - 1):
        r, nxt = d.iloc[j], days[j + 1]
        if nxt < START or nxt not in first_after:
            continue
        i = first_after[nxt]
        if np.isfinite(r["hh20"]) and r["volume"] > 1.5 * r["vol20"] and r["oichg"] > 0:
            if r["close"] > r["hh20"]:
                S["P1_daily_vol_breakout_oi"].append((i, 1))
            elif r["close"] < r["ll20"]:
                S["P1_daily_vol_breakout_oi"].append((i, -1))
        lim = (0.01, 0.03) if kind == "index" else (0.02, 0.05)
        if r["chg"] >= lim[0] and r["oichg"] >= lim[1]:
            S["P2_buildup_day"].append((i, 1))
        elif r["chg"] <= -lim[0] and r["oichg"] >= lim[1]:
            S["P2_buildup_day"].append((i, -1))
        if r["close"] > r["ema50"] and r["rsi2"] < 10:
            S["P4_rsi2_pullback"].append((i, 1))
        elif r["close"] < r["ema50"] and r["rsi2"] > 90:
            S["P4_rsi2_pullback"].append((i, -1))
        if rng.random() < 0.15:
            S["P0_random"].append((i, int(rng.choice([-1, 1]))))
    used = set()
    for i in range(200, len(df) - 1):
        r, p = df.iloc[i], df.iloc[i - 4]
        if r["time"] < START or not ("09:45" <= r["time"].strftime("%H:%M") <= "14:45") or r["day"] in used:
            continue
        if p["ema20h"] <= p["ema50h"] and r["ema20h"] > r["ema50h"] and r["rsih"] > 55 and r["oi_day"] > 0:
            S["P3_hourly_trend_rsi_oi"].append((i, 1)); used.add(r["day"])
        elif p["ema20h"] >= p["ema50h"] and r["ema20h"] < r["ema50h"] and r["rsih"] < 45 and r["oi_day"] > 0:
            S["P3_hourly_trend_rsi_oi"].append((i, -1)); used.add(r["day"])
    return S


# ─────────────── option simulation on REAL option candles ───────────────
EXITS = {  # name: (stop, target, trail_from, trail_to, max_days, intraday?)
    "intraday_sl30_t60": (0.30, 0.60, None, None, 0, True),
    "intraday_sl25_trail": (0.25, None, 0.40, 0.15, 0, True),
    "positional_sl35_t80_3d": (0.35, 0.80, None, None, 3, False),
    "positional_sl35_trail_3d": (0.35, None, 0.60, 0.25, 3, False),
}


def simulate(opt, t_entry, rule, lot, kind, cut_time="15:15"):
    """opt: option 15-min candles. Entry at the open of the bar starting at t_entry. Returns dict or None."""
    sl, tg, tf_, tt_, maxd, intra = EXITS[rule]
    o = opt[opt["time"] >= t_entry]
    if o.empty or o.iloc[0]["time"] - t_entry > pd.Timedelta(minutes=30) or o.iloc[0]["volume"] <= 0:
        return None                                                    # no trade in the option = illiquid, skipped
    e = float(o.iloc[0]["open"])
    if e <= 0.5:
        return None
    day0 = t_entry.normalize()
    sessions = sorted(o["time"].dt.normalize().unique())
    last_day = sessions[min(maxd, len(sessions) - 1)]
    peak, px, why = 0.0, None, "time"
    for r in o.itertuples():
        d = r.time.normalize()
        if d > last_day:
            break
        if r.low <= e * (1 - sl):
            px, why = min(r.open, e * (1 - sl)), "stop"; break
        if tg and r.high >= e * (1 + tg):
            px, why = max(r.open, e * (1 + tg)), "target"; break
        peak = max(peak, r.high / e - 1)
        if tf_ is not None and peak >= tf_ and r.close <= e * (1 + tt_):
            px, why = r.close, "trail"; break
        cut = cut_time if (intra or d == last_day) else None
        if cut and r.time.strftime("%H:%M") >= cut:
            px = r.close; break
        px = r.close
    if px is None:
        return None
    hs = HALF_SPREAD[kind]
    buy, sell = e * (1 + hs), px * (1 - hs)
    pnl_unit = sell - buy - FEES * sell
    rs = pnl_unit * lot - BROKER_LOT
    return {"entry_px": e, "exit_px": px, "ret": rs / (buy * lot), "rs_lot": rs, "why": why}


# ─────────────── stage 1: fetch ───────────────
def fetch():
    from angel import Angel, load_master
    import angel as A
    A.Angel.HIST_GAP = 1.0
    api, master = Angel(), load_master()
    DATA.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()
    end = today - pd.Timedelta(minutes=1)                               # last full session only
    fut = master[master["instrumenttype"].isin(["FUTIDX", "FUTSTK"]) & (master["exch_seg"] == "NFO") & (master["expiry_dt"] >= today)]
    near = fut.sort_values("expiry_dt").groupby("name").head(1)
    idx = near[near["name"].isin(INDICES)]
    stk = near[near["instrumenttype"] == "FUTSTK"]
    q = api.quotes({"NFO": list(stk["token"].astype(str))})
    act = sorted(((float(v.get("opnInterest") or 0) * float(v.get("ltp") or 0), k) for k, v in q.items()), reverse=True)[:TOP_STOCKS]
    keep = pd.concat([idx, stk[stk["token"].astype(str).isin({k for _, k in act})]])
    meta = []
    for r in keep.itertuples():
        f = DATA / f"fut_{r.name}.csv"
        if not f.exists():
            c = api.candles("NFO", r.token, "FIFTEEN_MINUTE", WARM, end)
            oi = api.oi_history("NFO", r.token, "FIFTEEN_MINUTE", WARM, end)
            if c is None or c.empty:
                print("no candles", r.name); continue
            c = c.merge(oi[["time", "oi"]], on="time", how="left") if oi is not None else c.assign(oi=np.nan)
            c.to_csv(f, index=False)
        meta.append({"name": r.name, "token": str(r.token), "expiry": str(r.expiry_dt.date()), "lot": int(r.lotsize),
                     "kind": "index" if r.name in INDICES else "stock"})
        print("fut", r.name, flush=True)
    (DATA / "meta.json").write_text(json.dumps(meta, indent=1))
    # option candles for every signal's ATM strike (current monthly expiry; if <= 2 days left, the next one)
    opts = master[master["instrumenttype"].isin(["OPTIDX", "OPTSTK"]) & (master["exch_seg"] == "NFO")].copy()
    opts["K"] = opts["strike"] / 100
    need = {}
    for m in meta:
        df = load_fut(m["name"])
        if df is None:
            continue
        for _, sigs in all_signals(df, m["kind"]).items():
            for i, d in sigs:
                row = df.iloc[i]
                tok = pick_option(opts, m["name"], row["close"], "CE" if d > 0 else "PE", row["time"])
                if tok:
                    need[tok[0]] = (*tok, m["name"])
    print("option series needed:", len(need), flush=True)
    for k, (tok, sym, *_rest) in need.items():
        f = DATA / f"opt_{sym}.csv"
        if f.exists():
            continue
        c = api.candles("NFO", tok, "FIFTEEN_MINUTE", START - pd.Timedelta(days=1), end)
        if c is not None and not c.empty:
            c.to_csv(f, index=False)
    (DATA / "options.json").write_text(json.dumps({k: list(v) for k, v in need.items()}, default=str))


def pick_option(opts, name, px, typ, t):
    o = opts[(opts["name"] == name) & (opts["symbol"].str.endswith(typ)) & (opts["expiry_dt"] >= t.normalize() + pd.Timedelta(days=3))]
    if o.empty:
        return None
    exp = o["expiry_dt"].min()
    o = o[o["expiry_dt"] == exp]
    r = o.iloc[(o["K"] - px).abs().argsort().iloc[0]]
    return (str(r["token"]), r["symbol"], float(r["K"]), str(exp.date()))


def load_fut(name):
    f = DATA / f"fut_{name}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, parse_dates=["time"])
    df = df[(df["time"].dt.strftime("%H:%M") >= "09:15") & (df["time"].dt.strftime("%H:%M") < "15:30")].reset_index(drop=True)
    return features(df)


def all_signals(df, kind):
    return {**intraday_signals(df, kind), **positional_signals(df, kind)}


# ─────────────── stage 2: analyse ───────────────
def analyse():
    meta = json.loads((DATA / "meta.json").read_text())
    master_like = pd.DataFrame([{"token": v[0], "symbol": v[1], "K": v[2], "expiry_dt": pd.Timestamp(v[3]), "name": v[4]}
                                for v in json.loads((DATA / "options.json").read_text()).values()])
    rows = []
    for m in meta:
        df = load_fut(m["name"])
        if df is None:
            continue
        ml = master_like[master_like["name"] == m["name"]]
        for strat, sigs in all_signals(df, m["kind"]).items():
            rules = [r for r in EXITS if EXITS[r][5]] if strat.startswith("I") else [r for r in EXITS if not EXITS[r][5]]
            for i, d in sigs:
                row, nxt = df.iloc[i], df.iloc[i + 1]
                pk = pick_option(ml, m["name"], row["close"], "CE" if d > 0 else "PE", row["time"]) if not ml.empty else None
                if not pk or not (DATA / f"opt_{pk[1]}.csv").exists():
                    continue
                opt = pd.read_csv(DATA / f"opt_{pk[1]}.csv", parse_dates=["time"])
                for rule in rules:
                    s = simulate(opt, nxt["time"], rule, m["lot"], m["kind"])
                    if s:
                        rows.append({"strategy": strat, "exit": rule, "name": m["name"], "kind": m["kind"], "time": row["time"],
                                     "dir": d, "option": pk[1], **s})
    T = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "trades.csv", index=False)
    mid = START + (T["time"].max() - START) / 2
    out = []
    for (s, e), g in T.groupby(["strategy", "exit"]):
        w = g[g.rs_lot > 0]; l = g[g.rs_lot <= 0]
        top = g.sort_values("ret", ascending=False)
        out.append(dict(strategy=s, exit=e, trades=len(g), days=g["time"].dt.normalize().nunique(), win=round(len(w) / len(g) * 100),
                        avg_ret=round(g.ret.mean() * 100, 1), med_ret=round(g.ret.median() * 100, 1),
                        net_rs_lot=round(g.rs_lot.sum()), pf=round(w.rs_lot.sum() / abs(l.rs_lot.sum()), 2) if len(l) and l.rs_lot.sum() else 99,
                        first_half=round(g[g.time < mid].ret.mean() * 100, 1), second_half=round(g[g.time >= mid].ret.mean() * 100, 1),
                        no_top5=round(top.ret.iloc[5:].mean() * 100, 1) if len(g) > 10 else None,
                        index_ret=round(g[g.kind == "index"].ret.mean() * 100, 1) if (g.kind == "index").any() else None,
                        stock_ret=round(g[g.kind == "stock"].ret.mean() * 100, 1) if (g.kind == "stock").any() else None,
                        calls=round(g[g.dir > 0].ret.mean() * 100, 1) if (g.dir > 0).any() else None,
                        puts=round(g[g.dir < 0].ret.mean() * 100, 1) if (g.dir < 0).any() else None))
    S = pd.DataFrame(out).sort_values("avg_ret", ascending=False)
    S.to_csv(OUT / "summary.csv", index=False)
    print(S.to_string(index=False))


if __name__ == "__main__":
    {"fetch": fetch, "analyse": analyse}[sys.argv[1]]()

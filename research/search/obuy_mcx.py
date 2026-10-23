"""OBUY-MCX-001 – option BUYING setups on MCX (Gold, Silver, Crude, Natural Gas, Copper), last month, REAL option prices.
Research only (no alerts). Same method as obuy_month.py (NSE), adapted to MCX:
  * MCX has NO open-interest history from Angel, so the OI conditions cannot be tested here: the setups are the NSE
    ones without OI (OI is only usable live).
  * Session 9:00-23:30; intraday entries 9:30-22:00, exit 23:00; positional exit at 23:00 on the 3rd session.
  * Option = ATM of the nearest LISTED expiry >= 3 days away (expired series cannot be downloaded, so early trades use a
    later expiry than a live trader would: conservative, more time value paid).
Stage 1: python -m research.search.obuy_mcx fetch   (Angel secrets)   Stage 2: python -m research.search.obuy_mcx analyse
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.search import obuy_month as RM  # noqa

DATA = ROOT / "research" / "data" / "obuy_mcx"
OUT = ROOT / "research" / "search" / "results_obuy_mcx"
NAMES = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER"]
START, WARM = RM.START, RM.WARM
RS_PT = {"CRUDEOIL": 100, "NATURALGAS": 1250, "GOLD": 100, "SILVER": 30, "COPPER": 2500}
EXIT = "23:00"


def intraday_signals(df):
    S = {k: [] for k in ("M1_vwap_rsi", "M2_orb_vol", "M3_dayhigh_vol", "M0_random")}
    rng, used = np.random.default_rng(len(df)), set()
    for i in range(60, len(df) - 1):
        r, p = df.iloc[i], df.iloc[i - 1]
        if r["time"] < START or r["day"] != df.iloc[i + 1]["day"]:
            continue
        t = r["time"].strftime("%H:%M")
        if not ("09:30" <= t <= "22:00"):
            continue
        rv = r["relvol"] if np.isfinite(r["relvol"]) else 0
        def add(k, d):
            if (k, r["day"]) not in used:
                used.add((k, r["day"])); S[k].append((i, d))
        if np.isfinite(r["vwap"]) and np.isfinite(p["vwap"]) and np.isfinite(r["px_1h"]):
            if p["close"] <= p["vwap"] < r["close"] and r["rsi"] >= 60 and r["px_1h"] > 0:
                add("M1_vwap_rsi", 1)
            elif p["close"] >= p["vwap"] > r["close"] and r["rsi"] <= 40 and r["px_1h"] < 0:
                add("M1_vwap_rsi", -1)
        if r["bar_no"] >= 2 and np.isfinite(r["orh"]) and rv >= 1.5:
            if r["close"] > r["orh"] and p["close"] <= r["orh"]:
                add("M2_orb_vol", 1)
            elif r["close"] < r["orl"] and p["close"] >= r["orl"]:
                add("M2_orb_vol", -1)
        if t >= "10:15" and np.isfinite(r["dhi"]) and rv >= 2:
            if r["close"] > r["dhi"]:
                add("M3_dayhigh_vol", 1)
            elif r["close"] < r["dlo"]:
                add("M3_dayhigh_vol", -1)
        if rng.random() < 0.01:
            add("M0_random", int(rng.choice([-1, 1])))
    return S


def positional_signals(df):
    d = RM.daily(df)
    S = {k: [] for k in ("MP1_daily_vol_breakout", "MP2_rsi2_pullback", "MP0_random")}
    first = {}
    for i, r in df.iterrows():
        if r["day"] not in first and r["time"].strftime("%H:%M") == "09:00":
            first[r["day"]] = i
    rng, days = np.random.default_rng(7 + len(df)), list(d["day"])
    for j in range(1, len(d) - 1):
        r, nxt = d.iloc[j], days[j + 1]
        if nxt < START or nxt not in first:
            continue
        i = first[nxt]
        if np.isfinite(r["hh20"]) and r["volume"] > 1.5 * r["vol20"]:
            if r["close"] > r["hh20"]:
                S["MP1_daily_vol_breakout"].append((i, 1))
            elif r["close"] < r["ll20"]:
                S["MP1_daily_vol_breakout"].append((i, -1))
        if r["close"] > r["ema50"] and r["rsi2"] < 10:
            S["MP2_rsi2_pullback"].append((i, 1))
        elif r["close"] < r["ema50"] and r["rsi2"] > 90:
            S["MP2_rsi2_pullback"].append((i, -1))
        if rng.random() < 0.15:
            S["MP0_random"].append((i, int(rng.choice([-1, 1]))))
    return S


def all_signals(df):
    return {**intraday_signals(df), **positional_signals(df)}


def load_fut(name):
    f = DATA / f"fut_{name}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, parse_dates=["time"])
    df = df[(df["time"].dt.strftime("%H:%M") >= "09:00") & (df["time"].dt.strftime("%H:%M") < "23:30")].reset_index(drop=True)
    if "oi" not in df:
        df["oi"] = np.nan
    return RM.features(df)


def pick_option(opts, name, px, typ, t):
    o = opts[(opts["name"] == name) & (opts["symbol"].str.endswith(typ)) & (opts["expiry_dt"] >= t.normalize() + pd.Timedelta(days=3))]
    if o.empty:
        return None
    o = o[o["expiry_dt"] == o["expiry_dt"].min()]
    r = o.iloc[(o["K"] - px).abs().argsort().iloc[0]]
    return (str(r["token"]), r["symbol"], float(r["K"]), str(pd.Timestamp(r["expiry_dt"]).date()), name)


def fetch():
    from angel import Angel, load_master
    import angel as A
    A.Angel.HIST_GAP = 1.2
    api, master = Angel(), load_master()
    DATA.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()
    end = today - pd.Timedelta(minutes=1)
    opts = master[(master["exch_seg"] == "MCX") & master["instrumenttype"].isin(["OPTFUT", "OPTCOM"])].copy()
    opts["K"] = opts["strike"] / 100
    meta = []
    for name in NAMES:
        fut = master[(master["exch_seg"] == "MCX") & (master["name"] == name) & (master["instrumenttype"] == "FUTCOM")
                     & (master["expiry_dt"] >= today)].sort_values("expiry_dt")
        oexp = opts[(opts["name"] == name) & (opts["expiry_dt"] >= today)]["expiry_dt"].min()
        if fut.empty or pd.isna(oexp):
            print("skip", name); continue
        f = fut[fut["expiry_dt"] >= oexp].iloc[0]                       # the future the nearest options are written on
        path = DATA / f"fut_{name}.csv"
        if not path.exists():
            c = api.candles("MCX", f["token"], "FIFTEEN_MINUTE", WARM, end)
            if c is None or c.empty:
                print("no candles", name); continue
            c.to_csv(path, index=False)
        meta.append({"name": name, "symbol": f["symbol"], "lot": RS_PT[name], "kind": "mcx"})
        print("fut", name, f["symbol"], flush=True)
    (DATA / "meta.json").write_text(json.dumps(meta, indent=1))
    need = {}
    for m in meta:
        df = load_fut(m["name"])
        for _, sigs in all_signals(df).items():
            for i, d in sigs:
                r = df.iloc[i]
                pk = pick_option(opts, m["name"], r["close"], "CE" if d > 0 else "PE", r["time"])
                if pk:
                    need[pk[0]] = pk
    print("option series needed:", len(need), flush=True)
    for tok, sym, *_ in need.values():
        path = DATA / f"opt_{sym}.csv"
        if not path.exists():
            c = api.candles("MCX", tok, "FIFTEEN_MINUTE", START - pd.Timedelta(days=1), end)
            if c is not None and not c.empty:
                c.to_csv(path, index=False)
    (DATA / "options.json").write_text(json.dumps(need, default=str))


def analyse():
    meta = json.loads((DATA / "meta.json").read_text())
    ml = pd.DataFrame([{"token": v[0], "symbol": v[1], "K": v[2], "expiry_dt": pd.Timestamp(v[3]), "name": v[4]}
                       for v in json.loads((DATA / "options.json").read_text()).values()])
    rows = []
    for m in meta:
        df = load_fut(m["name"])
        if df is None:
            continue
        mo = ml[ml["name"] == m["name"]]
        for strat, sigs in all_signals(df).items():
            intra = strat[1].isdigit()
            rules = ["intraday_sl30_t60", "intraday_sl25_trail"] if intra else ["positional_sl35_t80_3d", "positional_sl35_trail_3d"]
            for i, d in sigs:
                r, nxt = df.iloc[i], df.iloc[i + 1]
                pk = pick_option(mo, m["name"], r["close"], "CE" if d > 0 else "PE", r["time"]) if not mo.empty else None
                if not pk or not (DATA / f"opt_{pk[1]}.csv").exists():
                    continue
                opt = pd.read_csv(DATA / f"opt_{pk[1]}.csv", parse_dates=["time"])
                for rule in rules:
                    s = RM.simulate(opt, nxt["time"], rule, m["lot"], "mcx", EXIT)
                    if s:
                        rows.append({"strategy": strat, "exit": rule, "name": m["name"], "time": r["time"], "dir": d, "option": pk[1], **s})
    T = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "trades.csv", index=False)
    mid = START + (T["time"].max() - START) / 2
    out = []
    for (s, e), g in T.groupby(["strategy", "exit"]):
        w, l = g[g.rs_lot > 0], g[g.rs_lot <= 0]
        top = g.sort_values("ret", ascending=False)
        out.append(dict(strategy=s, exit=e, trades=len(g), win=round(len(w) / len(g) * 100), avg_ret=round(g.ret.mean() * 100, 1),
                        net_rs_lot=round(g.rs_lot.sum()), pf=round(w.rs_lot.sum() / abs(l.rs_lot.sum()), 2) if len(l) and l.rs_lot.sum() else 99,
                        first_half=round(g[g.time < mid].ret.mean() * 100, 1), second_half=round(g[g.time >= mid].ret.mean() * 100, 1),
                        no_top3=round(top.ret.iloc[3:].mean() * 100, 1) if len(g) > 6 else None,
                        calls=round(g[g.dir > 0].ret.mean() * 100, 1) if (g.dir > 0).any() else None,
                        puts=round(g[g.dir < 0].ret.mean() * 100, 1) if (g.dir < 0).any() else None,
                        **{n: round(g[g.name == n].ret.mean() * 100, 1) for n in NAMES if (g.name == n).any()}))
    S = pd.DataFrame(out).sort_values("avg_ret", ascending=False)
    S.to_csv(OUT / "summary.csv", index=False)
    print(S.to_string(index=False))


if __name__ == "__main__":
    {"fetch": fetch, "analyse": analyse}[sys.argv[1]]()

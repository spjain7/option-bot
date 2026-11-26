"""OI-LIVE-001 (26-Nov-2026, owner: "if we add OI as a filter, would it have stopped the calls that went negative?").
Every live-ledger call (28-Oct .. 25-Nov-2026, alerts-state) labelled with the OI build-up of the LAST COMPLETED SESSION
before the call (all futures expiries of the underlying added, so a roll does not look like an OI change):
  LB long build-up (price up, OI up) · SB short build-up (price down, OI up) · SC short covering (up, OI down) ·
  LU long unwinding (down, OI down). Sources: NSE F&O bhavcopy (research-nse-bhav), MCX bhavcopy (research-mcx-bhav).
Filters: AGREE (BUY on LB/SC, SELL on SB/LU) · STRICT (BUY on LB, SELL on SB) · OI-UP (any side, OI rose) ·
BUY-OI-UP (the MCX day-trend rule from PR #88: BUY only after an OI rise, SELL untouched).
R = side x (exit - entry) / (entry - stop) for closed calls; open calls use the last price.
python research/program/oi_filter_live.py"""
import io, json, subprocess, sys, zipfile
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, "/home/claude/ob-main")
from alerts import scorecard as SCD, strategies as ST  # noqa: E402
NB = Path("/home/claude/rd/nb/research/data")
s = json.loads(subprocess.check_output(["git", "-C", "/home/claude/option-bot", "show", "origin/alerts-state:alerts/state.json"]))

nse = {}
for z in sorted((NB / "nse_bhav_raw").glob("*.zip")):
    with zipfile.ZipFile(z) as f:
        d = pd.read_csv(io.BytesIO(f.read(f.namelist()[0])), usecols=["TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "ClsPric", "PrvsClsgPric", "OpnIntrst"])
    d = d[d.FinInstrmTp.isin(["STF", "IDF"])]
    near = d.sort_values("XpryDt").groupby("TckrSymb").first()
    nse[pd.Timestamp(d.TradDt.iat[0])] = pd.DataFrame({"oi": d.groupby("TckrSymb").OpnIntrst.sum(), "c": near.ClsPric, "pc": near.PrvsClsgPric})
mcx = {}
for f in sorted((NB / "mcx_bhav/days").glob("*.csv")):
    d = pd.read_csv(f); d = d[d.instrument == "FUTCOM"]
    if d.empty: continue
    d["exp"] = pd.to_datetime(d.expiry, format="%d%b%Y", errors="coerce")
    d = d[d.close > 0]
    near = d.sort_values("exp").groupby("symbol").first()
    mcx[pd.Timestamp(d.date.iat[0])] = pd.DataFrame({"oi": d.groupby("symbol").oi_lots.sum(), "c": near.close, "pc": near.prev_close})


def label(src, name, t):
    days = sorted(k for k in src if k < t.normalize() or (k == t.normalize() and False))
    # last completed session = the latest bhav date strictly before the call's date (calls are intraday)
    if len(days) < 2: return None
    d1, d0 = days[-1], days[-2]
    if (t.normalize() - d1).days > 5: return None
    a, b = src[d1], src[d0]
    if name not in a.index or name not in b.index: return None
    doi = a.oi[name] / b.oi[name] - 1; dp = a.c[name] / a.pc[name] - 1
    lab = ("LB" if doi > 0 else "SC") if dp > 0 else ("SB" if doi > 0 else "LU")
    return lab, round(100 * doi, 2), round(100 * dp, 2)


MCXN = {"GOLDM": "GOLDM", "SILVERM": "SILVERM"}
rows = []
for r in s["ledger"]:
    st = SCD.strategy_of(r)
    if ST.retired(st) or r.get("status") in ("VOID", "WAITING"): continue
    if r.get("status") == "CLOSED" and "withdrawn" in str(r.get("note", "")).lower(): continue
    if r.get("activated") in (False, "False"): continue
    sd = 1 if r["side"] == "BUY" else -1
    e, sl = float(r["entry"]), float(r["sl"])
    px = float(r["exit"]) if r.get("status") == "CLOSED" else float(r.get("ulast") or e)
    R = sd * (px - e) / (sd * (e - sl)) if sd * (e - sl) > 0 else np.nan
    t = pd.Timestamp(r["time"])
    lab = label(mcx if r["seg"] == "MCX" else nse, r["name"], t)
    rows.append(dict(time=t.strftime("%d-%b %H:%M"), seg=r["seg"], name=r["name"], side=r["side"], strategy=st, status=r["status"],
                     R=round(R, 2), lab=lab[0] if lab else None, doi=lab[1] if lab else None, dp=lab[2] if lab else None,
                     oi_txt=r.get("oi_txt") or next((w for w in (r.get("why_for") or []) + (r.get("why_against") or []) if "OI" in w), None)))
T = pd.DataFrame(rows)
T["agree"] = ((T.side == "BUY") & T.lab.isin(["LB", "SC"])) | ((T.side == "SELL") & T.lab.isin(["SB", "LU"]))
T["strict"] = ((T.side == "BUY") & (T.lab == "LB")) | ((T.side == "SELL") & (T.lab == "SB"))
T["oiup"] = T.doi > 0
T["buyoiup"] = (T.side == "SELL") | (T.doi > 0)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 40)
K = T[T.lab.notna()]
print(f"calls {len(T)}, with OI data {len(K)}  (missing: {T[T.lab.isna()].name.tolist()})")
def st_(g): return pd.Series(dict(n=len(g), won=int((g.R > 0).sum()), lost=int((g.R <= 0).sum()), win=round(100 * (g.R > 0).mean()), sumR=round(g.R.sum(), 1), avgR=round(g.R.mean(), 2)))
out = {"ALL (no filter)": st_(K)}
for f, nm in (("agree", "AGREE"), ("strict", "STRICT"), ("oiup", "OI-UP"), ("buyoiup", "BUY-OI-UP")):
    out[nm + " kept"] = st_(K[K[f]]); out[nm + " BLOCKED"] = st_(K[~K[f]])
print(pd.DataFrame(out).T.to_string())
print(K.groupby(["seg", "lab"]).apply(st_).to_string())
print(K.sort_values("R")[["time", "seg", "name", "side", "strategy", "R", "lab", "doi", "dp", "agree", "oi_txt"]].to_string(index=False))
T.to_csv(ROOT / "research/program/results/oi_filter_live.csv", index=False)

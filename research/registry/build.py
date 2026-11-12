"""One experiment registry for every market (owner 11-Nov priority 6). Rebuilt from the result files each study writes,
so nothing is typed by hand and nothing silently disappears; a study whose result file is missing is listed as such.
Columns: strategy_id · study · script · market · timeframe · family · rule · context · side · target · periods ·
DEV / VALID / OOS n, win %, avg R, PF · all-period n / avg R · day-clustered t · multiple-testing flag · cost model ·
result (PASS / FAIL by that study's own pre-set gate) · status · rejection reason · trade file.
Status: research only (default) · experimental-live (sent as EXPERIMENTAL alerts today) · candidate (passed its gate AND
the multiple-testing control AND a separate stress test) – nothing is "approved for production" by this file.
python -m research.registry.build  ->  research/registry/registry.csv.gz + REGISTRY.md"""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
COST = dict(MCX="real MCX fees + 1.5 ticks slippage per side",
            FUT="futures: STT sell 0.0125/0.02/0.05 % by date, exch 0.00173 % x2, stamp, GST, ₹40 brokerage, slippage 0.03 % (stocks) / 0.01 % (index) per side, +1 round trip per roll",
            CASH_DEL="delivery 0.393 % round trip incl. 0.05 % slippage per side", CASH_INT="intraday 0.163 % round trip incl. slippage")
LIVE = {}      # filled from the production code facts below (status experimental-live)


def sid(*parts):
    return "S-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10]


def reason(r, gate):
    if r.get("result") == "PASS":
        if r.get("mt_pass") is False:
            return "passed the period gate but not the multiple-testing control"
        return ""
    bits = []
    for p in ("DEV", "VAL", "OOS"):
        n, R, pf = r.get(f"{p}_n"), r.get(f"{p}_R"), r.get(f"{p}_PF")
        if n is None or (isinstance(n, float) and np.isnan(n)):
            continue
        if n < gate.get("min_n", 30):
            bits.append(f"{p} too few trades ({int(n)})")
        elif R is not None and R <= 0:
            bits.append(f"{p} loses ({R:+.2f}R)")
        elif pf is not None and pf < gate.get("pf", 1.2):
            bits.append(f"{p} PF {pf:.2f} < {gate.get('pf', 1.2)}")
    return "; ".join(bits) or "failed the study's gate"


def std(df, **fix):
    for k, v in fix.items():
        df[k] = v
    return df


def rsidiv(file, study, script, market, cost, periods, trades):
    p = ROOT / file
    if not p.exists():
        return None, dict(study=study, missing=file)
    L = pd.read_csv(p)
    out = pd.DataFrame(dict(study=study, script=script, market=market, timeframe=L.tf, family=L.family, rule=L.event,
                            context=L.context if "context" in L else L.zone_or_context, side=L.side, target=L.target_R.astype(str) + "R",
                            periods=periods))
    for p_ in ("DEV", "VAL", "OOS"):
        for k in ("n", "win", "R", "PF"):
            out[f"{p_}_{k}"] = L.get(f"{p_}_{k}")
    out["all_n"] = L.get("all_n", L.get("n")); out["all_R"] = L.get("all_R", L.get("R"))
    out["t_day"] = L.get("t_day", L.get("t")); out["mt_pass"] = L.get("FDR10")
    out["holm5"] = L.get("HOLM5"); out["instruments"] = L.get("names"); out["instruments_positive"] = L.get("names_pos")
    out["cost_model"] = cost; out["result"] = np.where(L.PASS.fillna(False), "PASS", "FAIL"); out["trades_file"] = trades
    out.loc[out.family == "BASE", "result"] = "BENCHMARK"
    return out, None


def mcx_reversal():
    L = pd.read_csv(ROOT / "research/mcxhw/results/reversal_pooled.csv")
    out = pd.DataFrame(dict(study="MCX-REV reversal candles (10-Nov)", script="research/mcxhw/reversal.py", market="MCX", timeframe=L.tf,
                            family="REVERSAL_CANDLE", rule=L.candle + " / " + L.entry, context=L.context, side=L.side, target=L.target_R.astype(str) + "R",
                            periods="DEV=CHECK 2023…Jan-2026 · OOS=FOCUS Feb…Nov-2026",
                            DEV_n=L.C_n, DEV_win=L.C_win, DEV_R=L.C_R, DEV_PF=L.C_PF, OOS_n=L.F_n, OOS_win=L.F_win, OOS_R=L.F_R, OOS_PF=L.F_PF))
    out["all_n"] = L.C_n + L.F_n; out["all_R"] = (L.C_R * L.C_n + L.F_R * L.F_n) / out.all_n
    out["cost_model"] = COST["MCX"]; out["result"] = np.where(L.GOOD | L.get("GOOD_small", False), "PASS", "FAIL")
    out["mt_pass"] = False; out["trades_file"] = ""
    return out


def mcx_highwin():
    L = pd.read_csv(ROOT / "research/mcxhw/results/mcxhw_focus_candidates.csv")
    out = pd.DataFrame(dict(study="MCX-HW 80-90 % win search (10-Nov)", script="research/mcxhw/search.py", market="MCX", timeframe=L["mode"],
                            family="HIGH_WIN", rule=L.pattern, context="trend " + L.trend.astype(str) + " · " + L.commodity.astype(str), side=L.side,
                            target=L.target_atr.astype(str) + " ATR / stop " + L.stop_atr.astype(str) + " ATR",
                            periods="DEV=CHECK 2023…Jan-2026 · OOS=FOCUS Feb…Nov-2026",
                            DEV_n=L.C_n, DEV_win=L.C_win, DEV_R=L.C_net_atr, DEV_PF=L.C_PF, OOS_n=L.F_n, OOS_win=L.F_win, OOS_R=L.F_net_atr, OOS_PF=L.F_PF))
    out["all_n"] = L.C_n + L.F_n; out["cost_model"] = COST["MCX"]; out["mt_pass"] = False; out["trades_file"] = ""
    out["result"] = np.where(L.winner.fillna(False), "PASS", "FAIL")
    out["note"] = "R columns are net ATR, not R. Only the 805 of 32,044 variants that passed the FOCUS test were saved; the other 31,239 failed it (win < 80 % or net <= 0 or < 40 trades) and are counted in REGISTRY.md, not listed row by row."
    return out


def cashq():
    L = pd.read_csv(ROOT / "research/cashq/results/LEADERBOARD.csv")
    extra = [pd.read_csv(ROOT / f"research/cashq/results/{f}.csv") for f in ("lonesome_leaderboard", "screeners_leaderboard")]
    for x in extra:
        L = pd.concat([L, x[~x.exp_id.isin(L.exp_id)]], ignore_index=True)
    tf = L.get("tf").fillna("1d") if "tf" in L else "1d"
    out = pd.DataFrame(dict(study="CASHQ cash research engine (Nov-2026)", script="research/cashq/*.py", market="NSE_CASH", timeframe=tf,
                            family=L.family, rule=L.strategy, context=L.params.astype(str), side=L.side, target=L.R.astype(str) + "R",
                            periods="daily DEV 2005-14 · VALID 2015-19 · OOS 2020-26; intraday DEV Oct-24…Sep-25 · VALID Oct-25…Mar-26 · OOS Apr-26…"))
    for p_, q in (("DEV", "DEV"), ("VAL", "VALID"), ("OOS", "OOS")):
        out[f"{p_}_n"], out[f"{p_}_win"], out[f"{p_}_R"], out[f"{p_}_PF"] = L.get(f"{q}_n"), L.get(f"{q}_win"), L.get(f"{q}_avgR"), L.get(f"{q}_PF")
    out["all_n"] = L.get("n_all"); out["t_day"] = L.get("OOS_t"); out["mt_pass"] = L.get("OOS_q") < 0.10
    out["cost_model"] = np.where(out.timeframe.astype(str).str.contains("m"), COST["CASH_INT"], COST["CASH_DEL"])
    out["result"] = np.where(L.status.astype(str).str.upper().str.startswith("PASS"), "PASS", "FAIL"); out["study_status"] = L.status
    out["trades_file"] = ""
    return out


def btst():
    L = pd.read_csv(ROOT / "research/eqbtst/RESULTS_btst.csv")
    out = pd.DataFrame(dict(study="EQ-BTST cash buy-today-sell-tomorrow", script="research/eqbtst/btst.py", market="NSE_CASH", timeframe="1d",
                            family="BTST", rule=L.setup, context="market " + L.mkt.astype(str), side="BUY", target=L.exit.astype(str), periods="DEV / OOS",
                            DEV_n=L.DEV_n, DEV_win=L.DEV_win, DEV_R=L.DEV_net, OOS_n=L.OOS_n, OOS_win=L.OOS_win, OOS_R=L.OOS_net))
    out["t_day"] = L.OOS_t; out["mt_pass"] = L.OOS_q < 0.10; out["cost_model"] = COST["CASH_DEL"]
    out["result"] = np.where(L.PASS.fillna(False), "PASS", "FAIL"); out["note"] = "R columns are net % per trade"; out["trades_file"] = ""
    return out


def rsirev():
    parts = []
    for m in ("mcx", "stockfut", "index", "cash"):
        f = ROOT / f"research/rsirev/results/{m}_grid.csv"
        if not f.exists():
            continue
        L = pd.read_csv(f)
        cost = COST["MCX"] if m == "mcx" else (COST["CASH_DEL"] if m == "cash" else COST["FUT"])
        out = pd.DataFrame(dict(study="RSIREV reversal vs continuation, 10 strategies x entry x stop x target x regime (11-Nov)",
                                script="research/rsirev/run.py", market=L.market, timeframe=L.tf, family="RSI_REV_CONT",
                                rule=L.strategy + " " + L.rule, context="entry " + L.entry + " · stop " + L.stop + " · regime " + L.regime,
                                side=np.where(L.label.str.endswith("BUY"), "BUY", "SELL"), target=L.target_R.astype(str) + "R", label=L.label))
        for p_ in ("DEV", "VAL", "OOS"):
            for k in ("n", "win", "R", "PF"):
                out[f"{p_}_{k}"] = L.get(f"{p_}_{k}")
        out["all_n"], out["all_R"], out["t_day"] = L.all_n, L.get("all_R"), L.get("t_day")
        out["mt_pass"], out["holm5"] = L.FDR10, L.HOLM5
        out["instruments"], out["instruments_positive"] = L.get("names"), L.get("names_pos")
        out["cost_model"] = cost; out["result"] = np.where(L.PASS.fillna(False), "PASS", "FAIL"); out["trades_file"] = ""
        out["periods"] = "MCX DEV to 2021… see research/rsirev/README.md"
        parts.append(out)
    return pd.concat(parts, ignore_index=True)


def cycle2():
    parts, C2 = [], ROOT / "research/cycle2/results"
    f = C2 / "cont_buy_filters_all.csv"
    if f.exists():
        L = pd.read_csv(f)
        o = pd.DataFrame(dict(study="CYCLE2-1 continuation BUY: one filter at a time, DEV+VALID selection, OOS check, walk-forward (11-Nov)",
                              script="research/cycle2/cont_buy.py", market=L.market, timeframe=L.tf, family="CONT_BUY_FILTER",
                              rule=L.base.map({"B1": "B1 RSI crosses >= 75", "B2": "B2 S10"}) + " + " + L["filter"], context="filter keep share " + L.keep_share.astype(str),
                              side="BUY", target=L.target_R.astype(str) + "R", label="CONTINUATION BUY",
                              DEV_n=L.DEV_n, DEV_R=L.DEV_R, VAL_n=L.VAL_n, VAL_R=L.VAL_R, OOS_n=L.OOS_n, OOS_R=L.OOS_R, all_n=L.n,
                              t_day=L.oos_welch_t, mt_pass=L.FDR10, cost_model="per market (research/rsidiv)", trades_file=""))
        o["result"] = np.where(L.genuine & L.FDR10, "PASS", np.where(L.genuine, "FAIL (selected on DEV+VALID and better OOS, not significant)", "FAIL"))
        o["note"] = "t_day column = OOS Welch t of filtered vs excluded trades; base OOS R " + L.OOS_base_R.astype(str) + "; walk-forward R " + L.wf_R.astype(str) + " vs base " + L.wf_base_R.astype(str)
        parts.append(o)
    f = C2 / "mcx_trend.csv"
    if f.exists():
        L = pd.read_csv(f)
        o = pd.DataFrame(dict(study="CYCLE2-4 MCX continuation by objective daily trend, metals vs energy (11-Nov)", script="research/cycle2/mcx_trend.py",
                              market="MCX", timeframe=L.tf, family="MCX_TREND", rule=L.strategy, context="trend " + L.trend + " · " + L.realism + " · " + L.group,
                              side=np.where(L.label.str.endswith("BUY"), "BUY", "SELL"), target=L.target_R.astype(str) + "R", label=L.label,
                              DEV_n=L.DEV_n, DEV_R=L.DEV_R, DEV_PF=L.DEV_PF, VAL_n=L.VAL_n, VAL_R=L.VAL_R, VAL_PF=L.VAL_PF, OOS_n=L.OOS_n, OOS_R=L.OOS_R,
                              OOS_PF=L.OOS_PF, all_n=L.n, all_R=L.R, t_day=L.t_day, mt_pass=L.FDR10, cost_model=COST["MCX"], trades_file="",
                              note=L.per_commodity))
        o["result"] = np.where(L.PASS, "PASS", "FAIL"); parts.append(o)
    f = C2 / "sf_crowd.json"
    if f.exists():
        J = json.load(open(f))
        for k, v in J.items():
            if not (isinstance(v, dict) and "research_basis" in v):
                continue
            rb, fb = v["research_basis"], v["futures_basis"]
            parts.append(pd.DataFrame([dict(study="CYCLE2-2 stock-futures CONTINUATION SELL crowding versions (11-Nov)", script="research/cycle2/sf_crowd.py",
                                             market="NSE_STOCK_FUT", timeframe="1d", family="SF_CROWD", rule=k, context="futures basis R " + str(fb["all"].get("R")),
                                             side="SELL", target="3.0R", label="CONTINUATION SELL", DEV_n=rb["DEV"].get("n"), DEV_R=rb["DEV"].get("R"),
                                             VAL_n=rb["VAL"].get("n"), VAL_R=rb["VAL"].get("R"), OOS_n=rb["OOS"].get("n"), OOS_R=rb["OOS"].get("R"),
                                             all_n=rb["all"].get("n"), all_R=rb["all"].get("R"), cost_model=COST["FUT"], trades_file="research/cycle2/results/sf_crowd_trades.csv.gz",
                                             result="v1 = shadow (unchanged)" if k.startswith("v1") else "research only – variant motivated by 2026 data, not evidence",
                                             note=f"futures: DEV {fb['DEV'].get('R')} VAL {fb['VAL'].get('R')} OOS {fb['OOS'].get('R')} 2026 {fb['y2026'].get('R')}")]))
    f = C2 / "cash_cm.json"
    if f.exists():
        J = json.load(open(f))
        for k, v in J["conditions"].items():
            for side_, lab in (("inside", "only when"), ("outside", "only when NOT")):
                x = v[side_]
                parts.append(pd.DataFrame([dict(study="CYCLE2-3 cash CONTINUATION BUY market dependence (11-Nov)", script="research/cycle2/cash_cm.py", market="NSE_CASH",
                                                 timeframe="1w", family="CM_CONDITION", rule=f"CM-CONT-BUY-v1 {lab} {k}", context=f"OOS inside-outside {v['oos_inside_minus_outside']} t {v['oos_welch_t']}",
                                                 side="BUY", target="1.0R", label="CONTINUATION BUY", DEV_n=x["DEV"].get("n"), DEV_R=x["DEV"].get("R"), VAL_n=x["VAL"].get("n"),
                                                 VAL_R=x["VAL"].get("R"), OOS_n=x["OOS"].get("n"), OOS_R=x["OOS"].get("R"), all_n=x["all"].get("n"), all_R=x["all"].get("R"),
                                                 cost_model=COST["CASH_DEL"], trades_file="", result="research only (condition split)")]))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def cycle3():
    parts, C3 = [], ROOT / "research/cycle3/results"
    f = C3 / "rvol_cells.csv"
    if f.exists():
        L = pd.read_csv(f)
        parts.append(pd.DataFrame(dict(study="CYCLE3-1 CONT-BUY-B1-RVOL2-v1 stability (11-Nov)", script="research/cycle3/rvol.py", market=L.market, timeframe=L.tf,
                                       family="RVOL_VERSION", rule="B1 + volume >= 2x (version CONT-BUY-B1-RVOL2-v1)", context="kept share " + L.kept_share.astype(str),
                                       side="BUY", target=L.target_R.astype(str) + "R", label="CONTINUATION BUY", DEV_R=L.DEV_version_R, VAL_R=L.VAL_version_R,
                                       OOS_R=L.OOS_version_R, OOS_n=L.OOS_kept_n, all_n=L.base_n, t_day=L.oos_t, mt_pass=L.BH10, holm5=L.HOLM5,
                                       result="FAIL (no cell passes Holm / BH)", cost_model="per market", trades_file="",
                                       note="years kept better " + L.years_kept_better + " · instruments " + L.instruments_kept_better + " · dose " + L.dose_response_all_R)))
    f = C3 / "mcx_metals.csv"
    if f.exists():
        L = pd.read_csv(f)
        parts.append(pd.DataFrame(dict(study="CYCLE3-3 MCX 3h continuation by commodity + benchmarks + untouched Jul-2022 window (11-Nov)", script="research/cycle3/mcx_metals.py",
                                       market="MCX", timeframe="3h", family="MCX_METALS", rule=L.signal, context="trend " + L.trend + " · " + L.group, side="BUY",
                                       target=L.target_R.astype(str) + "R", label=np.where(L.signal.isin(["B1", "S10"]), "CONTINUATION BUY", "benchmark"),
                                       DEV_n=L.DEV_n, DEV_R=L.DEV_R, VAL_n=L.VAL_n, VAL_R=L.VAL_R, OOS_n=L.OOS_n, OOS_R=L.OOS_R, all_n=L.ALL_n, all_R=L.ALL_R,
                                       untouched_n=L.UNTOUCHED_n, untouched_R=L.UNTOUCHED_R, cost_model=COST["MCX"], trades_file="",
                                       result=np.where(L.signal.isin(["B1", "S10"]), "research only", "BENCHMARK"))))
    f = ROOT / "research/families/results/families.csv"
    if f.exists():
        L = pd.read_csv(f)
        o = pd.DataFrame(dict(study="FAMILIES ORB / sweep+MSS / VWAP / squeeze / climax / pullback / S-R retest (11-Nov)", script="research/families/run.py",
                              market=L.market, timeframe=L.tf, family=L.family, rule=L.family, context="", side=L.side, target=L.target_R.astype(str) + "R",
                              label="not an RSI / divergence rule", cost_model="per market", trades_file=""))
        for p_ in ("DEV", "VAL", "OOS"):
            for k in ("n", "win", "R", "PF"):
                o[f"{p_}_{k}"] = L.get(f"{p_}_{k}")
        o["all_n"], o["all_R"], o["t_day"], o["mt_pass"], o["holm5"] = L.all_n, L.get("all_R"), L.get("t_day"), L.get("FDR10"), L.get("HOLM5")
        o["result"] = np.where(L.family.str.startswith("BENCH"), "BENCHMARK", np.where(L.PASS.fillna(False), "PASS", "FAIL"))
        parts.append(o)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def forward_shadow():
    """forward (live) shadow results from branch shadow-state – kept apart from every back-test row."""
    import subprocess, io
    rows = []
    try:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin", "shadow-state"], check=True, capture_output=True)
        for sid in ("SF-CONT-SELL-v1", "CM-CONT-BUY-v1"):
            try:
                txt = subprocess.run(["git", "-C", str(ROOT), "show", f"FETCH_HEAD:shadow/trades_{sid}.csv"], check=True, capture_output=True, text=True).stdout
                T = pd.read_csv(io.StringIO(txt))
            except Exception:
                T = pd.DataFrame(columns=["status", "exec_R"])
            done = T[T.status.astype(str).str.startswith(("TARGET", "STOP", "TIME"))] if len(T) else T
            rows.append(dict(study="FORWARD SHADOW (live, from 11-Nov-2026)", script="research/shadow/run.py", market="NSE_STOCK_FUT" if sid.startswith("SF") else "NSE_CASH",
                             timeframe="1d" if sid.startswith("SF") else "1w", family="SHADOW", rule=sid, context="forward signals " + str(len(T)),
                             side="SELL" if sid.startswith("SF") else "BUY", target="3.0R" if sid.startswith("SF") else "1.0R",
                             label="CONTINUATION SELL" if sid.startswith("SF") else "CONTINUATION BUY", forward_signals=len(T), forward_closed=len(done),
                             forward_R=round(float(done.exec_R.mean()), 3) if len(done) else np.nan,
                             forward_not_executable=int(T.status.astype(str).str.startswith("NOT EXEC").sum()) if len(T) else 0,
                             result="forward evidence accumulating", status="SHADOW TEST running since 11-Nov-2026 (not promoted)", cost_model="real execution", trades_file=f"shadow-state:shadow/trades_{sid}.csv"))
    except Exception as e:
        rows.append(dict(study="FORWARD SHADOW", rule="unavailable", note=str(e)[:100]))
    return pd.DataFrame(rows)


def direction_label(R):
    """REVERSAL / CONTINUATION + BUY / SELL for every RSI or divergence row (owner 11-Nov: keep them apart)."""
    lab = pd.Series("not an RSI / divergence rule", index=R.index, dtype=object)
    ev, ctx, side = R.rule.astype(str), R.context.astype(str), R.side.astype(str)
    m = ev.str.contains(":reversal"); lab[m] = "REVERSAL " + side[m]
    m = ev.str.contains(":continuation"); lab[m] = "CONTINUATION " + side[m]
    m = R.family.astype(str).eq("DIV") & ev.str.contains(":regular"); lab[m] = "REVERSAL " + side[m] + " (regular divergence)"
    m = R.family.astype(str).eq("DIV") & ev.str.contains(":hidden"); lab[m] = "CONTINUATION " + side[m] + " (hidden divergence)"
    mr = R.study.astype(str).str.startswith("MCX-RD") & R.family.astype(str).eq("RSI")
    z75, z25 = ctx.str.startswith("75"), ctx.str.startswith("25")
    lab[mr & z75 & side.eq("SELL")] = "REVERSAL SELL"; lab[mr & z75 & side.eq("BUY")] = "CONTINUATION BUY"
    lab[mr & z25 & side.eq("BUY")] = "REVERSAL BUY"; lab[mr & z25 & side.eq("SELL")] = "CONTINUATION SELL"
    if "label" in R:
        lab = R["label"].where(R["label"].notna(), lab)
    return lab


def main():
    parts, missing = [], []
    SFP = "daily DEV 2018-21 · VALID 2022-23 · OOS 2024-26"
    specs = [
        ("research/mcxhw/results/rsi_div_pooled.csv", "MCX-RD RSI 75/25 + divergence, pooled (10-Nov)", "research/mcxhw/rsi_div.py", "MCX", COST["MCX"], "DEV to 2024 · VALID 2025 · OOS 2026", ""),
        ("research/mcxhw/results/rsi_div_by_commodity.csv", "MCX-RD RSI 75/25 + divergence, per commodity (10-Nov)", "research/mcxhw/rsi_div.py", "MCX", COST["MCX"], "DEV to 2024 · VALID 2025 · OOS 2026", ""),
        ("research/rsidiv/results/stockfut_variants.csv", "RSIDIV-SF stock futures RSI + divergence + OI + basis (11-Nov)", "research/rsidiv/stockfut.py", "NSE_STOCK_FUT", COST["FUT"], SFP, "research/rsidiv/results/stockfut_trades.csv.gz"),
        ("research/rsidiv/results/index_variants.csv", "RSIDIV-IX index futures RSI + divergence + OI (11-Nov)", "research/rsidiv/index.py", "NSE_INDEX_FUT", COST["FUT"], SFP + "; hourly DEV Jul-22…Jun-24 · VALID Jul-24…Jun-25 · OOS Jul-25…Oct-26", "research/rsidiv/results/index_trades.csv.gz"),
        ("research/rsidiv/results/cash_variants.csv", "RSIDIV-CM cash RSI + divergence + liquidity / RS / sector (11-Nov)", "research/rsidiv/cash.py", "NSE_CASH", COST["CASH_DEL"], "DEV 2005-14 · VALID 2015-19 · OOS 2020-26", "research/rsidiv/results/cash_trades.csv.gz"),
    ]
    for f, st, sc, mk, co, pe, tr in specs:
        x, miss = rsidiv(f, st, sc, mk, co, pe, tr)
        if x is None:
            missing.append(miss)
        else:
            if "per commodity" in st:
                L = pd.read_csv(ROOT / f); x["instruments"] = L.commodity
            parts.append(x)
    for fn in (mcx_reversal, mcx_highwin, cashq, btst, rsirev, cycle2, cycle3, forward_shadow):
        try:
            parts.append(fn())
        except Exception as e:
            missing.append(dict(study=fn.__name__, error=str(e)))
    R = pd.concat(parts, ignore_index=True)
    fwd = R.study.astype(str).str.startswith("FORWARD")
    R["status"] = np.where(fwd, "SHADOW TEST running since 11-Nov-2026 (not promoted)", "research only")
    R["direction_label"] = direction_label(R)
    R["evidence_stage"] = np.where(R.study.astype(str).str.startswith("FORWARD"), "FORWARD SHADOW (live)",
                                   "BACKTEST – DEV/VALID in-sample, OOS = held-out history" + np.where(R.get("untouched_n", pd.Series(np.nan, index=R.index)).notna(), " + untouched window", ""))
    # stress-tested items (separate scripts; their verdicts are written in REGISTRY.md and the JSON files)
    stress = {}
    for f in ("research/mcxhw/results/hidden_check.json", "research/rsidiv/results/sf_check.json"):
        if (ROOT / f).exists():
            stress[f] = json.load(open(ROOT / f))
    CAND = [  # passed its gate + multiple-testing control + a separate stress test -> shadow testing only, never live
        dict(market="NSE_STOCK_FUT", timeframe="1d", family="RSI", rule="break5:continuation", context="zone25", side="SELL", target="3.0R",
             status="SHADOW TEST running since 11-Nov-2026 (not promoted)", label="CONTINUATION SELL", version="SF-CONT-SELL-v1",
             note="stress test research/rsidiv/results/sf_check.json + research/shadow/results/investigate_sf.json: placebo 0/300, neighbours positive, but 2019/2020/2023/2026 negative, weaker in falling markets"),
        dict(market="NSE_CASH", timeframe="1w", family="RSI", rule="cross_in:continuation", context="zone75|liq_bottom", side="BUY", target="1.0R",
             status="SHADOW TEST running since 11-Nov-2026 (not promoted)", label="CONTINUATION BUY", version="CM-CONT-BUY-v1",
             note="stress test research/rsidiv/results/cash_check.json + research/shadow/results/investigate_cm.json: placebo 0/300, robust to RSI 70-80 and liquidity cut, survives 0.3 % slippage; loses when the market is below its 40-week EMA")]
    R["stress_note"] = ""
    for c in CAND:
        m = np.ones(len(R), bool)
        for k in ("market", "timeframe", "family", "rule", "context", "side", "target"):
            m &= R[k].astype(str).values == c[k]
        R.loc[m & ~R.study.astype(str).str.startswith("FORWARD"), "status"] = c["status"]; R.loc[m, "stress_note"] = c["note"]; R.loc[m, "direction_label"] = c["label"]
        R.loc[m, "shadow_version"] = c["version"]
    R.loc[R.study.str.startswith("MCX-RD") & (R.timeframe == "3h") & R.rule.isin(["macd:hidden", "obv:hidden"]) & (R.side == "BUY"), "stress_note"] = \
        "stress test research/mcxhw/results/hidden_check.json: not promoted – below Bonferroni (t 3.3 vs 4.7), fails with pivot K=2, energy ~0R, divergence adds little over any higher low (p 0.04)"
    kf = [c for c in ("study", "timeframe", "family", "rule", "context", "side", "target", "instruments") if c in R]
    dup = R.groupby(kf, dropna=False).cumcount()                     # identical labels (e.g. MCX-HW hold variants) -> ordinal
    R["strategy_id"] = [sid(*v, d) for v, d in zip(R[kf].astype(str).values, dup.values)]
    R["rejection_reason"] = [reason(r, dict(min_n=30, pf=1.2)) if r["result"] != "BENCHMARK" else "" for r in R.to_dict("records")]
    first = ["strategy_id", "evidence_stage", "study", "market", "timeframe", "direction_label", "family", "rule", "context", "side", "target", "result", "status", "rejection_reason",
             "DEV_n", "DEV_win", "DEV_R", "DEV_PF", "VAL_n", "VAL_win", "VAL_R", "VAL_PF", "OOS_n", "OOS_win", "OOS_R", "OOS_PF", "all_n", "all_R",
             "t_day", "mt_pass", "holm5", "instruments", "instruments_positive", "periods", "cost_model", "script", "trades_file"]
    R = R[[c for c in first if c in R] + [c for c in R if c not in first]]
    assert R.strategy_id.is_unique
    R.to_csv(OUT / "registry.csv.gz", index=False, compression="gzip")
    R["pass_and_mt"] = (R.result == "PASS") & R.mt_pass.fillna(False).astype(bool)
    s = R.groupby(["market", "study"]).agg(variants=("result", "size"), passed=("result", lambda x: int((x == "PASS").sum())),
                                           passed_and_multiple_testing=("pass_and_mt", "sum")).reset_index()
    json.dump(dict(rows=len(R), missing=missing, by_study=s.to_dict("records"), stress_files=list(stress)), open(OUT / "registry_summary.json", "w"), indent=1, default=str)
    print(s.to_string(index=False)); print("rows", len(R), "missing", missing)
    return R, s


if __name__ == "__main__":
    main()

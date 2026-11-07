"""MCXE-004 script inventory (automatic, evidence-based). For every Python file under research/ (research branch) and every
alert / strategy module on main (alerts/, cashstock/, obuy/, crude/, runner.py, strategy.py, market.py):
  script_id, file, docstring summary, markets / timeframes mentioned, output files it writes (parsed from the code),
  which of those outputs exist and when they were last COMMITTED (git log), whether it is scheduled (named in a GitHub
  workflow or scripts/market_loop.sh on main), REPORT.md section that cites it, whether it produces trades / signals /
  statistics (parsed from its code), and an EXECUTION verdict:
     EXECUTED (committed output)  – an output file it writes is committed; date = last commit of that output
     EXECUTED (live loop log)     – main module seen running in the 6-Nov market-loop log (prefix evidence)
     SCHEDULED                    – named in a workflow / loop script (live code)
     DEFINED ONLY                 – no committed output, no schedule, no log evidence (may have run locally; not claimed)
     LIBRARY                      – helper module imported by others, no outputs of its own
A file existing is never taken as proof that it ran.
python research/mcxe004/inventory.py   -> research/mcxe004/script_inventory.csv / .md"""
import re
import subprocess
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MAIN = Path("/home/claude/ob-main")
LOG = Path("/tmp/claude-0/-home-claude/9dfb3327-26db-5f33-89ad-b39b1ae569a9/scratchpad/log_42154958592.txt")
OUT = ROOT / "research/mcxe004"
MK = {"MCX": r"\bMCX\b|GOLD|SILVER|CRUDE|NATURALGAS|COPPER", "NSE_CASH": r"cash|bhavcopy|NSE_EQ|eq_|delivery",
      "NSE_FUT": r"stock futures|NFO|FUTSTK|STOCKS|stk", "INDEX": r"NIFTY|BANKNIFTY|index", "OPTIONS": r"option|premium|\bCE\b|\bPE\b"}
TF = r"\b(1m|3m|5m|15m|30m|1h|2h|3h|4h|5h|6h|1d|daily|weekly|monthly|1w|1M|hourly|5-min|15-min|intraday)\b"


def git_date(repo, path):
    try:
        out = subprocess.check_output(["git", "-C", str(repo), "log", "-1", "--format=%cs", "--", str(path)], text=True).strip()
        return out or None
    except Exception:                                             # noqa: BLE001
        return None


def outputs(src):
    outs = set()
    for m in re.finditer(r'OUT\s*/\s*f?"([^"]+)"', src):
        outs.add(m.group(1))
    for m in re.finditer(r'(?:to_csv|to_parquet|write_text|savefig)\(\s*(?:OUT\s*/\s*)?f?"([^"]+\.(?:csv|gz|json|md|png|parquet|txt))"', src):
        outs.add(m.group(1))
    return sorted(outs)


def kind(src):
    k = []
    if re.search(r"simulate\(|net=|r1=|r2=|\bR\b.*=.*/ R|status=\"trade\"|walk\(", src):
        k.append("trades")
    if re.search(r"signal|sig\b|setups?_for|detect\(", src):
        k.append("signals")
    if re.search(r"t\.sf|ttest|bootstrap|BH|q_DEV|p_value|stats\.", src):
        k.append("statistics")
    return "+".join(k) or "none detected"


def summary(src):
    m = re.match(r'\s*(?:#.*\n)*\s*[rR]?"""(.*?)"""', src, re.S)
    if not m:
        return ""
    return " ".join(m.group(1).strip().split())[:220]


def scan(repo, files, results_dirs, sched_text, log_text, report_text, origin):
    rows = []
    for p in files:
        src = p.read_text(errors="ignore")
        rel = p.relative_to(repo)
        outs = outputs(src)
        found = []
        for o in outs:
            name = Path(o.replace("{", "").replace("}", "")).name
            stem = re.sub(r"\{[^}]*\}", "*", o)
            for d in results_dirs:
                for q in list(d.glob(stem)) + ([d / o] if (d / o).exists() else []):
                    dt = git_date(repo, q)
                    if dt:
                        found.append((str(q.relative_to(repo)), dt))
        found = sorted(set(found), key=lambda x: x[1])
        mod = str(rel.with_suffix("")).replace("/", ".")
        scheduled = bool(re.search(rf"(-m\s+{re.escape(mod)}\b|{re.escape(str(rel))})", sched_text))
        live_seen = False
        if origin == "main" and log_text:
            tag = p.stem
            generic = tag in ("run", "engine", "config", "data", "report", "paper", "rules", "stats", "probe", "backtest", "market")
            live_seen = bool(re.search(rf"\[{re.escape(tag)}\]|\b{re.escape(mod)}\b" + ("" if generic else rf"|\b{re.escape(tag)}:"), log_text))
        rid = re.findall(r"^## ([A-Z0-9][A-Z0-9\-/ +]+?)[ (–—-]", report_text, re.M)
        cited = [s for s in rid if p.stem.upper().replace("_", "")[:6] in s.replace("-", "").replace(" ", "")][:3]
        if not outs and "def main" not in src and "__main__" not in src:
            verdict = "LIBRARY"
        elif found:
            verdict = "EXECUTED (committed output)"
        elif live_seen:
            verdict = "EXECUTED (live loop log 6-Nov)"
        elif scheduled:
            verdict = "SCHEDULED"
        else:
            verdict = "DEFINED ONLY (no committed output / schedule / log evidence)"
        markets = [k for k, rx in MK.items() if re.search(rx, src)]
        tfs = sorted(set(re.findall(TF, src)))[:8]
        rows.append(dict(script_id=f"{'M' if origin == 'main' else 'R'}-{str(rel.with_suffix('')).replace('/', '.')}",
                         repo=origin, file=str(rel), lines=src.count("\n"), summary=summary(src), markets=",".join(markets),
                         timeframes=",".join(tfs), produces=kind(src), outputs_declared=len(outs),
                         outputs_committed=len(found), last_output_commit=found[-1][1] if found else None,
                         example_output=found[-1][0] if found else None, last_code_commit=git_date(repo, rel),
                         scheduled=scheduled, cited_in_report=",".join(cited), execution=verdict))
    return rows


ENTRY = ["alerts.run", "runner", "obuy.run", "cashstock.run", "wsfeed"]
EVID = {"alerts/rulebook.py": r"rulebook:|RB_[A-Z]", "alerts/funnel.py": r"funnel|data failures", "alerts/four_hour.py": r"4h SELL scan",
        "alerts/stocks.py": r"\[stocks\]", "alerts/engine.py": r"bo_3h|bo_1d|\[conflict\]", "alerts/candle_setups.py": r"candle_setups",
        "alerts/news.py": r"HIGH-IMPACT NEWS|EVENT AHEAD", "alerts/report.py": r"report_NSE.png|INDEX \+ STOCK CALLS",
        "alerts/scorecard.py": r"\[scorecard\]", "alerts/mcx_dtc.py": r"mcxdtc|DTC|day-trend", "alerts/paper.py": r"\\[paper\\]|E_BUY_v1",
        "alerts/run.py": r"alerts outcome", "runner.py": r"option engine exit", "obuy/run.py": r"option-buy", "wsfeed.py": r"wsfeed|ws bars"}


def live_modules():
    """module -> import chain from a scheduled entry point (main repo)."""
    graph = {}
    for p in MAIN.rglob("*.py"):
        if "__pycache__" in str(p) or "/research/" in str(p) or "/tests/" in str(p):
            continue
        mod = str(p.relative_to(MAIN).with_suffix("")).replace("/", ".")
        src = p.read_text(errors="ignore")
        deps = set()
        for m in re.finditer(r"^\s*from\s+([\w.]+)\s+import\s+([\w ,]+)", src, re.M):
            base = m.group(1)
            deps.add(base)
            for nm in m.group(2).split(","):
                nm = nm.strip().split()[0] if nm.strip() else ""
                if nm:
                    deps.add(f"{base}.{nm}")
        for m in re.finditer(r"^\s*import\s+([\w.]+)", src, re.M):
            deps.add(m.group(1))
        graph[mod] = deps
    chain = {}
    for e in ENTRY:
        stack = [(e, e)]
        while stack:
            m, path = stack.pop()
            if m in chain or m not in graph:
                continue
            chain[m] = path
            for d in graph[m]:
                if d in graph and d not in chain:
                    stack.append((d, path + " > " + d))
    return chain


def live_evidence(log_text):
    out = {}
    for f, rx in EVID.items():
        n = len(re.findall(rx, log_text))
        if n:
            out[f] = f"{n} log matches /{rx}/"
    return out


def main():
    rep = (ROOT / "research/program/REPORT.md").read_text()
    log_text = LOG.read_text(errors="ignore") if LOG.exists() else ""
    sched = ""
    if MAIN.exists():
        for f in list((MAIN / ".github/workflows").glob("*.yml")) + [MAIN / "scripts/market_loop.sh"]:
            sched += f.read_text(errors="ignore") + "\n"
    rfiles = [p for p in (ROOT / "research").rglob("*.py") if "__pycache__" not in str(p) and "/data/" not in str(p)
              and p.name != "__init__.py" and "/tests/" not in str(p)]
    rdirs = [ROOT / "research/program/results", ROOT / "research/mcxe003/results", ROOT / "research/mcxe004/results",
             ROOT / "research/output", ROOT / "research/output_v2", ROOT / "research/output_v3", ROOT / "research/program"]
    rows = scan(ROOT, sorted(rfiles), rdirs, sched, "", rep, "research")
    if MAIN.exists():
        mfiles = []
        for d in ("alerts", "cashstock", "obuy", "crude"):
            mfiles += [p for p in (MAIN / d).glob("*.py") if p.name != "__init__.py"]
        mfiles += [MAIN / x for x in ("runner.py", "strategy.py", "market.py", "notify.py", "wsfeed.py", "wsbars.py", "angel.py", "paperguard.py")
                   if (MAIN / x).exists()]
        rows += scan(MAIN, sorted(mfiles), [MAIN / "alerts/results", MAIN / "state"], sched, log_text, rep, "main")
    T = pd.DataFrame(rows)
    if MAIN.exists():
        live = live_modules()
        ev = live_evidence(log_text)
        is_main = T.repo == "main"
        T.loc[is_main, "live_import_chain"] = T.loc[is_main, "file"].map(lambda f: live.get(f.replace("/", ".")[:-3], ""))
        T.loc[is_main, "live_log_evidence_6nov"] = T.loc[is_main, "file"].map(lambda f: ev.get(f, ""))
        reach = is_main & T.live_import_chain.astype(str).ne("")
        T.loc[reach & (T.execution.eq("LIBRARY") | T.execution.str.startswith("DEFINED")), "execution"] = "LIVE LOOP COMPONENT (imported by a scheduled entry point)"
        logged = is_main & T.live_log_evidence_6nov.astype(str).str.len().gt(3) & T.live_log_evidence_6nov.notna()
        T.loc[logged & ~T.execution.str.startswith("EXECUTED"), "execution"] = "EXECUTED (live loop log 6-Nov)"
    T.to_csv(OUT / "script_inventory.csv", index=False)
    print(T.groupby(["repo", "execution"]).size().to_string())
    return T


if __name__ == "__main__":
    main()

"""MCXE-005 preservation + safety tests.  python research/mcxe005/tests/test_preservation.py
  1 production unchanged: origin/main still at the recorded baseline commit, and the S4 signal-path files are byte-identical
  2 production S4 (run from a pristine archive of the baseline commit, in a separate process) reproduces the PETRONET /
    GLENMARK / TITAN BUY signals on the recorded fixtures
  3 negative controls: each S4 condition, when broken, removes the signal
  4 the research copy (s4_research.evaluate / signals_vectorised) makes the same decisions as production
  5 research code cannot send alerts or place orders (no Telegram / notify / broker / HTTP-POST imports or calls)
  6 the production alert test-suite passes on the pristine baseline archive
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
FX = ROOT / "research/mcxe005/fixtures"
META = json.loads((FX / "s4_meta.json").read_text())
BASE = META["production_commit"]
S4_FILES = ["alerts/stocks.py", "alerts/tradeplan.py", "alerts/strategies.py", "alerts/dataquality.py", "alerts/breakout.py",
            "alerts/signals.py", "alerts/run.py", "crude/indicators.py", "config.py", "paperguard.py", "scripts/market_loop.sh"]
CASES = [("PETRONET", "2026-11-02"), ("GLENMARK", "2026-11-04"), ("TITAN", "2026-11-04")]
_ARCH = {}


def git(*a):
    return subprocess.check_output(["git", "-C", str(ROOT), *a], text=True)


def baseline_dir():
    """pristine copy of main @ baseline (never the working tree of main)."""
    if "d" not in _ARCH:
        git("fetch", "-q", "origin", "main")
        d = Path(tempfile.mkdtemp(prefix="mainbase_"))
        p1 = subprocess.Popen(["git", "-C", str(ROOT), "archive", BASE], stdout=subprocess.PIPE)
        subprocess.check_call(["tar", "-x", "-C", str(d)], stdin=p1.stdout); p1.wait()
        _ARCH["d"] = d
    return _ARCH["d"]


def prod_eval(fixture_csv, doi, mutate=None):
    code = ("import json,sys; import pandas as pd; sys.path.insert(0,'.'); from alerts import stocks as S\n"
            "d=pd.read_csv(sys.argv[1],parse_dates=['time']); d['volume']=d['volume'].astype(float); d['doi']=d['oi'].pct_change(); d.loc[d.index[-1],'doi']=float(sys.argv[2])\n"
            "exec(sys.argv[3])\n"
            "r=S.evaluate(d); print(json.dumps({k:(round(v,6) if isinstance(v,float) else v) for k,v in r.items()},default=str))")
    out = subprocess.check_output([sys.executable, "-c", code, str(fixture_csv), str(doi), mutate or "pass"], cwd=baseline_dir(), text=True)
    return json.loads(out.strip().splitlines()[-1])


def load_fx(nm, day):
    d = pd.read_csv(FX / f"s4_{nm}_{day}.csv", parse_dates=["time"])
    d["volume"] = d["volume"].astype(float)
    d["doi"] = d["oi"].pct_change(); d.loc[d.index[-1], "doi"] = META["prod_doi"][nm]
    return d


def test_production_unchanged():
    head = git("rev-parse", "origin/main").strip()
    changed = [f for f in S4_FILES if git("diff", "--name-only", BASE, "origin/main", "--", f).strip()]
    assert not changed, f"S4 signal-path files changed on main since {BASE[:7]}: {changed} (HEAD {head[:7]})"
    for f in S4_FILES:
        a = hashlib.sha256(git("show", f"{BASE}:{f}").encode()).hexdigest()
        b = hashlib.sha256(git("show", f"origin/main:{f}").encode()).hexdigest()
        assert a == b, f


def test_production_reproduces_three_signals():
    for nm, day in CASES:
        r = prod_eval(FX / f"s4_{nm}_{day}.csv", META["prod_doi"][nm])
        assert r["side"] == "BUY", (nm, r)
        assert r["candle"].startswith(day)
        assert r["close"] > r["hh"] and r["vol_x"] > 1.5 and r["dp"] > 0 and r["doi"] >= 0.02 and r["close"] > r["ema200"]


def test_negative_controls():
    nm, day = CASES[1]
    fx = FX / f"s4_{nm}_{day}.csv"
    doi = META["prod_doi"][nm]
    assert prod_eval(fx, 0.019)["side"] is None                                           # OI build-up below 2 %
    assert prod_eval(fx, doi, "d.loc[d.index[-1],'volume']=d['volume'].iloc[-21:-1].mean()*1.4")["side"] is None   # volume < 1.5x
    assert prod_eval(fx, doi, "d.loc[d.index[-1],'close']=d['high'].iloc[-21:-1].max()*0.999")["side"] is None     # no breakout
    assert prod_eval(fx, doi, "d['time']=d['time']-(d['time'].iloc[-1]-pd.Timestamp('2026-11-23 09:15'))")["side"] is None  # expiry window
    r = prod_eval(fx, doi, "d.loc[d.index[:-25],['open','high','low','close']]=d.loc[d.index[:-25],['open','high','low','close']].values*1.3")
    assert r["side"] is None and r["close"] < r["ema200"] and r["close"] > r["hh"], r          # breakout, but below EMA200


def test_research_copy_parity():
    from research.mcxe005 import s4_research as R4
    muts = ["pass", "d.loc[d.index[-1],'volume']=d['volume'].iloc[-21:-1].mean()*1.4",
            "d.loc[d.index[-1],'close']=d['high'].iloc[-21:-1].max()*0.999"]
    for nm, day in CASES:
        for mu in muts:
            p = prod_eval(FX / f"s4_{nm}_{day}.csv", META["prod_doi"][nm], mu)
            d = load_fx(nm, day); exec(mu)
            r = R4.evaluate(d)
            assert p["side"] == r["side"], (nm, mu, p, r)
            for k in ("close", "hh", "vol_x", "doi", "ema200", "atr"):
                assert abs(p[k] - r[k]) < 1e-4 * max(1, abs(r[k])), (nm, k)
            sig, _ = R4.signals_vectorised(d)
            assert (sig[-1] == 1) == (r["side"] == "BUY")


def test_research_cannot_send_or_trade():
    bad = re.compile(r"(import\s+notify|from\s+notify|crude\.run\s+import\s+telegram|api\.telegram\.org|sendMessage|placeOrder|"
                     r"place_order|SmartConnect|requests\.post|from\s+alerts\s+import\s+run|import\s+runner|ALERTS_TELEGRAM\s*=\s*['\"]1)")
    hits = []
    for d in ("research/mcxe004", "research/mcxe005"):
        for p in (ROOT / d).rglob("*.py"):
            if "tests" in p.parts:
                continue
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if bad.search(line):
                    hits.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not hits, hits


def test_production_alert_suite_passes():
    out = subprocess.run([sys.executable, "-m", "alerts.tests.test_alerts"], cwd=baseline_dir(), capture_output=True, text=True,
                         timeout=900, env={"PATH": "/usr/bin:/bin:/usr/local/bin", "ALERTS_TELEGRAM": "0", "HOME": "/tmp"})
    assert out.returncode == 0 and "ALL" in out.stdout and "PASSED" in out.stdout, out.stdout[-2000:] + out.stderr[-2000:]


if __name__ == "__main__":
    n = 0
    for nm, fn in list(globals().items()):
        if nm.startswith("test_"):
            fn(); print("ok", nm); n += 1
    print(f"{n} preservation tests passed")

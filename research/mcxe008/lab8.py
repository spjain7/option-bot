"""MCXE-008 runner: reuses the MCXE-007 lab/engine (OOS masked) with its own register and an extra market IDX1H
(Angel front-stitched index futures 1-hour, NSE_FUT_INTRADAY window).  python research/mcxe008/lab8.py run N1 N2 ...
python research/mcxe008/lab8.py controls N1/L ..."""
import sys
import types
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe007 import lab7 as L, data7 as DA7  # noqa: E402
from research.mcxe005 import frames as FR  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402
from research.mcxe003 import bars as B  # noqa: E402
from research.mcxe008.exp8 import EXPS  # noqa: E402

D = ROOT / "research/mcxe008"
IDX = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"]
_C = {}


def idx1h():
    if "f" in _C:
        return _C["f"]
    from research.search import strategy_search as SS
    man = pd.read_csv(ROOT / "research/data/angel/manifest.csv")
    w = W.get("NSE_FUT_INTRADAY"); out = []
    for n in IDX:
        m = man[(man.exch == "NFO") & (man.name == n) & (man.interval == "ONE_HOUR") & (man.front_stitched.astype(str) == "True")]
        if m.empty:
            continue
        p = ROOT / "research/data/angel/NFO" / f"{m.symbol.iat[0]}_ONE_HOUR.csv"
        if not p.exists():
            print("missing 1h file:", n); continue
        d = pd.read_csv(p, parse_dates=["time"])
        d = d.sort_values("time").drop_duplicates("time")
        d = d[(d.time >= w["start"]) & (d.time < w["reference"] + pd.Timedelta(days=1))].reset_index(drop=True)
        sw = SS.switch_days(n, "NFO", d)
        f = d[["time", "open", "high", "low", "close", "volume"]].copy()
        f["switch"] = f.time.dt.normalize().isin(sw)
        f = B._finish(f, 60, intraday=True)
        day = f.time.dt.normalize()
        f["roll"] = f.groupby(day).switch.transform("max").astype(bool).values
        f["sig_ok"] = ~f.roll.values
        f.attrs.update(market="NSE_FUT", kind="IDX", name=n, tf=60, wkey="NSE_FUT_INTRADAY")
        out.append(f)
    _C["f"] = out
    return out


def frames(kind):
    return idx1h() if kind == "IDX1H" else DA7.frames(kind)


shim = types.SimpleNamespace(frames=frames, nifty=DA7.nifty, WKEY=dict(DA7.WKEY, IDX1H="NSE_FUT_INTRADAY"))
L.DA = shim; L.EXPS = EXPS; L.D = D; L.REGF = D / "EXPERIMENT_REGISTER.csv"

if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "run":
        L.main(args)
    elif cmd == "controls":
        for a in args:
            L.controls(a)

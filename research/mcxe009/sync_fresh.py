"""MCXE-009 fresh-data sync (research only, NO network, NO broker calls). Copies only what is newer than the local
research store from data the repo's existing jobs already collected:
  NSE F&O daily  : origin/research-nse-bhav  research/data/nse_bhav_raw/YYYYMMDD.zip  (scheduled nse-bhav.yml, NSE archive)
                   -> parsed with research.adapters.nse_stkfut_pit.parse -> research/data/nse_fut_pit/days/YYYYMMDD.csv.gz
  MCX daily      : origin/research-mcx-bhav  research/data/mcx_bhav/days/YYYYMMDD.csv  (scheduled mcx-bhav.yml, MCX site)
                   -> research/data/mcx_bhav/days/
  MCX intraday   : origin/research-data  research/data/angel/MCX/*_FIVE_MINUTE.csv + manifest  (manual research-data.yml,
                   Angel) -> research/data/angel/ only if the branch's last bar is newer than the local file's
Writes research/mcxe009/fresh_manifest.csv (source, branch commit, timeframe, instrument, expiry, first, last, rows).
python research/mcxe009/sync_fresh.py [--dry-run]"""
import datetime as dt
import io
import subprocess
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.adapters import nse_stkfut_pit as NF  # noqa: E402

DATA = ROOT / "research/data"
OUT = ROOT / "research/mcxe009"
MCX7 = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]


def git(*a, binary=False):
    r = subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode()[:300])
    return r.stdout if binary else r.stdout.decode()


def ls(branch, path):
    return [x for x in git("ls-tree", "-r", "--name-only", f"origin/{branch}", path).split("\n") if x]


def sync(dry=False):
    git("fetch", "-q", "origin", "research-nse-bhav", "research-mcx-bhav", "research-data")
    rows = []
    # NSE F&O
    sha = git("rev-parse", "--short", "origin/research-nse-bhav").strip()
    have = {p.name[:8] for p in (DATA / "nse_fut_pit/days").glob("*.csv.gz")}
    for p in ls("research-nse-bhav", "research/data/nse_bhav_raw"):
        d = Path(p).name[:8]
        if d in have or not d.isdigit():
            continue
        df = NF.parse(git("show", f"origin/research-nse-bhav:{p}", binary=True), dt.date(int(d[:4]), int(d[4:6]), int(d[6:])))
        if not dry:
            df.to_csv(DATA / "nse_fut_pit/days" / f"{d}.csv.gz", index=False)
        rows.append(dict(source="NSE F&O bhavcopy (nse-bhav.yml)", branch=f"research-nse-bhav@{sha}", timeframe="1D",
                         instrument="all FUTSTK/FUTIDX", expiry="all", first=d, last=d, rows=len(df), action="imported"))
    # MCX daily bhavcopy
    sha = git("rev-parse", "--short", "origin/research-mcx-bhav").strip()
    have = {p.name[:8] for p in (DATA / "mcx_bhav/days").glob("*.csv")}
    for p in ls("research-mcx-bhav", "research/data/mcx_bhav/days"):
        d = Path(p).name[:8]
        if d in have or not d.isdigit():
            continue
        raw = git("show", f"origin/research-mcx-bhav:{p}", binary=True)
        if not dry:
            (DATA / "mcx_bhav/days" / f"{d}.csv").write_bytes(raw)
        rows.append(dict(source="MCX bhavcopy (mcx-bhav.yml)", branch=f"research-mcx-bhav@{sha}", timeframe="1D",
                         instrument="all MCX contracts", expiry="all", first=d, last=d, rows=raw.count(b"\n") - 1, action="imported"))
    # Angel MCX 5-minute (front stitched)
    sha = git("rev-parse", "--short", "origin/research-data").strip()
    man = pd.read_csv(io.BytesIO(git("show", "origin/research-data:research/data/angel/manifest.csv", binary=True)))
    loc = pd.read_csv(DATA / "angel/manifest.csv")
    for n in MCX7:
        r = man[(man.exch == "MCX") & (man.name == n) & (man.interval == "FIVE_MINUTE") & (man.front_stitched.astype(str) == "True")]
        lr = loc[(loc.exch == "MCX") & (loc.name == n) & (loc.interval == "FIVE_MINUTE") & (loc.front_stitched.astype(str) == "True")]
        if r.empty:
            continue
        b_last, l_last = pd.Timestamp(r["last"].iat[0]), pd.Timestamp(lr["last"].iat[0]) if len(lr) else pd.Timestamp(0)
        act = "up to date (no newer bars on branch)"
        if b_last > l_last:
            act = "imported"
            if not dry:
                f = f"research/data/angel/MCX/{r.symbol.iat[0]}_FIVE_MINUTE.csv"
                (ROOT / f).write_bytes(git("show", f"origin/research-data:{f}", binary=True))
        rows.append(dict(source="Angel candles (research-data.yml, manual)", branch=f"research-data@{sha}", timeframe="5m",
                         instrument=n, expiry=r.expiry.iat[0], first=r["first"].iat[0], last=str(b_last), rows=int(r.bars.iat[0]), action=act))
    if not dry and any(x["action"] == "imported" and x["timeframe"] == "5m" for x in rows):
        loc = pd.concat([loc[~((loc.exch == "MCX") & (loc.interval == "FIVE_MINUTE") & loc.name.isin(MCX7))],
                         man[(man.exch == "MCX") & (man.interval == "FIVE_MINUTE") & man.name.isin(MCX7)]])
        loc.to_csv(DATA / "angel/manifest.csv", index=False)
    M = pd.DataFrame(rows)
    M.insert(0, "synced_at", pd.Timestamp.now(tz="Asia/Kolkata").strftime("%Y-%m-%d %H:%M IST"))
    p = OUT / "fresh_manifest.csv"
    M = pd.concat([pd.read_csv(p), M]) if p.exists() else M
    if not dry:
        M.to_csv(p, index=False)
    return M


def latest():
    nse = max(p.name[:8] for p in (DATA / "nse_fut_pit/days").glob("*.csv.gz"))
    mcx = max(p.name[:8] for p in (DATA / "mcx_bhav/days").glob("*.csv"))
    loc = pd.read_csv(DATA / "angel/manifest.csv")
    m5 = loc[(loc.exch == "MCX") & (loc.interval == "FIVE_MINUTE") & (loc.front_stitched.astype(str) == "True")]["last"].min()
    return dict(nse_fo_daily=nse, mcx_daily=mcx, mcx_5m_min_last=m5)


if __name__ == "__main__":
    M = sync(dry="--dry-run" in sys.argv)
    print(M.tail(20).to_string(index=False)); print("local latest:", latest())

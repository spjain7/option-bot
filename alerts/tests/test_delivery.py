"""6-Nov: undelivered CALL alerts older than 30 minutes are dropped (with a notice), others re-sent; delivery counts kept.
python alerts/tests/test_delivery.py"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
d = tempfile.mkdtemp(); os.environ["ALERTS_STATE_DIR"] = d; os.environ["ALERTS_TELEGRAM"] = "1"
from alerts import run as R  # noqa: E402

R.GAP_SEC = 0
R.SD, R.PENDING, R.OUTBOX = Path(d), Path(d) / "pending.json", Path(d) / "outbox.json"
call = "🟢 BUY  GOLD FUT\nEntry   : 100\nSL      : 98"
R.PENDING.write_text(json.dumps([dict(m=call, t=time.time() - 3600), dict(m="📊 report", t=time.time() - 3600),
                                 dict(m=call.replace("GOLD", "SILVER"), t=time.time() - 60), "legacy plain text"]))
R.OUTBOX.write_text(json.dumps(dict(messages=["new message"])))
sent = []
import crude.run as CR  # noqa: E402
CR.telegram = lambda m: (sent.append(m) or True, "ok")
R.flush()
assert not any("GOLD" in m for m in sent), "stale GOLD call must not be delivered"
assert any("SILVER" in m for m in sent) and "📊 report" in sent and "legacy plain text" in sent and "new message" in sent
assert any("dropped" in m for m in sent), "a notice about the dropped stale call"
dv = json.loads((Path(d) / "delivery.json").read_text())
day = list(dv)[0]
assert dv[day]["stale_dropped"] == 1 and dv[day]["failed"] == 0 and dv[day]["sent"] == len(sent)
print("✅ stale call dropped with a notice, fresh pending + reports re-sent, delivery counts recorded")

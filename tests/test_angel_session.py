"""10-Nov: one Angel login per job (shared session) instead of one per engine process per scan; safe fallbacks.
python tests/test_angel_session.py  (offline – a fake SmartConnect, no credentials, no network)"""
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(ANGEL_API_KEY="k", ANGEL_CLIENT_ID="C1", ANGEL_PIN="0", ANGEL_TOTP_SECRET="JBSWY3DPEHPK3PXP")
import angel as A  # noqa: E402

ok = 0
LOG = dict(logins=0, profiles=0)


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


class Fake:
    valid = {"good"}

    def __init__(self, api_key=None):
        self.access_token = self.refresh_token = self.feed = self.userId = None

    def generateSession(self, c, p, t):
        LOG["logins"] += 1
        tok = f"jwt{LOG['logins']}"; Fake.valid.add(tok)
        self.access_token, self.refresh_token, self.feed = tok, "r" + tok, "f" + tok
        return dict(status=True, data=dict(jwtToken="Bearer " + tok, refreshToken="r" + tok, feedToken="f" + tok))

    def setAccessToken(self, x): self.access_token = x
    def setRefreshToken(self, x): self.refresh_token = x
    def setFeedToken(self, x): self.feed = x
    def setUserId(self, x): self.userId = x

    def getProfile(self, r):
        LOG["profiles"] += 1
        return dict(status=self.access_token in Fake.valid, data={})

    def getCandleData(self, p):
        if self.access_token not in Fake.valid:
            return dict(status=False, message="Invalid Token", errorcode="AG8001", data=None)
        return dict(status=True, data=[["2026-11-10T09:15:00+05:30", 1, 2, 0.5, 1.5, 10]])


sys.modules["SmartApi"] = types.SimpleNamespace(SmartConnect=Fake)
d = Path(tempfile.mkdtemp())
A.Angel.SESSION_FILE = d / "angel_session.json"
A.CACHE = d

a1 = A.Angel()
check(LOG["logins"] == 1 and not a1.reused and A.Angel.SESSION_FILE.exists(), "first process logs in and saves the session")
check(oct(A.Angel.SESSION_FILE.stat().st_mode)[-3:] == "600" and "Bearer" not in A.Angel.SESSION_FILE.read_text(), "session file mode 600")
a2 = A.Angel()
check(LOG["logins"] == 1 and a2.reused and a2.jwt == a1.jwt and a2.feed == a1.feed, "second process re-uses it (no new login)")
a3 = A.Angel(fresh=True)
check(LOG["logins"] == 2 and not a3.reused, "fresh=True (collector) always logs in")
s = json.loads(A.Angel.SESSION_FILE.read_text()); s["t"] = time.time() - 6 * 3600; A.Angel.SESSION_FILE.write_text(json.dumps(s))
A.Angel(); check(LOG["logins"] == 3, "session older than 5 h -> new login")
s = json.loads(A.Angel.SESSION_FILE.read_text()); s["day"] = "2026-01-01"; A.Angel.SESSION_FILE.write_text(json.dumps(s))
A.Angel(); check(LOG["logins"] == 4, "session from another day -> new login")
Fake.valid.discard(json.loads(A.Angel.SESSION_FILE.read_text())["jwt"])
A.Angel(); check(LOG["logins"] == 5, "saved session rejected by the profile check -> new login")
A.Angel.SESSION_FILE.write_text("{bad json"); A.Angel(); check(LOG["logins"] == 6, "unreadable session file -> new login")
os.environ["ANGEL_SESSION_REUSE"] = "0"; A.Angel(); check(LOG["logins"] == 7, "ANGEL_SESSION_REUSE=0 -> old behaviour (login every time)")
os.environ.pop("ANGEL_SESSION_REUSE")
b = A.Angel(); b._cache = {}; b.HIST_GAP = 0
Fake.valid.discard(b.api.access_token)                      # token invalidated during the day
n0 = LOG["logins"]
r = b._call(b.api.getCandleData, {"x": 1})
check(r is not None and LOG["logins"] == n0 + 1, "'Invalid Token' reply -> one fresh login and the call is retried")
print(f"{ok} Angel session checks passed")

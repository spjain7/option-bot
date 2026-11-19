"""7-Nov-2026: manual research jobs use the SAME Angel API key as the live market loop. On 6-Nov research-data.yml ran
15:15-20:16 IST while the loop was scanning (its comment said it could never overlap: false – it is in the old bot's
concurrency group, not market-loop's). This guard stops such a job while the loop runs (Mon-Fri 08:30-00:30 IST), so it
never takes the live bot's request quota. Override: FORCE=1 (research-data.yml input 'force').  No API call, no secrets."""
import os
import sys
from datetime import datetime, timedelta, timezone


def busy(now_ist):
    """True while the market loop may be running: weekday 08:30-23:59, or 00:00-00:30 after a weekday session."""
    hm = now_ist.hour * 60 + now_ist.minute
    if now_ist.weekday() < 5 and hm >= 8 * 60 + 30:
        return True
    return hm < 30 and (now_ist - timedelta(days=1)).weekday() < 5


if __name__ == "__main__":
    now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    if busy(now) and os.getenv("FORCE", "") != "1":
        print(f"::error::{now:%a %H:%M} IST – live market loop hours (Mon-Fri 08:30-00:30 IST). This job shares the Angel "
              "API key with the live bot; run it after 00:30 IST or at the weekend (or set force=1 knowingly).")
        sys.exit(1)
    print(f"{now:%a %H:%M} IST – outside live loop hours" + (" (FORCE)" if busy(now) else "") + " – OK")

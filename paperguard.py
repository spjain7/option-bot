"""Last-line guard for every Telegram sender (4-Nov-2026): text carrying the PAPER_ONLY marker is never sent.
Paper strategies (alerts/paper.py) are recorded, not alerted; this makes that true even if some engine tries to send one."""
MARKER = "PAPER_ONLY"
SHADOW = "SHADOW_ONLY"                # shadow calls (alerts/strategies.py) are logged, never sent


def blocked(text):
    """True if the text must not be sent (and prints why)."""
    if MARKER in str(text or "") or SHADOW in str(text or ""):
        print("::error::blocked a PAPER_ONLY / SHADOW_ONLY message from Telegram (paper and shadow calls are never sent)")
        return True
    return False

"""Last-line guard for every Telegram sender (4-Nov-2026): text carrying the PAPER_ONLY marker is never sent.
Paper strategies (alerts/paper.py) are recorded, not alerted; this makes that true even if some engine tries to send one."""
MARKER = "PAPER_ONLY"


def blocked(text):
    """True if the text must not be sent (and prints why)."""
    if MARKER in str(text or ""):
        print(f"::error::blocked a {MARKER} message from Telegram (paper strategies are never sent)")
        return True
    return False

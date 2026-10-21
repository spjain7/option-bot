# Crude Oil PAPER engine – runbook

## Is it running?
1. Open GitHub → **Actions** → **Crude Oil PAPER engine**. Scheduled runs happen every 15 minutes, Mon–Fri, 08:32 → 00:17 IST.
2. A green run means the workflow completed. To see whether it got **fresh market data**, open the run's **Summary**:
   - "✅ fresh market data" – it did.
   - "⚪ market closed / no fresh data" – outside the session, or no fresh candles.
   - "❌ FAILED" – something broke.
3. The health line in Telegram shows how late the run started after its slot, and how the previous run ended.

## Manual health check (never opens positions)
Go to Actions → Crude Oil PAPER engine → **Run workflow**, then set mode `health` and telegram `1`.

## Locks and limits
When a limit is breached, the engine stops **new entries only**. Open positions keep their own stop, target, square-off and roll rules.

| Lock | Trigger | How it clears |
|---|---|---|
| Stale data | No fresh 15-min candle, or quote older than 5 min | Automatically, once data is fresh |
| Data suspect | Misaligned or duplicate candles, a missing recent candle, or price more than 3 ATR from the last candle | Automatically |
| Daily loss (per engine) | Realised + open loss today ≤ −1% of equity | Next session |
| Account daily loss | Both engines together ≤ −1.5% | Next session |
| Open-risk cap | Combined initial risk would exceed 0.5% of equity | When positions close |
| **Drawdown lock** | Equity incl. open P&L 5% below its peak | **Manual only** (see below) |
| Expiry | Within 4 trading days of expiry | Engine moves to the next contract; positional trades are closed at the roll |

### Clearing the drawdown lock (after review)
```
git fetch origin crude-state && git checkout crude-state
python - <<'P'
import json; f = "crude/state.json"; s = json.load(open(f)); s.pop("dd_lock", None); s["peak_equity"] = s["capital"] + s["realized"]; json.dump(s, open(f, "w"), indent=1)
P
git commit -am "unlock drawdown after review" && git push origin crude-state
```

## Restart / recovery
- **State** lives on branch `crude-state`: `crude/state.json` holds positions, ledger and locks; `crude/scan_log.jsonl` is the audit trail of every decision.
- **Corrupt or missing state:** the run stops, sends a Telegram alert, and never resets on its own.
  - To restore, revert `crude-state` to the last good commit with `git log crude-state`, then `git revert`.
  - Only delete the branch if you deliberately want a **new** paper account.
- **State push failed:** Telegram says "STATE SAVE FAILED" and nothing from that run counts. The next run starts from the last pushed state.
- **Telegram failed:** the run is marked failed. The next health line shows "previous run: failure".
- **API login failed:** the run fails and sends "API AUTHENTICATION FAILED". Check the `ANGEL_*` secrets and whether the TOTP secret has changed.
- **Stop everything:** set `ENABLED = False` in `crude/config.py`, or Actions → workflow → "Disable workflow".

## What this engine never does
It never places, modifies or cancels a broker order; the code to do so does not exist in `crude/`. It never writes research results into the paper ledger.

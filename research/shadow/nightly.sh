#!/usr/bin/env bash
# Nightly shadow run (SHADOW ONLY – no alerts, no orders, nothing on main). Run from a clone of spjain7/option-bot:
#   bash research/shadow/nightly.sh
# Uses branch exp/cash-equity-engine for the code and keeps the ledgers / reports on branch shadow-state.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git fetch -q origin exp/cash-equity-engine
git checkout -q -f -B exp/cash-equity-engine origin/exp/cash-equity-engine
python -c "import pandas, requests, numpy" 2>/dev/null || pip install -q pandas numpy requests --break-system-packages
WT=/tmp/shadow-state; rm -rf "$WT"; git worktree prune
if git ls-remote --exit-code --heads origin shadow-state >/dev/null 2>&1; then
  git fetch -q origin shadow-state && git worktree add -q "$WT" FETCH_HEAD
else
  git worktree add -q --detach "$WT" && (cd "$WT" && git checkout -q --orphan shadow-state && git rm -rqf --ignore-unmatch .)
fi
mkdir -p "$WT/shadow"
python -m research.shadow.run --state "$WT/shadow" ${ASOF:+--asof "$ASOF"}
cd "$WT" && git add shadow && (git diff --cached --quiet || git commit -qm "shadow run $(TZ=Asia/Kolkata date +%F_%H%M) IST") \
  && git push -q origin HEAD:refs/heads/shadow-state && echo "saved to shadow-state"

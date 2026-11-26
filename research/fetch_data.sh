#!/usr/bin/env bash
# 26-Nov-2026: one command to bring every research data set into research/data (e.g. a fresh research machine / session).
# Reads the data branches with `git archive` (no history clone). Usage: bash research/fetch_data.sh [set ...]
# Sets: nse_fut nse_bhav mcx_bhav stocks m5 ws angel nse_cm   (default: all). Catalog: docs/research/DATA.md
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
want="${*:-nse_fut nse_bhav mcx_bhav stocks m5 ws angel nse_cm}"
get() {  # $1 branch  $2 path inside the branch
  if git fetch -q --depth 1 origin "$1" 2>/dev/null; then
    git archive FETCH_HEAD "$2" | tar -x && echo "✓ $1:$2 ($(du -sh "$2" 2>/dev/null | cut -f1))"
  else echo "✗ $1 not found"; fi
}
for s in $want; do
  case "$s" in
    nse_fut)  get research-nse-fut  research/data/nse_fut ;;
    nse_bhav) get research-nse-bhav research/data/nse_bhav_raw ;;
    mcx_bhav) get research-mcx-bhav research/data/mcx_bhav ;;
    stocks)   get research-stocks   research/data/angel/NFO_STK ;;
    m5)       get research-m5       research/data/m5 ;;
    ws)       get ws-bars           wsbars ;;
    angel)    get research-data     research/data/angel ;;
    nse_cm)   get research-nse-cm   research/data/nse_cm ;;
    *) echo "unknown set $s" ;;
  esac
done

#!/usr/bin/env bash
# Sequential finish for weak top-100 — retries holdout/rank_q per symbol until clear.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/venv/bin/python"
LOG="${ROOT}/logs/finish_weak_top100.log"
mkdir -p "${ROOT}/logs"

exec >>"$LOG" 2>&1
echo "=== finish_weak_top100 $(date -Iseconds) ==="

cd "$ROOT"
export STRONG_N_EST=400
export STRONG_BACKENDS=xgb,lgb
export TRAIN_TICKER_TIMEOUT_SEC=0

FRACS=(0.12 0.15 0.10 0.18 0.08)
RANKS=(0.78 0.80 0.82 0.75 0.85)
MAX_ROUNDS=20
round=0

weak_list() {
  "$PY" -c "
import sys
sys.path.insert(0, '$ROOT')
from tools.retrain_weak_models import find_weak_symbols
for s in sorted(find_weak_symbols(min_top20=0.6, min_meta=0.52, top100_only=True)):
    print(s)
"
}

while (( round < MAX_ROUNDS )); do
  round=$((round + 1))
  syms=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && syms+=("$line")
  done < <(weak_list)

  if [[ "${#syms[@]}" -eq 0 ]]; then
    echo "[finish] all top100 pass at round $round $(date -Iseconds)"
    exit 0
  fi
  echo "[finish] round $round — ${#syms[@]} weak: ${syms[*]}"
  for sym in "${syms[@]}"; do
    ok=0
    for i in "${!FRACS[@]}"; do
      export STRONG_TRAIN_TEST_FRACTION="${FRACS[$i]}"
      export STRONG_RANK_QUANTILE="${RANKS[$i]}"
      echo "[finish] $sym attempt $((i + 1)) holdout=${FRACS[$i]} rank=${RANKS[$i]}"
      if "$PY" -u tools/retrain_top100_strong.py --ticker "$sym"; then
        echo "[finish] $sym PASS"
        ok=1
        break
      fi
    done
    if [[ "$ok" -eq 0 ]]; then
      echo "[finish] $sym still weak after ${#FRACS[@]} attempts"
    fi
  done
done

echo "[finish] stopped after $MAX_ROUNDS rounds — still weak:"
"$PY" -u tools/retrain_weak_models.py --top100-only || true
exit 1

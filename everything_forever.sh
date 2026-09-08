#!/usr/bin/env bash
# 24/7: keep-awake + paper/HFT + each timeframe's own top-K + trainers forever.
# Does not flatten, does not shrink the universe, does not delete models.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
exec ./run_all.sh forever "$@"

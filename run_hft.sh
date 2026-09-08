#!/usr/bin/env bash
#
# Launcher for the FATE_AlgoBot HFT (Node.js/TypeScript) module.
#
#   ./run_hft.sh build              # compile TS → dist/
#   ./run_hft.sh test               # hot-path smoke tests
#   ./run_hft.sh earnings           # earnings sub-100ms reaction loop
#   ./run_hft.sh obi-tape           # OBI + Tape Velocity sub-10ms loop
#   ./run_hft.sh earnings:perf      # earnings w/ V8 GC-quieted flags
#   ./run_hft.sh obi-tape:perf      # OBI/Tape w/ V8 GC-quieted flags
#   ./run_hft.sh both:perf          # both loops in parallel (recommended)
#
# Cramer is *deliberately not used* in the HFT module — these are the sub-second
# fluctuation trades that the user asked to keep clean of long-form signals.
#
set -euo pipefail
cd "$(dirname "$0")/hft"

# Make sure Homebrew Node is on PATH even from non-login shells.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v node >/dev/null 2>&1; then
    echo "node not found — install with: brew install node" >&2
    exit 1
fi

cmd="${1:-earnings}"

case "$cmd" in
    install)
        npm install --no-audit --no-fund
        ;;
    build)
        npm install --no-audit --no-fund >/dev/null
        npm run build
        ;;
    test)
        npm test
        ;;
    earnings|obi-tape|earnings:perf|obi-tape:perf)
        [[ -d dist ]] || npm run build
        exec npm run "$cmd"
        ;;
    both:perf)
        [[ -d dist ]] || npm run build
        npm run earnings:perf &
        EPID=$!
        npm run obi-tape:perf &
        OPID=$!
        trap "kill $EPID $OPID 2>/dev/null || true" INT TERM
        wait
        ;;
    *)
        echo "Unknown command: $cmd" >&2
        echo "Usage: $0 [install|build|test|earnings|obi-tape|earnings:perf|obi-tape:perf|both:perf]" >&2
        exit 1
        ;;
esac

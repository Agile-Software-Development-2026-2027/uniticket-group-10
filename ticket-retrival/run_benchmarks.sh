#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$#" -eq 0 ]; then
  echo "Usage: bash run_benchmarks.sh path/to/prototype.py [benchmark options]" >&2
  exit 2
fi
PROTOTYPE="$1"
shift
uv run python benchmark.py --prototype "$PROTOTYPE" "$@"

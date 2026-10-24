#!/usr/bin/env bash
set -e

DEVICE="cpu" # or mps
PROTOTYPE="./retrival/prototypes"

# Benchmark con configurazione base
# Forse non è l'approccio migliore...
#uv run python benchmark.py --prototype $PROTOTYPE/experiments/embeddinggemma-2.py --device $DEVICE
#uv run python benchmark.py --prototype retrival/prototypes/bm25.py --k1 1.2 --b 0.5 --device $DEVICE
uv run python benchmark.py --prototype $PROTOTYPE/dense.py --device $DEVICE

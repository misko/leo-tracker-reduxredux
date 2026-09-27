#!/usr/bin/env bash
set -euo pipefail
repo=/home/mouse9911/gits/leo-adaptive-position-deploy
out=/srv/bulk/leo/experiments/ds6-fast-transfer
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
case "${1:-}" in
  test) "$repo/.venv/bin/python" -m pytest -q "$repo/reports/2026_09_27_ds6_fast_transfer/test_run.py" ;;
  infer) "$repo/.venv/bin/python" "$repo/reports/2026_09_27_ds6_fast_transfer/run.py" infer --output "$out/inference.json" ;;
  postseal) "$repo/.venv/bin/python" "$repo/reports/2026_09_27_ds6_fast_transfer/run.py" postseal --inference "$out/inference.json" --output "$out/postseal.json" --png "$out/summary.png" ;;
  *) echo "usage: $0 {test|infer|postseal}" >&2; exit 2 ;;
esac

#!/usr/bin/env bash
set -euo pipefail
repo=/home/mouse9911/gits/leo-adaptive-position-deploy
runner="$repo/reports/2026_09_27_ds5_exact_summary/build.py"
bulk=/srv/bulk/leo/experiments/ds5-all-methods
out=/srv/bulk/leo/experiments/ds5-exact-summary
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
case "${1:-}" in
  test) "$repo/.venv/bin/python" -m pytest -q "$repo/reports/2026_09_27_ds5_exact_summary/test_build.py" ;;
  inference) "$repo/.venv/bin/python" "$runner" inference --cell "$bulk/cell-batched/stages/full-2km-00/aggregate.json" --crossfit "$bulk/crossfit/stages/full-2km-00/aggregate-crossfit-exact.json" --output "$out/inference.json" ;;
  postseal) "$repo/.venv/bin/python" "$runner" postseal --inference "$out/inference.json" --output "$out/postseal.json" --png "$out/exact-summary.png" ;;
  *) echo "usage: $0 {test|inference|postseal}" >&2; exit 2 ;;
esac

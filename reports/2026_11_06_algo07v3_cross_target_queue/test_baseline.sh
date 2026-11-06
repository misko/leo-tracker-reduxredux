#!/bin/sh
# Reproduce historical-tool failures with all six candidate modules hidden.
set -eu
test "$#" -eq 3 || exit 2
exec unshare --mount --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
for module in leo/analysis/localization_v3/predictive_annotation.py \
  leo/analysis/localization_v3/recovery_controller.py \
  leo/application/localization_v3.py leo/application/localization_v3_engine.py \
  leo/operations/localization_v3_parallel.py leo/operations/localization_v3_job.py; do
  mount --bind "$1/$module" "src/$module"
  mount -o remount,bind,ro "src/$module"
done
mount --bind "$1/../baseline-tools/probe_algo07v3_branch_queue.py" \
  tools/probe_algo07v3_branch_queue.py
mount -o remount,bind,ro tools/probe_algo07v3_branch_queue.py
for name in test_probe_algo07v3_branch_queue.py test_probe_algo07v3_initial_cache_models.py; do
  mount --bind "$1/../baseline-tests/$name" "tests/tools/$name"
  mount -o remount,bind,ro "tests/tools/$name"
done
exec env PYTHONPATH=src:tools:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  taskset -c 4 "$2" -B -m pytest -q \
  tests/tools/test_probe_algo07v3_branch_queue.py \
  tests/tools/test_probe_algo07v3_initial_cache_models.py --junitxml="$3"
PRIVATE

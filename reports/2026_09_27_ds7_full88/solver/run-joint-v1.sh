#!/bin/sh
set -eu

test "$#" -eq 2
final_input=$1
final_input_sha256=$2
test "$(sha256sum "$final_input" | cut -d ' ' -f 1)" = "$final_input_sha256"
test "$(awk '/MemAvailable:/ { print $2 * 1024 }' /proc/meminfo)" -ge 17179869184
test ! -e /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_full88/solver/joint-v1

exec sudo -n prlimit --as=8589934592 -- \
  timeout --signal=TERM --kill-after=10s 1920s \
  nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  /opt/leo-tracker/current-api/.venv/bin/python \
  /home/mouse9911/gits/leo-tracker-reduxredux/tools/ds7_eval.py run \
  --plan /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json \
  --inputs "$final_input" \
  --arm /home/mouse9911/gits/leo-tracker-reduxredux/config/ds7/baseline-wave4-batched-ready-v1.json \
  --output /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_full88/solver/joint-v1 \
  --max-seconds 1800 --unit-seconds 1800 --unit full88

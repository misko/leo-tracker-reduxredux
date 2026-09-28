#!/usr/bin/env bash
set -eu
cd /home/mouse9911/gits/leo-tracker-reduxredux
report=reports/2026_09_28_rx_beam_crossing
output="$report/corrected"
test -f "$output/launch.json"
test ! -e "$output/result.json"
test ! -e "$output/resources.txt"
set +e
sudo -n /usr/bin/time -v -o "$output/resources.txt" \
  /usr/bin/timeout --signal=TERM --kill-after=5s 300s \
  /usr/bin/prlimit --as=4294967296 \
  /usr/bin/nice -n 19 /usr/bin/env \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /opt/leo-tracker/current-api/.venv/bin/python tools/ds7_beam_crossing_eval.py \
  --contract "$report/input-audit/CONDITIONAL-INPUT-CONTRACT.json" \
  --output "$output/result.json" > "$output/terminal.log" 2>&1
result_code=$?
printf '%s\n' "$result_code" > "$output/exit-code.txt"
exit "$result_code"

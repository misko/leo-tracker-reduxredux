#!/bin/bash
set -euo pipefail

root=/home/mouse9911/gits/leo-adaptive-position-deploy
python="$root/.venv/bin/python"
run="$root/reports/2026_09_25_ds3_iteration32_session_nominal_closure/run.py"
evaluate="$root/reports/2026_09_25_ds3_iteration32_session_nominal_closure/evaluate_postseal.py"
lock=/var/tmp/leo-ds3-backfill-two-worker.lock

cd "$root"
/usr/bin/flock -x "$lock" "$python" "$run" infer --workers 2
/usr/bin/flock -x "$lock" "$python" "$run" replay --workers 2
"$python" "$run" qualify
"$python" "$evaluate" \
  --reference-latitude 37.84903264307456 \
  --reference-longitude -122.4856541910174

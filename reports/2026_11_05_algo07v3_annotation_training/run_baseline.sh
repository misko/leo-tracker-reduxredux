#!/bin/sh
# Apply either declared training-scheduler snapshot in a private namespace.
set -eu
test "$#" -eq 7 || {
  echo 'usage: SOURCES BUNDLE OUTPUT_PARENT PYTHON REQUEST TIMEOUT CPUS' >&2
  exit 2
}
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
for module in leo/analysis/localization_v3/prediction.py \
              leo/analysis/localization_v3/predictive_annotation.py \
              leo/analysis/localization_v3/recovery_controller.py \
              leo/application/localization_v3.py \
              leo/application/localization_v3_engine.py \
              leo/operations/localization_v3_parallel.py \
              leo/operations/localization_v3_job.py; do
  mount --bind "$1/$module" "src/$module"
  mount -o remount,bind,ro "src/$module"
done
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

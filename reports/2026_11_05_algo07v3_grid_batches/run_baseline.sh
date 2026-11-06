#!/bin/sh
# Either frozen grid implementation, in a private read-only namespace.
set -eu
test "$#" -eq 7 || exit 2
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
for module in leo/analysis/position_grid.py \
              leo/presentation/localization_v3.py \
              leo/application/localization_v3_engine.py \
              leo/operations/localization_v3_parallel.py \
              leo/operations/localization_v3_job.py; do
  mount --bind "$1/$module" "src/$module"
  mount -o remount,bind,ro "src/$module"
done
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

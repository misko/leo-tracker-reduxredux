#!/bin/sh
# Read-only overlays of the two changed runtime modules; common helper is bound.
set -eu
test "$#" -eq 7 || exit 2
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
for module in leo/analysis/localization_v3/recovery_inclusion.py \
  leo/analysis/localization_v3/recovery_controller.py; do
  mount --bind "$1/$module" "src/$module"
  mount -o remount,bind,ro "src/$module"
done
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

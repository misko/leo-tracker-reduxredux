#!/bin/sh
# External original-kernel reference; baseline source is read-only in its namespace.
set -eu
test "$#" -eq 7
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
module=leo/analysis/localization_v3/joint_density.py
mount --bind "$1/$module" "src/$module"
mount -o remount,bind,ro "src/$module"
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

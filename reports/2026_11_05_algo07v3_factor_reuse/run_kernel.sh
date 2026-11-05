#!/bin/sh
# External paired benchmark: replace only the numerical kernel inside a private
# namespace. The checkout and production installation remain unchanged.
set -eu
test "$#" -eq 7 || {
  echo 'usage: KERNEL_SOURCE BUNDLE OUTPUT_PARENT PYTHON REQUEST TIMEOUT CPUS' >&2
  exit 2
}
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
mount --bind "$1" src/leo/analysis/localization_v3/hierarchical.py
mount -o remount,bind,ro src/leo/analysis/localization_v3/hierarchical.py
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

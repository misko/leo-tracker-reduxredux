#!/bin/sh
# External comparison only. The historical kernel is mounted only in this
# private namespace; the host checkout and production services never change.
set -eu
test "$#" -eq 7 || {
  echo 'usage: KERNEL BUNDLE OUTPUT_PARENT PYTHON REQUEST TIMEOUT CPU' >&2
  exit 2
}
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
mount --bind "$1" src/leo/analysis/localization_v3/hierarchical.py
mount -o remount,bind,ro src/leo/analysis/localization_v3/hierarchical.py
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

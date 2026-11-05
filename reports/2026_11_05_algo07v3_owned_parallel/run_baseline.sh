#!/bin/sh
# External serial control: bind the previous job composition only inside a
# private namespace. Both sides use the current numerical implementation.
set -eu
test "$#" -eq 7 || {
  echo 'usage: JOB_SOURCE BUNDLE OUTPUT_PARENT PYTHON REQUEST TIMEOUT CPUS' >&2
  exit 2
}
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
mount --bind "$1" src/leo/operations/localization_v3_job.py
mount -o remount,bind,ro src/leo/operations/localization_v3_job.py
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

#!/bin/sh
# External comparison only: restore the three pre-optimization v3 modules in
# a private namespace. Production and the shared checkout remain unchanged.
set -eu
test "$#" -eq 7 || {
  echo 'usage: SOURCES BUNDLE OUTPUT_PARENT PYTHON REQUEST TIMEOUT CPUS' >&2
  exit 2
}
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
for module in hierarchical position discovery_likelihood; do
  target="src/leo/analysis/localization_v3/$module.py"
  mount --bind "$1/baseline-$module.py" "$target"
  mount -o remount,bind,ro "$target"
done
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

#!/bin/sh
# Frozen screen and phase geometry in a private read-only namespace.
set -eu
test "$#" -eq 7 || exit 2
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
for module in leo/analysis/localization_v3/residual_screen.py leo/analysis/research/orbit_phase_geometry.py; do
    mount --bind "$1/$module" "src/$module"
    mount -o remount,bind,ro "src/$module"
done
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

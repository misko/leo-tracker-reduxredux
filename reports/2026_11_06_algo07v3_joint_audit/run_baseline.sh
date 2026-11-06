#!/bin/sh
# Frozen serial-audit reference in a private read-only mount namespace.
set -eu
test "$#" -eq 7
exec unshare --mount --net --propagation private sh -s -- "$@" <<'PRIVATE'
set -eu
for module in leo/analysis/localization_v3/joint_recovery.py \
    leo/analysis/localization_v3/recovery_controller.py \
    leo/analysis/localization_v3/numerical_recovery.py \
    leo/application/localization_v3.py \
    leo/application/localization_v3_engine.py
do
    mount --bind "$1/$module" "src/$module"
    mount -o remount,bind,ro "src/$module"
done
exec taskset -c "$7" sh tools/qualify_algo07v3_cli.sh "$2" "$3" "$4" "$5" run "$6"
PRIVATE

#!/bin/sh
# Reproduce the exact measured candidate in a private source-overlay namespace.
set -eu
test "$#" -eq 5 || {
    echo 'usage: PYTHON REQUEST NATIVE_COMPARISON FRESH_OUTPUT TIMEOUT_SECONDS' >&2
    exit 2
}
report=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec unshare --mount --net --propagation private sh -s -- "$report" "$@" <<'PRIVATE'
set -eu
"$2" -B - "$1" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
for name, sha in json.loads((root / 'candidate-sources.json').read_bytes()).items():
    source = (root / 'candidate-src' / name).resolve()
    assert source.is_relative_to((root / 'candidate-src').resolve())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == sha, name
PY
for module in leo/analysis/localization_v3/joint_recovery.py \
    leo/analysis/localization_v3/recovery_controller.py \
    leo/analysis/localization_v3/numerical_recovery.py \
    leo/application/localization_v3.py \
    leo/application/localization_v3_engine.py
do
    mount --bind "$1/candidate-src/$module" "src/$module"
    mount -o remount,bind,ro "src/$module"
done
exec env PYTHONPATH=src:tools:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    timeout --kill-after=5s "$6"s taskset -c 0,1,2 "$2" -B \
    tools/probe_algo07v3_joint_audit.py --request "$3" --native-comparison "$4" --output "$5"
PRIVATE

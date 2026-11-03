#!/bin/sh
set -eu

base=${1:-/tmp/leo-server-graph-compatibility-host}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../../../../.." && pwd)
pow_out="$base/pow"
lexeme_out="$base/lexeme"
pipeline_out="$base/pipeline"
tracking="$root/reports/2026_09_30_native_adaptive_deployment/tracking"
reference_python=${LEO_REFERENCE_PYTHON:-/var/tmp/leo-arm-realtime-publication/.venv/bin/python}

"$here/test_compatibility_stack.sh" host "$base/stack"
pow_out="$base/stack/pow"
lexeme_out="$base/stack/lexeme"
"$lexeme_out/build-server-graph-compat" \
    "$tracking/graph-candidates.tsv" "$pow_out/actual.tsv" "$base/recomputed-graph.tsv"
cmp "$tracking/graph-candidates.tsv" "$base/recomputed-graph.tsv"

"$root/native/adaptive/pipeline/build.sh" host "$pipeline_out"
"$pipeline_out/leo-adaptive-pipeline" \
    "$tracking/candidates.tsv" "$base/recomputed-graph.tsv" \
    "$tracking/native-e2.loc1" "$base/recomputed.loc1"
"$reference_python" "$here/compare_recomputed_partitions.py" \
    "$tracking/oracle-tracks.json" "$base/recomputed-graph.tsv" \
    "$base/recomputed.loc1.tracks.tsv" > "$base/comparison.json"
cat "$base/comparison.json"

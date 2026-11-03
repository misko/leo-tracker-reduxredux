#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../../../.." && pwd)"
build="${1:-/tmp/leo-location-stencil-research-host}"
fixture="${2:-$root/reports/2026_09_30_native_adaptive_deployment/tracking/native-e2.loc1}"
output="${3:-$build/abba}"
sequences="${4:-4}"
mkdir -p "$output"

control="$build/leo-location-control"
candidate="$build/leo-location-stencil-research"
for path in "$control" "$candidate" "$fixture"; do
  if [[ ! -r "$path" ]]; then
    echo "missing input: $path" >&2
    exit 2
  fi
done
if [[ ! "$sequences" =~ ^[1-9][0-9]*$ ]] || (( sequences > 8 )); then
  echo "sequences must be in 1..8" >&2
  exit 2
fi

printf 'sequence\tposition\timplementation\twall_ns\toutput_sha256\n' >"$output/timings.tsv"
run_index=0
run_one() {
  local sequence="$1"
  local position="$2"
  local implementation="$3"
  local binary="$control"
  if [[ "$implementation" == candidate ]]; then
    binary="$candidate"
  fi
  local result="$output/result-$(printf '%02d' "$run_index")-$implementation.json"
  local before after digest
  before="$(date +%s%N)"
  "$binary" score "$fixture" 1 >"$result"
  after="$(date +%s%N)"
  digest="$(sha256sum "$result" | awk '{print $1}')"
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$sequence" "$position" "$implementation" "$((after - before))" "$digest" \
    >>"$output/timings.tsv"
  run_index=$((run_index + 1))
}

for ((sequence = 0; sequence < sequences; ++sequence)); do
  if (( sequence % 2 == 0 )); then
    order=(control candidate candidate control)
  else
    order=(candidate control control candidate)
  fi
  for position in 0 1 2 3; do
    run_one "$sequence" "$position" "${order[$position]}"
  done
done

expected="$(awk 'NR == 2 {print $5}' "$output/timings.tsv")"
if awk -v expected="$expected" 'NR > 1 && $5 != expected {exit 1}' "$output/timings.tsv"; then
  :
else
  echo "control/candidate output mismatch" >&2
  exit 1
fi

"$control" score "$fixture" 2 >"$output/control-workers2.json"
"$candidate" score "$fixture" 2 >"$output/candidate-workers2.json"
cmp "$output/control-workers2.json" "$output/candidate-workers2.json"
if [[ "$(sha256sum "$output/control-workers2.json" | awk '{print $1}')" != "$expected" ]]; then
  echo "one-worker and two-worker output mismatch" >&2
  exit 1
fi

python3 - "$output/timings.tsv" "$output/summary.json" <<'PY'
import csv
import json
import statistics
import sys

rows = list(csv.DictReader(open(sys.argv[1], newline=""), delimiter="\t"))
groups = {
    name: [int(row["wall_ns"]) for row in rows if row["implementation"] == name]
    for name in ("control", "candidate")
}
summary = {
    "schema": "org.leo.location-score-interpolation-stencil-abba/v1",
    "runs_per_implementation": len(groups["control"]),
    "output_sha256": rows[0]["output_sha256"],
    "control_median_wall_ms": statistics.median(groups["control"]) / 1e6,
    "candidate_median_wall_ms": statistics.median(groups["candidate"]) / 1e6,
}
summary["median_speedup"] = (
    summary["control_median_wall_ms"] / summary["candidate_median_wall_ms"]
)
with open(sys.argv[2], "w") as stream:
    json.dump(summary, stream, indent=2)
    stream.write("\n")
print(json.dumps(summary, sort_keys=True))
PY

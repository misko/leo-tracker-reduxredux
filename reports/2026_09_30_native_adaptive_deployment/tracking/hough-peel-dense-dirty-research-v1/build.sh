#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
report="$root/reports/2026_09_30_native_adaptive_deployment/tracking/hough-peel-dense-dirty-research-v1"
source_dir="$report/source"
output="${2:-/var/tmp/leo-hough-peel-dense-dirty-$mode}"
mkdir -p "$output"

case "$mode" in
  host)
    cxx="${CXX:-g++}"
    ar="${AR:-ar}"
    flags=(-std=c++17 -O3 -fno-fast-math -ffp-contract=off -fPIC)
    link_flags=()
    ;;
  sanitize)
    cxx="${CXX:-g++}"
    ar="${AR:-ar}"
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math
      -ffp-contract=off -fPIC -fsanitize=address,undefined)
    link_flags=()
    ;;
  *)
    echo "usage: $0 [host|sanitize] [output-directory]" >&2
    exit 2
    ;;
esac

common=(-I "$source_dir" -Wall -Wextra -Wpedantic -Werror)

"$cxx" "${flags[@]}" "${common[@]}" -c "$source_dir/tracking.cpp" \
  -o "$output/candidate.o"
"$ar" rcs "$output/libcandidate.a" "$output/candidate.o"
"$cxx" "${flags[@]}" "${common[@]}" -DLEO_TRACKING_DIRTY_DIAGNOSTIC \
  -c "$source_dir/tracking.cpp" -o "$output/candidate-diagnostic.o"
"$ar" rcs "$output/libcandidate-diagnostic.a" \
  "$output/candidate-diagnostic.o"
"$cxx" "${flags[@]}" "${common[@]}" -c "$source_dir/control.cpp" \
  -o "$output/control.o"
"$ar" rcs "$output/libcontrol.a" "$output/control.o"

"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/test_tracking.cpp" \
  "$output/libcandidate-diagnostic.a" "${link_flags[@]}" \
  -o "$output/test-tracking"
"$cxx" "${flags[@]}" "${common[@]}" -DLEO_TRACKING_DIRTY_DIAGNOSTIC \
  -Wno-subobject-linkage "$source_dir/test_exact_dirty_histogram.cpp" \
  "${link_flags[@]}" \
  -o "$output/test-exact-dirty-histogram"

for variant in candidate control; do
  "$cxx" "${flags[@]}" "${common[@]}" \
    "$source_dir/tracking_prefix_benchmark.cpp" "$output/lib$variant.a" \
    "${link_flags[@]}" -o "$output/prefix-$variant"
  "$cxx" "${flags[@]}" "${common[@]}" -pthread \
    -I "$root/native/adaptive/tracking" \
    -DLEO_TRACKING_EXECUTION_CLI "$source_dir/tracking_cli.cpp" \
    "$root/native/adaptive/runtime/runtime.cpp" "$output/lib$variant.a" \
    "${link_flags[@]}" -o "$output/tracking-$variant"
done

"$cxx" "${flags[@]}" "${common[@]}" \
  "$source_dir/tracking_prefix_benchmark.cpp" \
  "$output/libcandidate-diagnostic.a" "${link_flags[@]}" \
  -o "$output/prefix-candidate-allocation"

"$output/test-exact-dirty-histogram"
"$output/test-tracking"
printf '%s\n' "$output"

#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../.." && pwd)"
source_dir="$root/native/adaptive/tracking"
test_dir="$root/tests/native_adaptive/tracking"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"

case "$mode" in
  host)
    cxx="${CXX:-g++}"
    ar="${AR:-ar}"
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC)
    link_flags=()
    ;;
  sanitize)
    cxx="${CXX:-g++}"
    ar="${AR:-ar}"
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math -fPIC
      -fsanitize=address,undefined)
    link_flags=()
    ;;
  thread)
    cxx="${CXX:-g++}"
    ar="${AR:-ar}"
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math -fPIC
      -fsanitize=thread)
    link_flags=()
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cxx="${CXX:-$toolchain-g++}"
    ar="${AR:-$toolchain-ar}"
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link_flags=(-static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|thread|arm] [output-directory]" >&2
    exit 2
    ;;
esac

common=(-I "$source_dir" -Wall -Wextra -Wpedantic)
"$cxx" "${flags[@]}" "${common[@]}" -c "$source_dir/tracking.cpp" -o "$output/tracking.o"
"$ar" rcs "$output/libleotracking.a" "$output/tracking.o"
"$cxx" -shared "${flags[@]}" "$output/tracking.o" "${link_flags[@]}" \
  -o "$output/libleotracking.so"
"$cxx" "${flags[@]}" "${common[@]}" -pthread -DLEO_TRACKING_EXECUTION_CLI \
  "$source_dir/tracking_cli.cpp" "$root/native/adaptive/runtime/runtime.cpp" \
  "$output/libleotracking.a" "${link_flags[@]}" -o "$output/leo-tracking"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/tracking_prefix_benchmark.cpp" \
  "$output/libleotracking.a" "${link_flags[@]}" -o "$output/leo-tracking-prefix-benchmark"
"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_tracking.cpp" \
  "$output/libleotracking.a" "${link_flags[@]}" -o "$output/test_tracking"
"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_chosen_point.cpp" \
  "$output/libleotracking.a" "${link_flags[@]}" -o "$output/test_chosen_point"
"$cxx" "${flags[@]}" "${common[@]}" -pthread "$test_dir/test_lane_execution.cpp" \
  "$output/libleotracking.a" "${link_flags[@]}" -o "$output/test_lane_execution"
"$cxx" "${flags[@]}" -frounding-math "${common[@]}" "$test_dir/test_hough_bin.cpp" \
  "${link_flags[@]}" -o "$output/test_hough_bin"
"$cxx" "${flags[@]}" "${common[@]}" \
  "$test_dir/test_exact_fit_cache_internal.cpp" "${link_flags[@]}" \
  -o "$output/test_exact_fit_cache_internal"
"$cxx" "${flags[@]}" "${common[@]}" \
  "$test_dir/test_residual_predicate_internal.cpp" "${link_flags[@]}" \
  -o "$output/test_residual_predicate_internal"

if [[ "$mode" != arm ]]; then
  "$output/test_tracking"
  "$output/test_chosen_point"
  "$output/test_lane_execution"
  "$output/test_hough_bin"
  "$output/test_exact_fit_cache_internal"
  "$output/test_residual_predicate_internal"
fi

echo "$output"

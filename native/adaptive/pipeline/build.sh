#!/usr/bin/env bash
set -euo pipefail
mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../.." && pwd)"
source_dir="$root/native/adaptive/pipeline"
tracking_dir="$root/native/adaptive/tracking"
location_dir="$root/native/adaptive/location"
runtime_dir="$root/native/adaptive/runtime"
test_dir="$root/tests/native_adaptive/tracking"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"
case "$mode" in
 host) cxx="${CXX:-g++}";ar="${AR:-ar}";flags=(-std=c++17 -O3 -fno-fast-math -fPIC);link=();;
 sanitize) cxx="${CXX:-g++}";ar="${AR:-ar}";flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math -fPIC -fsanitize=address,undefined);link=();;
 arm) toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}";cxx="${CXX:-$toolchain-g++}";ar="${AR:-$toolchain-ar}";flags=(-std=c++17 -O3 -fno-fast-math -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard);link=(-static-libstdc++ -static-libgcc);;
 *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2;exit 2;;
esac
include=(-I "$source_dir" -I "$tracking_dir" -I "$location_dir" -I "$runtime_dir" -Wall -Wextra -Wpedantic)
"$cxx" "${flags[@]}" "${include[@]}" -c "$tracking_dir/tracking.cpp" -o "$output/tracking.o"
"$cxx" "${flags[@]}" "${include[@]}" -c "$source_dir/pipeline.cpp" -o "$output/pipeline.o"
"$cxx" "${flags[@]}" "${include[@]}" -c "$source_dir/track_input.cpp" -o "$output/track_input.o"
"$cxx" "${flags[@]}" "${include[@]}" -c "$source_dir/selection.cpp" -o "$output/selection.o"
"$ar" rcs "$output/libleopipeline.a" "$output/tracking.o" "$output/pipeline.o" "$output/track_input.o" "$output/selection.o"
"$cxx" "${flags[@]}" "${include[@]}" "$source_dir/pipeline_cli.cpp" "$output/libleopipeline.a" "${link[@]}" -o "$output/leo-adaptive-pipeline"
"$cxx" "${flags[@]}" "${include[@]}" "$test_dir/test_pipeline.cpp" "$output/libleopipeline.a" "${link[@]}" -o "$output/test_pipeline"
if [[ "$mode" != arm ]]; then "$output/test_pipeline";fi
if [[ -n "${3:-}" ]]; then
  "$cxx" "${flags[@]}" "${include[@]}" "$source_dir/in_memory_cli.cpp" \
    "$output/libleopipeline.a" "$3/libleolocation.a" "${link[@]}" -pthread -lm -o "$output/leo-memory-position"
  if [[ "$mode" != arm ]]; then python3 "$test_dir/check_memory_cli.py" "$output/leo-memory-position";fi
fi
echo "$output"

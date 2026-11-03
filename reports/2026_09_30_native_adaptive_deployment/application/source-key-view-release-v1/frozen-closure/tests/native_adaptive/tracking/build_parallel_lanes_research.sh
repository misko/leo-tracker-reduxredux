#!/usr/bin/env bash
set -euo pipefail
mode=${1:-host}
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
out=${2:-/tmp/leo-tracking-parallel-research-$mode}
source_dir=$root/native/adaptive/tracking
research=$root/reports/2026_09_30_native_adaptive_deployment/tracking/research/tracking_parallel_lanes.cpp
mkdir -p "$out"
flags=(-std=c++17 -O3 -fno-fast-math -fPIC -pthread -Wall -Wextra -Wpedantic)
link=()
case "$mode" in
  host) cxx=${CXX:-g++} ;;
  sanitize) cxx=${CXX:-g++}; flags+=(-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer) ;;
  thread) cxx=${CXX:-g++}; flags+=(-O1 -g -fsanitize=thread -fno-omit-frame-pointer) ;;
  arm) cxx=${CXX:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-g++}
       flags+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
       link+=(-static-libstdc++ -static-libgcc) ;;
  *) exit 2 ;;
esac
"$cxx" "${flags[@]}" -I"$source_dir" -c "$research" -o "$out/tracking.o"
"$cxx" "${flags[@]}" -I"$source_dir" "$source_dir/tracking_cli.cpp" "$out/tracking.o" "${link[@]}" -o "$out/leo-tracking"
for test in test_tracking test_chosen_point peak_threshold_fixture; do
  "$cxx" "${flags[@]}" -I"$source_dir" "$root/tests/native_adaptive/tracking/$test.cpp" "$out/tracking.o" "${link[@]}" -o "$out/$test"
  if [[ $mode != arm ]]; then "$out/$test" > "$out/$test.log"; fi
done

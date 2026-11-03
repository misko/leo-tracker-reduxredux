#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/tmp/leo-one-per-source-rank-$mode}
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
source_dir="$root/native/adaptive/tracking"
candidate="$root/reports/2026_09_30_native_adaptive_deployment/tracking/research/tracking_one_per_source_rank.cpp"
mkdir -p "$out"
flags=(-std=c++17 -fno-fast-math -fPIC -Wall -Wextra -Wpedantic)
link=()
case "$mode" in
  host) cxx=${CXX:-g++}; flags+=(-O3) ;;
  sanitize)
    cxx=${CXX:-g++}
    flags+=(-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer)
    link+=(-fsanitize=address,undefined)
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}
    flags+=(-O3 -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link+=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2; exit 2 ;;
esac

"$cxx" "${flags[@]}" -I"$source_dir" -c "$source_dir/tracking.cpp" \
  -o "$out/control.o"
"$cxx" "${flags[@]}" -I"$source_dir" -c "$candidate" -o "$out/candidate.o"
"$cxx" "${flags[@]}" -I"$source_dir" "$source_dir/tracking_cli.cpp" \
  "$out/control.o" "${link[@]}" -o "$out/control"
"$cxx" "${flags[@]}" -I"$source_dir" "$source_dir/tracking_cli.cpp" \
  "$out/candidate.o" "${link[@]}" -o "$out/candidate"
"$cxx" "${flags[@]}" -I"$source_dir" \
  "$root/tests/native_adaptive/tracking/test_one_per_source_rank_research.cpp" \
  "${link[@]}" -o "$out/test-one-per-source-rank"
"$cxx" "${flags[@]}" -I"$source_dir" \
  "$root/tests/native_adaptive/tracking/test_tracking.cpp" "$out/candidate.o" \
  "${link[@]}" -o "$out/test-tracking-candidate"

if [[ $mode != arm ]]; then
  "$out/test-one-per-source-rank" | tee "$out/rank-test.log"
  "$out/test-tracking-candidate" | tee "$out/tracking-test.log"
fi
printf '%s\n' "$out"

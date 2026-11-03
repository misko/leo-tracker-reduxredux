#!/usr/bin/env bash
set -euo pipefail

variant=${1:?usage: build.sh control|candidate host|sanitize OUTPUT}
mode=${2:?usage: build.sh control|candidate host|sanitize OUTPUT}
output=${3:?usage: build.sh control|candidate host|sanitize OUTPUT}
root=$(cd -- "$(dirname -- "$0")/../../../.." && pwd)
research=$root/reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research
source_file=$research/source-$variant/tracking.cpp
source_dir=$root/native/adaptive/tracking
tests=$root/tests/native_adaptive/tracking
mkdir -p "$output"
flags=(-std=c++17 -fno-fast-math -fPIC -Wall -Wextra -Wpedantic -I"$source_dir")
link=()
cxx=g++
archiver=ar
case $mode in
  host) flags+=(-O3) ;;
  sanitize) flags+=(-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined) ;;
  arm)
    toolchain=/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf
    cxx=$toolchain-g++
    archiver=$toolchain-ar
    flags+=(-O3 -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link+=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "mode must be host, sanitize or arm" >&2; exit 2 ;;
esac
export TMPDIR=$output
"$cxx" "${flags[@]}" -c "$source_file" -o "$output/tracking.o"
"$archiver" rcs "$output/libleotracking.a" "$output/tracking.o"
"$cxx" "${flags[@]}" "$source_dir/tracking_cli.cpp" \
  "$output/libleotracking.a" "${link[@]}" -o "$output/leo-tracking"
"$cxx" "${flags[@]}" "$source_dir/tracking_prefix_benchmark.cpp" \
  "$output/libleotracking.a" "${link[@]}" -o "$output/tracking-prefix-benchmark"
for test in test_tracking test_chosen_point; do
  "$cxx" "${flags[@]}" "$tests/$test.cpp" "$output/libleotracking.a" \
    "${link[@]}" -o "$output/$test"
done
if [[ $mode == host ]]; then
  "$cxx" "${flags[@]}" -DLEO_TRACKING_RESIDUAL_COUNT -c "$source_file" \
    -o "$output/tracking-count.o"
  "$cxx" "${flags[@]}" "$source_dir/tracking_cli.cpp" "$output/tracking-count.o" \
    -o "$output/leo-tracking-count"
fi

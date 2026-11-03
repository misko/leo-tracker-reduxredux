#!/usr/bin/env bash
set -euo pipefail

variant=${1:?usage: build.sh control|optimized host|arm OUTPUT}
mode=${2:?usage: build.sh control|optimized host|arm OUTPUT}
output=${3:?usage: build.sh control|optimized host|arm OUTPUT}
root=$(cd -- "$(dirname -- "$0")/../../../.." && pwd)
report=$root/reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-two-worker-v1
tracking=$root/native/adaptive/tracking
runtime=$root/native/adaptive/runtime
source_file=$report/source-$variant/tracking.cpp
mkdir -p "$output"
flags=(-std=c++17 -O3 -fno-fast-math -fPIC -Wall -Wextra -Wpedantic
  -I"$tracking" -I"$runtime")
link=(-pthread)
cxx=g++
archiver=ar
case $mode in
  host) ;;
  arm)
    toolchain=/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf
    cxx=$toolchain-g++
    archiver=$toolchain-ar
    flags+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link+=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "mode must be host or arm" >&2; exit 2 ;;
esac
export TMPDIR=$output
"$cxx" "${flags[@]}" -c "$source_file" -o "$output/tracking.o"
"$archiver" rcs "$output/libleotracking.a" "$output/tracking.o"
"$cxx" "${flags[@]}" -DLEO_TRACKING_EXECUTION_CLI \
  "$tracking/tracking_cli.cpp" "$runtime/runtime.cpp" \
  "$output/libleotracking.a" "${link[@]}" -o "$output/leo-tracking-execution"

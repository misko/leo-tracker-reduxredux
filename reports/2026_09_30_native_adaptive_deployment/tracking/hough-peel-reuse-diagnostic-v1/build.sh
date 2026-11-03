#!/usr/bin/env bash
set -euo pipefail

mode=${1:?host or arm}
output=${2:?output directory}
base=$(cd -- "$(dirname -- "$0")" && pwd)
source_dir="$base/source"
mkdir -p "$output/tmp"
export TMPDIR="$output/tmp"

case "$mode" in
  host)
    cxx=${CXX:-g++}
    ar=${AR:-ar}
    flags=(-std=c++17 -O3 -fno-fast-math -ffp-contract=off -fPIC)
    link=()
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}
    ar=${AR:-$toolchain-ar}
    flags=(-std=c++17 -O3 -fno-fast-math -ffp-contract=off -fPIC -mcpu=cortex-a9
      -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *) exit 2 ;;
esac

common=(-I "$source_dir" -Wall -Wextra -Wpedantic -Werror)
"$cxx" "${flags[@]}" "${common[@]}" -c \
  "$source_dir/tracking_stage_profile.cpp" -o "$output/tracking_stage_profile.o"
"$ar" rcs "$output/libleotracking-stage-profile.a" \
  "$output/tracking_stage_profile.o"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/tracking_cli.cpp" \
  "$output/libleotracking-stage-profile.a" "${link[@]}" \
  -o "$output/leo-tracking-stage-profile"
"$cxx" "${flags[@]}" "${common[@]}" \
  "$source_dir/tracking_prefix_benchmark.cpp" \
  "$output/libleotracking-stage-profile.a" "${link[@]}" \
  -o "$output/leo-tracking-prefix-stage-profile"

"$cxx" "${flags[@]}" "${common[@]}" -DLEO_TRACKING_PEEL_COUNTERS -c \
  "$source_dir/tracking_stage_profile.cpp" -o "$output/tracking_peel_counters.o"
"$ar" rcs "$output/libleotracking-peel-counters.a" \
  "$output/tracking_peel_counters.o"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/tracking_cli.cpp" \
  "$output/libleotracking-peel-counters.a" "${link[@]}" \
  -o "$output/leo-tracking-peel-counters"
"$cxx" "${flags[@]}" "${common[@]}" \
  "$source_dir/tracking_prefix_benchmark.cpp" \
  "$output/libleotracking-peel-counters.a" "${link[@]}" \
  -o "$output/leo-tracking-prefix-peel-counters"

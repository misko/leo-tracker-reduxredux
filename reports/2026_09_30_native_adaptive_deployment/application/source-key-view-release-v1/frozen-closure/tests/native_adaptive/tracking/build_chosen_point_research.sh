#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../.." && pwd)"
source_dir="$root/native/adaptive/tracking"
research_source="$root/reports/2026_09_30_native_adaptive_deployment/tracking/research/tracking_chosen_point.cpp"
test_source="$root/tests/native_adaptive/tracking/test_chosen_point_research.cpp"
output="${2:-/tmp/leo-tracking-chosen-point-$mode}"
mkdir -p "$output"

case "$mode" in
  host)
    cxx="${CXX:-g++}"
    flags=(-std=c++17 -O3 -fno-fast-math)
    link_flags=()
    ;;
  sanitize)
    cxx="${CXX:-g++}"
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math
      -fsanitize=address,undefined)
    link_flags=()
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cxx="${CXX:-$toolchain-g++}"
    flags=(-std=c++17 -O3 -fno-fast-math -mcpu=cortex-a9 -mfpu=neon
      -mfloat-abi=hard)
    link_flags=(-static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2
    exit 2
    ;;
esac

common=(-I "$source_dir" -Wall -Wextra -Wpedantic)
"$cxx" "${flags[@]}" "${common[@]}" -c "$research_source" \
  -o "$output/tracking-chosen-point.o"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/tracking_cli.cpp" \
  "$output/tracking-chosen-point.o" "${link_flags[@]}" \
  -o "$output/leo-tracking-chosen-point"
"$cxx" "${flags[@]}" "${common[@]}" "$test_source" \
  "${link_flags[@]}" -o "$output/test-chosen-point"

if [[ "$mode" != arm ]]; then
  "$output/test-chosen-point"
fi

echo "$output"

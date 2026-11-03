#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/device/recorded"
common_dir="$root/native/adaptive/device/source"
test_dir="$root/tests/native_adaptive/device/recorded"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"
link_flags=()

case "$mode" in
  host)
    cxx="${CXX:-g++}"; cc="${CC:-gcc}"
    flags=(-O2 -fPIC)
    ;;
  sanitize)
    cxx="${CXX:-g++}"; cc="${CC:-gcc}"
    flags=(-O1 -g -fno-omit-frame-pointer -fPIC -fsanitize=address,undefined)
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cxx="${CXX:-$toolchain-g++}"; cc="${CC:-$toolchain-gcc}"
    flags=(-O2 -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link_flags=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2; exit 2 ;;
esac

warnings=(-Wall -Wextra -Werror -Wpedantic)
"$cc" -std=c11 "${flags[@]}" "${warnings[@]}" -I "$common_dir" \
  -c "$common_dir/source_port.c" -o "$output/source_port.o"
"$cxx" -std=c++17 "${flags[@]}" "${warnings[@]}" -pthread -I "$root/native/adaptive" \
  -c "$source_dir/recorded_source.cpp" -o "$output/recorded_source.o"
"$cxx" -std=c++17 "${flags[@]}" "${warnings[@]}" -pthread -I "$root/native/adaptive" \
  "$test_dir/test_recorded_source.cpp" "$output/recorded_source.o" \
  "$output/source_port.o" "${link_flags[@]}" -o "$output/test-recorded-source"
"$cxx" -std=c++17 "${flags[@]}" "${warnings[@]}" -pthread -I "$root/native/adaptive" \
  "$test_dir/test_recorded_source_ds9.cpp" "$output/recorded_source.o" \
  "$output/source_port.o" "${link_flags[@]}" -o "$output/test-recorded-source-ds9"
if [[ "$mode" != arm ]]; then "$output/test-recorded-source"; fi
printf '%s\n' "$output"

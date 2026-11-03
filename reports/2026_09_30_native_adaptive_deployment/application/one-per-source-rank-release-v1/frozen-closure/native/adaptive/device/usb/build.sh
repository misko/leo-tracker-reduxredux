#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/device/usb"
test_dir="$root/tests/native_adaptive/device/usb"
output="${2:-$source_dir/build/$mode}"
fixture="$root/reports/2026_09_30_native_adaptive_deployment/ds9/location-selection/raw/scan-fw-3cfdaa6d75762cad-276.ci16"
fixture_sha256="36a9d2aacabe1a456083ee353d90fa980744645d4ca2ee31aee12bdf7dec9d0d"
mkdir -p "$output"
link_flags=()

case "$mode" in
  host)
    cc="${CC:-gcc}"; cxx="${CXX:-g++}"; ar="${AR:-ar}"
    flags=(-O2 -fPIC)
    ;;
  sanitize)
    cc="${CC:-gcc}"; cxx="${CXX:-g++}"; ar="${AR:-ar}"
    flags=(-O1 -g -fno-omit-frame-pointer -fPIC -fsanitize=address,undefined)
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cc="${CC:-$toolchain-gcc}"; cxx="${CXX:-$toolchain-g++}"; ar="${AR:-$toolchain-ar}"
    flags=(-O2 -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link_flags=(-static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2
    exit 2
    ;;
esac

warnings=(-Wall -Wextra -Werror -Wpedantic)
"$cc" -std=c11 "${flags[@]}" "${warnings[@]}" -I "$source_dir" \
  -c "$source_dir/usb_source.c" -o "$output/usb_source.o"
"$ar" rcs "$output/libleousbsource.a" "$output/usb_source.o"
"$cxx" -std=c++17 "${flags[@]}" "${warnings[@]}" -pthread \
  -I "$source_dir" -I "$root/native/adaptive/runtime" \
  "$test_dir/test_usb_source.cpp" "$root/native/adaptive/runtime/runtime.cpp" \
  "$output/libleousbsource.a" "${link_flags[@]}" -o "$output/test-usb-source"

if [[ "$mode" != arm ]]; then
  if [[ ! -r "$fixture" ]]; then
    echo "required DS9 replay fixture missing: $fixture" >&2
    exit 1
  fi
  actual_fixture_sha256="$(sha256sum "$fixture" | cut -d' ' -f1)"
  if [[ "$actual_fixture_sha256" != "$fixture_sha256" ]]; then
    echo "DS9 replay fixture hash mismatch: $actual_fixture_sha256" >&2
    exit 1
  fi
  "$output/test-usb-source" "$fixture"
fi
echo "$output"

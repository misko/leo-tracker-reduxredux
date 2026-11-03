#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/device/usb"
test_dir="$root/tests/native_adaptive/device/usb"
output="${1:-$source_dir/build/soapy}"
mkdir -p "$output"

if ! pkg-config --exists SoapySDR; then
  echo "SoapySDR development package is required for the optional backend" >&2
  exit 2
fi
cflags=($(pkg-config --cflags SoapySDR))
libs=($(pkg-config --libs SoapySDR))
warnings=(-Wall -Wextra -Werror -Wpedantic)
gcc -std=c11 -O2 -fPIC "${warnings[@]}" -I "$source_dir" \
  -c "$source_dir/usb_source.c" -o "$output/usb_source.o"
g++ -std=c++17 -O2 -fPIC "${warnings[@]}" -I "$source_dir" "${cflags[@]}" \
  -c "$source_dir/usb_soapy_provider.cpp" -o "$output/usb_soapy_provider.o"
ar rcs "$output/libleousbsoapy.a" "$output/usb_source.o" \
  "$output/usb_soapy_provider.o"
g++ -std=c++17 -O2 "${warnings[@]}" -I "$source_dir" "${cflags[@]}" \
  "$test_dir/test_soapy_hardware.cpp" "$output/libleousbsoapy.a" \
  "${libs[@]}" -pthread -o "$output/test-soapy-hardware"
echo "$output"

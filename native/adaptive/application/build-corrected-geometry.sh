#!/usr/bin/env bash
set -euo pipefail
mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../.." && pwd)"
output="${2:?usage: build-corrected-geometry.sh host|sanitize|arm OUTPUT}"
mkdir -p "$output"
flags=(-std=c++17 -Wall -Wextra -Werror -pedantic -fno-fast-math)
case "$mode" in
  host) compiler="${CXX:-g++}"; flags+=(-O2) ;;
  sanitize) compiler="${CXX:-g++}"; flags+=(-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer) ;;
  arm)
    compiler="${CXX:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-g++}"
    flags+=(-O2 -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard -static-libstdc++ -static-libgcc) ;;
  *) exit 2 ;;
esac
"$compiler" "${flags[@]}" \
  "$root/native/adaptive/application/corrected_geometry.cpp" \
  "$root/tests/native_adaptive/application/test_corrected_geometry.cpp" \
  -o "$output/test-corrected-geometry"
if [[ "$mode" != arm ]]; then "$output/test-corrected-geometry"; fi

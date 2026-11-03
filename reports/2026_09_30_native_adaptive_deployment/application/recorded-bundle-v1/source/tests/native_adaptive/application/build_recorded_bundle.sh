#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
output=${2:-"/var/tmp/leo-recorded-bundle-$mode"}
mkdir -p "$output"

case "$mode" in
  host)
    cxx=${CXX:-g++}
    flags=(-O2 -g)
    link=()
    ;;
  sanitize)
    cxx=${CXX:-g++}
    flags=(-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined)
    link=(-fsanitize=address,undefined)
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-"$toolchain-g++"}
    flags=(-O2 -g -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [output]" >&2; exit 2 ;;
esac

common=(-std=c++17 -Wall -Wextra -Werror -Wpedantic -fno-fast-math -ffp-contract=off)
"$cxx" "${common[@]}" "${flags[@]}" -I"$root/native/adaptive" \
  "$root/native/adaptive/application/recorded_bundle.cpp" \
  "$root/native/adaptive/application/corrected_geometry.cpp" \
  "$root/tests/native_adaptive/application/test_recorded_bundle.cpp" \
  "${link[@]}" -o "$output/test-recorded-bundle"

if [[ $mode != arm ]]; then
  TMPDIR=${TMPDIR:-/var/tmp} "$output/test-recorded-bundle"
fi
sha256sum "$output/test-recorded-bundle"
printf '%s\n' "$output"

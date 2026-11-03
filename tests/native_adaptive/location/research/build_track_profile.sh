#!/usr/bin/env bash
set -euo pipefail
mode="${1:?host or arm}"
library="${2:?qualified location build directory}"
output="${3:?output executable}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
case "$mode" in
  host) compiler="${CXX:-g++}"; target=(); link=(-pthread);;
  arm)
    compiler="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}-g++"
    target=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-pthread -static-libstdc++ -static-libgcc);;
  *) exit 2;;
esac
"$compiler" -std=c++17 -O3 -fno-fast-math "${target[@]}" \
  -I "$root/native/adaptive/location" \
  "$root/tests/native_adaptive/location/research/profile_track_scoring.cpp" \
  "$library/libleolocation.a" "${link[@]}" -lm -o "$output"

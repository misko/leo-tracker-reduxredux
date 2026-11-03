#!/usr/bin/env bash
set -euo pipefail
mode="${1:?host or arm}"
output="${2:?absolute output directory}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
[[ "$output" = /* ]] || { echo 'output must be absolute' >&2; exit 1; }
mkdir -p "$output"
case "$mode" in
  host) cxx="${CXX:-g++}"; arch=(); link=() ;;
  sanitize) cxx="${CXX:-g++}"; arch=(-fsanitize=address,undefined -fno-omit-frame-pointer); link=() ;;
  arm) cxx="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}-g++"
       arch=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard); link=(-static-libstdc++ -static-libgcc) ;;
  *) exit 1 ;;
esac
src="$root/native/adaptive/location"
flags=(-std=c++17 -O3 -fno-fast-math -ffp-contract=off "${arch[@]}" -I "$src" -I "$src/research")
"$cxx" "${flags[@]}" -w -c "$src/vendor/sgp4/SGP4.cpp" -o "$output/sgp4.o"
"$cxx" "${flags[@]}" -c "$src/orbit.cpp" -o "$output/orbit.o"
"$cxx" "${flags[@]}" "$src/research/streaming_match_cli.cpp" "$output/orbit.o" "$output/sgp4.o" "${link[@]}" -o "$output/streaming-match"
"$cxx" "${flags[@]}" "$root/tests/native_adaptive/location/research/test_streaming_match.cpp" "$output/orbit.o" "$output/sgp4.o" "${link[@]}" -o "$output/test-streaming-match"
if [[ "$mode" != arm ]]; then "$output/test-streaming-match"; fi

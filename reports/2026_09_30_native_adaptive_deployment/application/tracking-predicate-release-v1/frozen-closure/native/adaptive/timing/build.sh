#!/usr/bin/env bash
set -euo pipefail
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
out=${1:?usage: build.sh OUTPUT_DIRECTORY}
mkdir -p "$out"
flags=(-std=c++17 -O2 -g -Wall -Wextra -Werror -Wpedantic -fno-fast-math)
if [[ ${SANITIZE:-0} == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
if [[ ${ARM:-0} == 1 ]]; then flags+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard -static-libstdc++ -static-libgcc); fi
"${CXX:-g++}" "${flags[@]}" -I"$dir" "$dir/timebase.cpp" "$dir/posix_clock.cpp" "$repo/tests/native_adaptive/timing/test_timebase.cpp" -o "$out/test-timebase"

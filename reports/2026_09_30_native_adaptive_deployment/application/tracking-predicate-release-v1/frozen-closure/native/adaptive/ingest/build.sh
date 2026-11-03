#!/usr/bin/env bash
set -euo pipefail
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
out=${1:?usage: build.sh OUTPUT_DIRECTORY}
mkdir -p "$out"
flags=(-std=c++17 -O2 -g -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off -pthread)
if [[ ${SANITIZE:-0} == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
if [[ ${ARM:-0} == 1 ]]; then flags+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard -static-libstdc++ -static-libgcc); fi
"${CXX:-g++}" "${flags[@]}" "$dir/ingest.cpp" "$dir/../timing/timebase.cpp" \
    "$dir/../runtime/runtime.cpp" "$dir/../runtime/projection.cpp" \
    -I"$dir" "$repo/tests/native_adaptive/ingest/test_ingest.cpp" -o "$out/test-ingest"
"${CXX:-g++}" "${flags[@]}" "$dir/ingest.cpp" "$dir/../timing/timebase.cpp" \
    "$dir/../runtime/runtime.cpp" "$dir/../runtime/projection.cpp" \
    -I"$dir" "$repo/tests/native_adaptive/ingest/test_ds9_ingest.cpp" -o "$out/test-ds9-ingest"

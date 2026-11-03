#!/usr/bin/env bash
set -euo pipefail
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
out=${1:?usage: build.sh OUTPUT_DIRECTORY ONLINE_LIBRARY_DIRECTORY}
online=${2:?prebuilt online library directory required}
mkdir -p "$out"
flags=(-std=c++17 -O2 -g -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off -pthread)
if [[ ${SANITIZE:-0} == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
if [[ ${ARM:-0} == 1 ]]; then flags+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard -static-libstdc++ -static-libgcc); fi
"${CXX:-g++}" "${flags[@]}" -I"$dir" -I"$dir/../runtime" -I"$dir/../tracking" \
    -I"$dir/../pipeline" -I"$dir/../location" "$dir/session.cpp" \
    "$dir/../ingest/ingest.cpp" "$dir/../timing/timebase.cpp" \
    "$dir/../runtime/runtime.cpp" "$dir/../runtime/projection.cpp" \
    "$repo/tests/native_adaptive/application/test_session.cpp" "$online/libleoonline.a" \
    -lm -o "$out/test-session"

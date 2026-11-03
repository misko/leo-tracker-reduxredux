#!/usr/bin/env bash
set -euo pipefail
bench_dir=$(cd -- "$(dirname -- "$0")" && pwd)
output=${1:?output directory}
detector=${2:?detector library directory}
mkdir -p "$output"
options=(-std=c++17 -O2 -Wall -Wextra -Werror -fno-fast-math -pthread)
if [[ ${ARM:-0} == 1 ]]; then options+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard -static-libstdc++ -static-libgcc); fi
"${CXX:-g++}" "${options[@]}" "$bench_dir/paced.cpp" "$bench_dir/../runtime/runtime.cpp" \
    -L"$detector" -Wl,-rpath,'$ORIGIN' -lleo-adaptive-detector -o "$output/leo-paced"

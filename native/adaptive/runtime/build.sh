#!/usr/bin/env bash
set -euo pipefail
runtime_dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(cd -- "$runtime_dir/../../.." && pwd)
build_dir=${1:?usage: build.sh OUTPUT_DIRECTORY}
mkdir -p "$build_dir"
compiler=${CXX:-g++}
options=(-std=c++17 -O2 -g -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off -pthread)
if [[ ${SANITIZE:-0} == 1 ]]; then
    options+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
if [[ ${ARM:-0} == 1 ]]; then
    options+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard -static-libstdc++ -static-libgcc)
fi
"$compiler" "${options[@]}" -I"$runtime_dir" "$runtime_dir/runtime.cpp" "$runtime_dir/projection.cpp" \
    "$repo_dir/tests/native_adaptive/runtime/test_runtime.cpp" -o "$build_dir/test-runtime"
"$compiler" "${options[@]}" -I"$runtime_dir" "$runtime_dir/runtime.cpp" \
    "$runtime_dir/projection_cli.cpp" -o "$build_dir/project-support"
"$compiler" "${options[@]}" -I"$runtime_dir" "$runtime_dir/runtime.cpp" \
    "$runtime_dir/integer_support_cli.cpp" -o "$build_dir/project-integer-support"
"$compiler" "${options[@]}" -I"$runtime_dir" "$runtime_dir/runtime.cpp" "$runtime_dir/projection.cpp" \
    "$runtime_dir/observations_cli.cpp" -o "$build_dir/leo-project"
"$compiler" "${options[@]}" -I"$runtime_dir" "$runtime_dir/runtime.cpp" \
    "$runtime_dir/windows_cli.cpp" -o "$build_dir/leo-windows"
"$compiler" "${options[@]}" -I"$runtime_dir" -I"$runtime_dir/../detector" \
    "$runtime_dir/runtime.cpp" "$runtime_dir/projection.cpp" \
    "$repo_dir/tests/native_adaptive/runtime/test_detector_projection.cpp" \
    -o "$build_dir/test-detector-projection"
if [[ ${ARM:-0} != 1 ]]; then "$build_dir/test-detector-projection"; fi

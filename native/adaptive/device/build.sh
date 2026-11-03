#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
build_dir=${1:?usage: build.sh OUTPUT_DIRECTORY}
mkdir -p "$build_dir"
options=(-std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror)
if [[ ${ARM:-0} == 1 ]]; then options+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard); fi
"${CC:-gcc}" "${options[@]}" "$source_dir/pluto_caps.c" -o "$build_dir/pluto-local-caps"
"${CC:-gcc}" "${options[@]}" "$source_dir/run_bounded.c" -o "$build_dir/run-bounded"
"${CC:-gcc}" "${options[@]}" "$source_dir/measure_run.c" -o "$build_dir/measure-run"
"${CC:-gcc}" "${options[@]}" -Dmain=pluto_caps_main -c "$source_dir/pluto_caps.c" -o "$build_dir/caps-test.o"
"${CC:-gcc}" "${options[@]}" -I"$source_dir" \
    "$source_dir/../../../tests/native_adaptive/device/test_caps.c" "$build_dir/caps-test.o" \
    -Wl,--wrap=open -Wl,--wrap=close -Wl,--wrap=ioctl -o "$build_dir/test-caps"

#!/usr/bin/env bash
set -euo pipefail
policy_dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(cd -- "$policy_dir/../../.." && pwd)
build_dir=${1:?usage: build.sh OUTPUT_DIRECTORY}
mkdir -p "$build_dir"
compiler=${CC:-gcc}
options=(-std=c11 -O2 -g -Wall -Wextra -Werror)
if [[ ${SANITIZE:-0} == 1 ]]; then options+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
if [[ ${ARM:-0} == 1 ]]; then options+=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard); fi
for test_name in original_policy continuous; do
    "$compiler" "${options[@]}" -I"$policy_dir" "$policy_dir/spf-scan-policy.c" \
        "$repo_dir/tests/native_adaptive/policy/test_$test_name.c" -o "$build_dir/test-$test_name"
done

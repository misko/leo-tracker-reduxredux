#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/tmp/leo-application-execution-$mode}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
mkdir -p "$out"

case "$mode" in
  host)
    cxx=${CXX:-g++}
    flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread)
    link=()
    ;;
  sanitize)
    cxx=${CXX:-g++}
    flags=(-std=c++17 -O1 -g -fno-fast-math -ffp-contract=off -pthread
      -fsanitize=address,undefined -fno-omit-frame-pointer)
    link=(-fsanitize=address,undefined)
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}
    flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread
      -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2
    exit 2
    ;;
esac

app="$repo/native/adaptive/application"
"$cxx" "${flags[@]}" -I"$app" -I"$repo/native/adaptive/runtime" \
  -I"$repo/native/adaptive/tracking" -Wall -Wextra -Werror -Wpedantic \
  "$dir/test_execution.cpp" "$repo/native/adaptive/runtime/runtime.cpp" \
  "${link[@]}" -o "$out/test-application-execution"

if [[ "$mode" != arm ]]; then
  "$out/test-application-execution"
fi
echo "$out"

#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/tmp/leo-application-tracking-tail-$mode}
tracking=${3:?usage: build_tracking_tail_benchmark.sh MODE OUTPUT TRACKING_BUILD [FIXTURE]}
fixture=${4:-}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
[[ -f "$tracking/libleotracking.a" ]] || {
  echo "tracking archive is absent" >&2
  exit 3
}
mkdir -p "$out"

case "$mode" in
  host)
    cxx=${CXX:-g++}
    flags=(-std=c++17 -O3 -g -fno-fast-math -ffp-contract=off -pthread)
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
    flags=(-std=c++17 -O3 -g -fno-fast-math -ffp-contract=off -pthread
      -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 host|sanitize|arm OUTPUT TRACKING_BUILD [FIXTURE]" >&2
    exit 2
    ;;
esac

"$cxx" "${flags[@]}" -I"$repo/native/adaptive/application" \
  -I"$repo/native/adaptive/runtime" -I"$repo/native/adaptive/tracking" \
  -Wall -Wextra -Werror -Wpedantic \
  "$repo/native/adaptive/application/tracking_tail_benchmark.cpp" \
  "$repo/native/adaptive/runtime/runtime.cpp" "$tracking/libleotracking.a" \
  "${link[@]}" -o "$out/leo-application-tracking-tail-benchmark"

if [[ "$mode" != arm && -n "$fixture" ]]; then
  "$out/leo-application-tracking-tail-benchmark" "$fixture" 1 >"$out/workers-1.json"
  "$out/leo-application-tracking-tail-benchmark" "$fixture" 2 >"$out/workers-2.json"
  python3 "$dir/test_tracking_tail_benchmark.py" \
    "$out/workers-1.json" "$out/workers-2.json"
fi

echo "$out"

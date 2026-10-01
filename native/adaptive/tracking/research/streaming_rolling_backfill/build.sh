#!/usr/bin/env bash
set -euo pipefail
mode=${1:-host}
root=$(cd -- "$(dirname -- "$0")/../../../../.." && pwd)
dir="$root/native/adaptive/tracking/research/streaming_rolling_backfill"
out=${2:-"$dir/build/$mode"}; mkdir -p "$out"
case "$mode" in
 host) cxx=${CXX:-g++}; flags=(-std=c++17 -O3 -g -Wall -Wextra -Wpedantic -Werror -fno-fast-math -ffp-contract=off); link=();;
 sanitize) cxx=${CXX:-g++}; flags=(-std=c++17 -O1 -g -Wall -Wextra -Wpedantic -Werror -fno-fast-math -ffp-contract=off -fsanitize=address,undefined -fno-omit-frame-pointer); link=();;
 arm) toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}; cxx=${CXX:-$toolchain-g++}; flags=(-std=c++17 -O3 -g -Wall -Wextra -Wpedantic -Werror -fno-fast-math -ffp-contract=off -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard); link=(-static-libstdc++ -static-libgcc);;
 *) echo "usage: $0 [host|sanitize|arm] [OUTPUT]" >&2; exit 2;; esac
common=(-I "$dir" -I "$root/native/adaptive/tracking")
"$cxx" "${flags[@]}" "${common[@]}" "$dir/streaming_rolling_backfill.cpp" "$dir/test_streaming_rolling_backfill.cpp" "${link[@]}" -o "$out/test-streaming-rolling-backfill"
"$cxx" "${flags[@]}" "${common[@]}" "$dir/streaming_rolling_backfill.cpp" "$dir/streaming_rolling_backfill_cli.cpp" "${link[@]}" -o "$out/leo-streaming-rolling-backfill"
if [[ "$mode" != arm ]]; then "$out/test-streaming-rolling-backfill"; fi
printf '%s\n' "$out"

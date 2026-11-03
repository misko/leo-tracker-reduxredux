#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/tmp/leo-paced-analysis-$mode}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to the matching online build}
[[ -f "$online/libleoonline.a" ]] || { echo "online library is absent" >&2; exit 3; }
mkdir -p "$out"
case "$mode" in
  host)
    cxx=${CXX:-g++}; flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread); link=()
    ;;
  sanitize)
    cxx=${CXX:-g++}; flags=(-std=c++17 -O1 -g -fno-fast-math -ffp-contract=off -pthread
      -fsanitize=address,undefined -fno-omit-frame-pointer); link=(-fsanitize=address,undefined)
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}; flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off
      -pthread -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard); link=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2; exit 2;;
esac
app="$repo/native/adaptive/application"
includes=(-I"$app" -I"$repo/native/adaptive" -I"$repo/native/adaptive/runtime"
  -I"$repo/native/adaptive/tracking" -I"$repo/native/adaptive/pipeline"
  -I"$repo/native/adaptive/location" -I"$repo/native/adaptive/ingest"
  -I"$repo/native/adaptive/scanner" -I"$repo/native/adaptive/device/local"
  -Wall -Wextra -Werror -Wpedantic)
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_CORE_ONLY \
  "$dir/test_paced_analysis.cpp" "$app/live.cpp" "$app/session.cpp" \
  "$repo/native/adaptive/ingest/ingest.cpp" "$repo/native/adaptive/timing/timebase.cpp" \
  "$repo/native/adaptive/runtime/runtime.cpp" "$repo/native/adaptive/runtime/projection.cpp" \
  "$online/libleoonline.a" "${link[@]}" -lm -o "$out/test-paced-analysis"

if [[ "$mode" != arm ]]; then
  projection=${LEO_DS9_PROJECTION_INPUT:?set LEO_DS9_PROJECTION_INPUT to the 24681-row TSV}
  pace=${LEO_PACED_SCALE:-0.01}
  "$out/test-paced-analysis" "$projection" \
    "$repo/reports/2026_09_30_native_adaptive_deployment/application/ds9-targets.tsv" \
    "$repo/reports/2026_09_30_arm_location_prototype/local/tles.txt" \
    "$repo/reports/2026_09_30_native_adaptive_deployment/application/ds9-search.tsv" \
    "$pace" | tee "$out/result.json"
fi
echo "$out"

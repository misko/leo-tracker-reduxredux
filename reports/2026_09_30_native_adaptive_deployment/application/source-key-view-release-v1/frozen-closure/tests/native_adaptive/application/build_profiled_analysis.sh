#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/var/tmp/leo-profiled-analysis-$mode}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to the matching online build}
compat=${LEO_SERVER_COMPAT_BUILD:?set LEO_SERVER_COMPAT_BUILD to the matching server-compat build}
[[ -f "$online/libleoonline.a" ]] || { echo "online library is absent" >&2; exit 3; }
[[ -f "$compat/libleoservercompat.a" && -f "$compat/libleo-server-pow3-fma.so" ]] || {
  echo "server compatibility libraries are absent" >&2; exit 3;
}
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
  -I"$repo/native/adaptive/runtime/server_compat" -I"$repo/native/adaptive/tracking"
  -I"$repo/native/adaptive/pipeline" -I"$repo/native/adaptive/location"
  -I"$repo/native/adaptive/ingest" -I"$repo/native/adaptive/scanner"
  -I"$repo/native/adaptive/device/local" -Wall -Wextra -Werror -Wpedantic)
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_CORE_ONLY \
  "$dir/test_profiled_analysis.cpp" "$app/live.cpp" "$app/session.cpp" \
  "$repo/native/adaptive/ingest/ingest.cpp" "$repo/native/adaptive/timing/timebase.cpp" \
  "$repo/native/adaptive/runtime/runtime.cpp" "$repo/native/adaptive/runtime/projection.cpp" \
  "$compat/libleoservercompat.a" "$online/libleoonline.a" -L"$compat" \
  -lleo-server-pow3-fma -Wl,-rpath,'$ORIGIN' "${link[@]}" -lm \
  -o "$out/test-profiled-analysis"
cp "$compat/libleo-server-pow3-fma.so" "$out/"

if [[ "$mode" != arm ]]; then
  projection=${LEO_DS9_PROJECTION_INPUT:?set LEO_DS9_PROJECTION_INPUT to the 24681-row TSV}
  LD_LIBRARY_PATH="$out${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$out/test-profiled-analysis" "$projection" \
    "$repo/reports/2026_09_30_native_adaptive_deployment/application/ds9-targets.tsv" \
    "$repo/reports/2026_09_30_arm_location_prototype/local/tles.txt" \
    "$repo/reports/2026_09_30_native_adaptive_deployment/application/ds9-search.tsv" \
    | tee "$out/result.json"
fi
sha256sum "$out/test-profiled-analysis" "$out/libleo-server-pow3-fma.so"
echo "$out"

#!/usr/bin/env bash
set -euo pipefail
mode=${1:-host}
out=${2:-/tmp/leo-recorded-replay-$mode}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
mkdir -p "$out"
case "$mode" in
  host)
    cxx=${CXX:-g++}; flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread); link=()
    online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to a host online build}
    ;;
  sanitize)
    cxx=${CXX:-g++}; flags=(-std=c++17 -O1 -g -fno-fast-math -ffp-contract=off -pthread
      -fsanitize=address,undefined -fno-omit-frame-pointer); link=()
    online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to a sanitizer online build}
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}; flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread
      -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard); link=(-static-libstdc++ -static-libgcc)
    online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to an ARM online build}
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [output]" >&2; exit 2;;
esac
includes=(-I"$dir" -I"$dir/../runtime" -I"$dir/../tracking" -I"$dir/../pipeline"
  -I"$dir/../location" -Wall -Wextra -Werror -Wpedantic)
"$cxx" "${flags[@]}" "${includes[@]}" "$dir/replay.cpp" "$dir/session.cpp" \
  "$dir/../ingest/ingest.cpp" "$dir/../timing/timebase.cpp" \
  "$dir/../runtime/runtime.cpp" "$dir/../runtime/projection.cpp" \
  "$online/libleoonline.a" "${link[@]}" -lm -o "$out/leo-recorded-replay"
if [[ "$mode" != arm ]]; then
  projection=${LEO_DS9_PROJECTION_INPUT:?set LEO_DS9_PROJECTION_INPUT to the 24681-row TSV}
  targets="$repo/reports/2026_09_30_native_adaptive_deployment/application/ds9-targets.tsv"
  tles="$repo/reports/2026_09_30_arm_location_prototype/local/tles.txt"
  reference="$repo/reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv"
  search="$repo/reports/2026_09_30_native_adaptive_deployment/application/ds9-search.tsv"
  [[ -f "$projection" && -f "$targets" && -f "$tles" && -f "$reference" && -f "$search" ]] || {
    echo "required recorded replay fixture is absent" >&2; exit 3;
  }
  "$repo/tests/native_adaptive/application/test_recorded_replay.sh" \
    "$out/leo-recorded-replay" "$projection" "$targets" "$tles" "$reference" "$search" \
    "$out/replay-diagnostic.tsv"
fi
echo "$out"

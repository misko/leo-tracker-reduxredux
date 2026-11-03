#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/var/tmp/leo-publication-profile-$mode}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../../.." && pwd)
online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to the matching online build}
[[ -f "$online/libleoonline.a" ]] || { echo "online library is absent" >&2; exit 3; }
mkdir -p "$out"

case "$mode" in
  host)
    cxx=${CXX:-g++}; flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread)
    link=()
    coordinator_publish=_ZN3leo8adaptive6online11Coordinator7publishElPSt10shared_ptrIKNS1_8SnapshotEE
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}; flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off
      -pthread -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    coordinator_publish=_ZN3leo8adaptive6online11Coordinator7publishExPSt10shared_ptrIKNS1_8SnapshotEE
    ;;
  *) echo "usage: $0 [host|arm] [output-directory]" >&2; exit 2;;
esac

app="$repo/native/adaptive/application"
includes=(-I"$app" -I"$repo/native/adaptive" -I"$repo/native/adaptive/runtime"
  -I"$repo/native/adaptive/tracking" -I"$repo/native/adaptive/pipeline"
  -I"$repo/native/adaptive/location" -I"$repo/native/adaptive/ingest"
  -I"$repo/native/adaptive/scanner" -I"$repo/native/adaptive/device/local"
  -Wall -Wextra -Werror -Wpedantic)
wrap=(
  -Wl,--wrap=_ZN3leo8adaptive11application7Session7publishEPSt10shared_ptrIKNS0_6online8SnapshotEE
  -Wl,--wrap="$coordinator_publish"
  -Wl,--wrap=_ZN3leo8adaptive8tracking11reconstructERKSt6vectorINS1_9CandidateESaIS3_EERKNS1_6ConfigERKNS1_13LaneExecutionE
  -Wl,--wrap=_ZN3leo8adaptive8pipeline20make_location_tracksERKNS0_8tracking6ResultERKNS1_14GraphAuthorityE
)

"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_CORE_ONLY \
  "$repo/tests/native_adaptive/application/test_paced_analysis.cpp" \
  "$dir/publication_profile_wrap.cpp" "$app/live.cpp" "$app/session.cpp" \
  "$repo/native/adaptive/ingest/ingest.cpp" "$repo/native/adaptive/timing/timebase.cpp" \
  "$repo/native/adaptive/runtime/runtime.cpp" "$repo/native/adaptive/runtime/projection.cpp" \
  "$online/libleoonline.a" "${wrap[@]}" "${link[@]}" -lm \
  -o "$out/test-publication-profile"

echo "$out"

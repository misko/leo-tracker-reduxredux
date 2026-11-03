#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/tmp/leo-live-$mode}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
scanner=${LEO_SCANNER_BUILD:?set LEO_SCANNER_BUILD to the matching timed-scanner build directory}
online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to the matching online build directory}
[[ -f "$scanner/libleoscanner.a" && -f "$scanner/libleo-adaptive-detector.so" &&
   -f "$scanner/local_iio_provider.o" && -f "$scanner/local_radio_prepare_iio.o" &&
   -f "$online/libleoonline.a" ]] || {
  echo "required scanner/online build artifacts are absent" >&2; exit 3;
}
mkdir -p "$out"

case "$mode" in
  host)
    cxx=${CXX:-g++}
    flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread)
    link=(-Wl,-l:libiio.so.0)
    ;;
  sanitize)
    cxx=${CXX:-g++}
    flags=(-std=c++17 -O1 -g -fno-fast-math -ffp-contract=off -pthread
      -fsanitize=address,undefined -fno-omit-frame-pointer)
    link=(-fsanitize=address,undefined -Wl,-l:libiio.so.0)
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}
    flags=(-std=c++17 -O2 -g -fno-fast-math -ffp-contract=off -pthread
      -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc -liio)
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2; exit 2;;
esac

includes=(-I"$dir" -I"$dir/../runtime" -I"$dir/../tracking"
  -I"$dir/../pipeline" -I"$dir/../location" -I"$dir/../ingest"
  -I"$dir/../scanner" -I"$dir/../device/local"
  -Wall -Wextra -Werror -Wpedantic)
core=("$dir/live.cpp" "$dir/session.cpp" "$dir/../ingest/ingest.cpp"
  "$dir/../timing/timebase.cpp" "$dir/../runtime/runtime.cpp"
  "$dir/../runtime/projection.cpp")

# Component-owned Analysis/background-lifecycle test. It has no detector,
# local-IIO, hardware, or RF dependency.
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_CORE_ONLY "${core[@]}" \
  "$repo/tests/native_adaptive/application/test_live.cpp" "$online/libleoonline.a" \
  -lm -o "$out/test-live"

# The executable-lifecycle test uses the same run function as production with
# fake providers. Detector/scanner calls are stubs because the injected source
# fails after preparation, specifically exercising fail-path restoration.
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_NO_MAIN "${core[@]}" \
  "$dir/../timing/posix_clock.cpp" \
  "$repo/tests/native_adaptive/application/test_live_cli.cpp" \
  "$scanner/libleoscanner.a" "$online/libleoonline.a" -lm -o "$out/test-live-cli"

# Real scanner + paced local-provider + analysis integration. The detector is
# deterministic, but capture assembly, adaptive policy, executor/backpressure,
# projection, tracking, orbit/search, and position publication are production
# implementations.
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_CORE_ONLY "${core[@]}" \
  "$repo/tests/native_adaptive/application/test_live_local_pipeline.cpp" \
  "$scanner/libleoscanner.a" "$online/libleoonline.a" -lm \
  -o "$out/test-live-local-pipeline"

cp "$scanner/libleo-adaptive-detector.so" "$out/libleo-adaptive-detector.so"
ln -sfn libleo-adaptive-detector.so "$out/libleo-adaptive-detector.so.1"
"$cxx" "${flags[@]}" "${includes[@]}" "${core[@]}" \
  "$dir/../timing/posix_clock.cpp" "$scanner/libleoscanner.a" \
  "$scanner/local_iio_provider.o" "$scanner/local_radio_prepare_iio.o" \
  "$online/libleoonline.a" -L"$out" -Wl,-l:libleo-adaptive-detector.so \
  '-Wl,-rpath,$ORIGIN' "${link[@]}" -lm -o "$out/leo-adaptive-live"

if [[ "$mode" != arm ]]; then
  "$out/test-live"
  "$out/test-live-cli"
  "$out/test-live-local-pipeline"
  "$out/leo-adaptive-live" >"$out/capabilities.json"
fi
echo "$out"

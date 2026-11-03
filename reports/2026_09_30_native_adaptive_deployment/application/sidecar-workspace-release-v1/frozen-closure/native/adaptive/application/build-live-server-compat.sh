#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
out=${2:-/var/tmp/leo-live-server-compat-$mode}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$dir/../../.." && pwd)
scanner=${LEO_SCANNER_BUILD:?set LEO_SCANNER_BUILD to the matching scanner build}
online=${LEO_ONLINE_LIBRARY:?set LEO_ONLINE_LIBRARY to the matching online build}
compat=${LEO_SERVER_COMPAT_BUILD:?set LEO_SERVER_COMPAT_BUILD to the matching server-compat build}
source_package=${LEO_SERVER_COMPAT_SOURCE_PACKAGE:?set LEO_SERVER_COMPAT_SOURCE_PACKAGE to the verified source package directory}
[[ -f "$scanner/libleoscanner.a" && -f "$scanner/libleo-adaptive-detector.so" &&
   -f "$scanner/local_iio_provider.o" && -f "$scanner/local_radio_prepare_iio.o" &&
   -f "$online/libleoonline.a" && -f "$compat/libleoservercompat.a" &&
   -f "$compat/libleo-server-pow3-fma.so" &&
   -f "$source_package/corresponding-source.tar.gz" &&
   -f "$source_package/README.md" && -f "$source_package/source-manifest.json" ]] || {
  echo "required scanner/online/server-compat artifacts are absent" >&2; exit 3;
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

includes=(-I"$dir" -I"$dir/../runtime" -I"$dir/../runtime/server_compat"
  -I"$dir/../tracking" -I"$dir/../pipeline" -I"$dir/../location"
  -I"$dir/../ingest" -I"$dir/../scanner" -I"$dir/../device/local"
  -Wall -Wextra -Werror -Wpedantic)
core=("$dir/live.cpp" "$dir/session.cpp" "$dir/../ingest/ingest.cpp"
  "$dir/../timing/timebase.cpp" "$dir/../runtime/runtime.cpp"
  "$dir/../runtime/projection.cpp")

# Generic profiled lifecycle test. Its fake neutral port deliberately avoids a
# dependency on the concrete compatibility implementation.
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_NO_MAIN "${core[@]}" \
  "$dir/../timing/posix_clock.cpp" \
  "$repo/tests/native_adaptive/application/test_live_profiled_cli.cpp" \
  "$scanner/libleoscanner.a" "$online/libleoonline.a" -lm \
  -o "$out/test-live-profiled-cli"

cp "$scanner/libleo-adaptive-detector.so" "$out/libleo-adaptive-detector.so"
ln -sfn libleo-adaptive-detector.so "$out/libleo-adaptive-detector.so.1"
cp "$compat/libleo-server-pow3-fma.so" "$out/libleo-server-pow3-fma.so"
cp "$source_package/corresponding-source.tar.gz" "$out/"
cp "$source_package/README.md" "$out/server-compat-corresponding-source-README.md"
cp "$source_package/source-manifest.json" "$out/server-compat-source-manifest.json"
cp "$dir/../runtime/server_compat/glibc/COPYING.LIB" "$out/COPYING.LIB"

"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_NO_MAIN "${core[@]}" \
  "$dir/live_server_compat_main.cpp" "$dir/../timing/posix_clock.cpp" \
  "$scanner/libleoscanner.a" "$scanner/local_iio_provider.o" \
  "$scanner/local_radio_prepare_iio.o" "$online/libleoonline.a" \
  "$compat/libleoservercompat.a" -L"$out" -Wl,-l:libleo-adaptive-detector.so \
  -lleo-server-pow3-fma '-Wl,-rpath,$ORIGIN' "${link[@]}" -lm \
  -o "$out/leo-adaptive-live-server-compat"

if [[ "$mode" != arm ]]; then
  "$out/test-live-profiled-cli"
  "$out/leo-adaptive-live-server-compat" >"$out/capabilities.json"
fi
sha256sum "$out/leo-adaptive-live-server-compat" \
  "$out/libleo-server-pow3-fma.so" "$out/corresponding-source.tar.gz" \
  "$out/server-compat-corresponding-source-README.md" \
  "$out/server-compat-source-manifest.json" "$out/COPYING.LIB"
echo "$out"

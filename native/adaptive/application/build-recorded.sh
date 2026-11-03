#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
output=${2:?usage: build-recorded.sh MODE OUTPUT}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
root=$(cd -- "$dir/../../.." && pwd)
scanner=${LEO_RECORDED_SCANNER_LIBRARY:?set to final recorded scanner build directory}
source_lib=${LEO_RECORDED_SOURCE_LIBRARY:?set to final recorded source build directory}
adapter=${LEO_CORRECTED_ADAPTER_LIBRARY:?set to corrected profile adapter build directory}
corrected=${LEO_CORRECTED_DETECTOR_STATIC:?set to corrected-only detector archive}
fftw_float=${LEO_FFTW_FLOAT_STATIC:?set to matching fftw3f archive}
fftw_double=${LEO_FFTW_DOUBLE:?set to matching fftw3 library/archive}
online=${LEO_ONLINE_LIBRARY:?set to coherent online build directory}
compat=${LEO_SERVER_COMPAT_LIBRARY:?set to server compatibility build directory}
for required in "$scanner/libleoscanner.a" "$source_lib/recorded_source.o" \
    "$adapter/libleocorrectedprofileadapter.a" "$corrected" "$fftw_float" "$fftw_double" \
    "$online/libleoonline.a" "$compat/libleoservercompat.a" \
    "$compat/libleo-server-pow3-fma.so"; do
  [[ -f $required ]] || { echo "missing dependency: $required" >&2; exit 3; }
done
mkdir -p "$output"

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
  *) echo "usage: build-recorded.sh host|sanitize|arm OUTPUT" >&2; exit 2;;
esac

includes=(-I"$dir" -I"$root/native/adaptive" -I"$root/native/adaptive/runtime"
  -I"$root/native/adaptive/runtime/server_compat" -I"$root/native/adaptive/tracking"
  -I"$root/native/adaptive/pipeline" -I"$root/native/adaptive/location"
  -I"$root/native/adaptive/ingest" -I"$root/native/adaptive/scanner"
  -I"$root/native/adaptive/detector" -I"$root/native/adaptive/device/recorded"
  -Wall -Wextra -Werror -Wpedantic)
core=("$dir/recorded_main.cpp" "$dir/recorded_bundle.cpp" "$dir/corrected_geometry.cpp"
  "$dir/live.cpp" "$dir/session.cpp" "$root/native/adaptive/ingest/ingest.cpp"
  "$root/native/adaptive/timing/timebase.cpp" "$root/native/adaptive/runtime/runtime.cpp"
  "$root/native/adaptive/runtime/projection.cpp")
libraries=("$source_lib/recorded_source.o" "$scanner/libleoscanner.a"
  "$adapter/libleocorrectedprofileadapter.a" "$corrected" "$fftw_float" "$fftw_double"
  "$compat/libleoservercompat.a" "$online/libleoonline.a")

cp "$compat/libleo-server-pow3-fma.so" "$output/"
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_CORE_ONLY \
  "${core[@]}" "${libraries[@]}" \
  -L"$output" -lleo-server-pow3-fma -Wl,-rpath,'$ORIGIN' "${link[@]}" -lm \
  -o "$output/leo-recorded-ds9"
"$cxx" "${flags[@]}" "${includes[@]}" -DLEO_LIVE_CORE_ONLY \
  -DLEO_RECORDED_APPLICATION_NO_MAIN \
  "${core[@]}" "$root/tests/native_adaptive/application/test_recorded_application.cpp" \
  "${libraries[@]}" -L"$output" -lleo-server-pow3-fma -Wl,-rpath,'$ORIGIN' \
  "${link[@]}" -lm -o "$output/test-recorded-application"

if [[ "$mode" != arm ]]; then
  "$output/test-recorded-application" "$output"
fi
sha256sum "$output/leo-recorded-ds9" "$output/test-recorded-application" \
  "$output/libleo-server-pow3-fma.so" >"$output/build-sha256.txt"
echo "$output"

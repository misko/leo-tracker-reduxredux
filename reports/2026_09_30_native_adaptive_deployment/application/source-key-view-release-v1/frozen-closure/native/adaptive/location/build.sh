#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../.." && pwd)"
source_dir="$root/native/adaptive/location"
test_dir="$root/tests/native_adaptive/location"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"

case "$mode" in
  host)
    cxx="${CXX:-g++}"
    ar="${AR:-ar}"
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC)
    link_flags=(-pthread)
    ;;
  sanitize)
    cxx="${CXX:-g++}"
    ar="${AR:-ar}"
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math -fPIC
      -fsanitize=address,undefined)
    link_flags=(-pthread)
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cxx="${CXX:-$toolchain-g++}"
    ar="${AR:-$toolchain-ar}"
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link_flags=(-pthread -static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2
    exit 2
    ;;
esac

common=(-I "$source_dir" -Wall -Wextra -Wpedantic)
sources=(orbit score search)
objects=()
for name in "${sources[@]}"; do
  object="$output/$name.o"
  "$cxx" "${flags[@]}" "${common[@]}" -c "$source_dir/$name.cpp" -o "$object"
  objects+=("$object")
done
"$cxx" "${flags[@]}" -w -I "$source_dir" \
  -c "$source_dir/vendor/sgp4/SGP4.cpp" -o "$output/sgp4.o"
objects+=("$output/sgp4.o")
"$ar" rcs "$output/libleolocation.a" "${objects[@]}"
"$cxx" -shared "${flags[@]}" "${objects[@]}" "${link_flags[@]}" -lm \
  -o "$output/libleolocation.so"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/location_cli.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/leo-location"

"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_location.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/test_location"

"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_score_stencil.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/test_score_stencil"

if [[ "$mode" != arm ]]; then
  "$output/test_location"
  "$output/test_score_stencil"
fi

"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_tle_id.cpp" \
  "${link_flags[@]}" -o "$output/test_tle_id"
if [[ "$mode" != arm ]]; then
  "$output/test_tle_id"
fi

echo "$output"

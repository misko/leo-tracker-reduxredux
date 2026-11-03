#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/location"
test_dir="$root/tests/native_adaptive/location"
output="${2:-/tmp/leo-location-stencil-research-$mode}"
mkdir -p "$output/control" "$output/candidate"

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
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC
      -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link_flags=(-pthread -static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2
    exit 2
    ;;
esac

common=(-I "$source_dir" -I "$source_dir/research" -Wall -Wextra -Wpedantic)

for name in orbit search; do
  "$cxx" "${flags[@]}" "${common[@]}" -c "$source_dir/$name.cpp" \
    -o "$output/$name.o"
done
"$cxx" "${flags[@]}" -w -I "$source_dir" \
  -c "$source_dir/vendor/sgp4/SGP4.cpp" -o "$output/sgp4.o"

"$cxx" "${flags[@]}" "${common[@]}" -c "$source_dir/score.cpp" \
  -o "$output/control/score.o"
"$cxx" "${flags[@]}" "${common[@]}" \
  -c "$source_dir/research/score_interpolation_stencil.cpp" \
  -o "$output/candidate/score.o"

common_objects=("$output/orbit.o" "$output/search.o" "$output/sgp4.o")
"$ar" rcs "$output/control/libleolocation-control.a" \
  "${common_objects[@]}" "$output/control/score.o"
"$ar" rcs "$output/candidate/libleolocation-stencil-research.a" \
  "${common_objects[@]}" "$output/candidate/score.o"

"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/location_cli.cpp" \
  "$output/control/libleolocation-control.a" "${link_flags[@]}" -lm \
  -o "$output/leo-location-control"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/location_cli.cpp" \
  "$output/candidate/libleolocation-stencil-research.a" "${link_flags[@]}" -lm \
  -o "$output/leo-location-stencil-research"

"$cxx" "${flags[@]}" "${common[@]}" \
  "$test_dir/research/test_score_interpolation_stencil.cpp" \
  "$output/candidate/libleolocation-stencil-research.a" "${link_flags[@]}" -lm \
  -o "$output/test-score-interpolation-stencil"
"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_location.cpp" \
  "$output/candidate/libleolocation-stencil-research.a" "${link_flags[@]}" -lm \
  -o "$output/test-location-stencil-research"

if [[ "$mode" != arm ]]; then
  "$output/test-score-interpolation-stencil"
  "$output/test-location-stencil-research"
fi

echo "$output"

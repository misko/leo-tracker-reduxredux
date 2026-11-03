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
sources=(orbit score search session)
objects=()
for name in "${sources[@]}"; do
  object="$output/$name.o"
  "$cxx" "${flags[@]}" "${common[@]}" -c "$source_dir/$name.cpp" -o "$object"
  objects+=("$object")
done
# The candidate matcher uses the prototype's explicit floating-point policy.
# Keep this local so existing scorer build semantics remain unchanged.
"$cxx" "${flags[@]}" -ffp-contract=off "${common[@]}" \
  -c "$source_dir/doppler_match/matcher.cpp" -o "$output/doppler_match.o"
objects+=("$output/doppler_match.o")
"$cxx" "${flags[@]}" -w -I "$source_dir" \
  -c "$source_dir/vendor/sgp4/SGP4.cpp" -o "$output/sgp4.o"
objects+=("$output/sgp4.o")
"$ar" rcs "$output/libleolocation.a" "${objects[@]}"
"$cxx" -shared "${flags[@]}" "${objects[@]}" "${link_flags[@]}" -lm \
  -o "$output/libleolocation.so"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/location_cli.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/leo-location"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/orbit_cli.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/leo-orbit"
"$cxx" "${flags[@]}" "${common[@]}" "$source_dir/doppler_match/cli.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/leo-doppler-match"
"$cxx" "${flags[@]}" -ffp-contract=off "${common[@]}" "$test_dir/test_doppler_match.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/test_doppler_match"

"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_location.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/test_location"

"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_score_stencil.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/test_score_stencil"
"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_session.cpp" \
  "$output/libleolocation.a" "${link_flags[@]}" -lm -o "$output/test_session"
"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/research/test_catalogue_index.cpp" \
  "${link_flags[@]}" -o "$output/test_catalogue_index"

if [[ "$mode" != arm ]]; then
  "$output/test_doppler_match"
  "$output/test_location"
  "$output/test_score_stencil"
  "$output/test_session"
  "$output/test_catalogue_index"
fi

"$cxx" "${flags[@]}" "${common[@]}" "$test_dir/test_tle_id.cpp" \
  "${link_flags[@]}" -o "$output/test_tle_id"
if [[ "$mode" != arm ]]; then
  "$output/test_tle_id"
  python3 "$test_dir/check_doppler_match_cli.py" "$output/leo-doppler-match"
  python3 "$test_dir/check_orbit_cli.py" "$output/leo-orbit"
  python3 "$test_dir/check_score_site_cli.py" "$output/leo-location"
fi

echo "$output"

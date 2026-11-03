#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
location="$root/native/adaptive/location"
tracking="$root/native/adaptive/tracking"
pipeline="$root/native/adaptive/pipeline"
runtime="$root/native/adaptive/runtime"
research="$location/research"
tests="$root/tests/native_adaptive/location/research"
out="${2:-$research/build/$mode-score-reuse}"
mkdir -p "$out"

case "$mode" in
  host)
    cxx="${CXX:-g++}"
    flags=(-std=c++17 -O3 -fno-fast-math -ffp-contract=off -fPIC)
    link=(-pthread)
    ;;
  sanitize)
    cxx="${CXX:-g++}"
    flags=(-std=c++17 -O1 -g -fno-fast-math -ffp-contract=off -fPIC
      -fno-omit-frame-pointer -fsanitize=address,undefined)
    link=(-pthread)
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cxx="${CXX:-$toolchain-g++}"
    flags=(-std=c++17 -O3 -fno-fast-math -ffp-contract=off -fPIC
      -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-pthread -static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2; exit 2;;
esac

include=(-I "$research" -I "$location" -I "$tracking" -I "$pipeline" -I "$runtime"
  -Wall -Wextra -Werror -Wpedantic)
sources=(
  "$research/exact_track_score_cache.cpp"
  "$tracking/tracking.cpp"
  "$pipeline/pipeline.cpp"
  "$location/orbit.cpp"
  "$location/score.cpp"
  "$location/vendor/sgp4/SGP4.cpp"
)

objects=()
for source in "${sources[@]:0:${#sources[@]}-1}"; do
  name="$(basename "${source%.cpp}")"
  object="$out/$name.o"
  "$cxx" "${flags[@]}" "${include[@]}" -c "$source" -o "$object"
  objects+=("$object")
done
"$cxx" "${flags[@]}" -w -I "$location" -c \
  "$location/vendor/sgp4/SGP4.cpp" -o "$out/sgp4.o"
objects+=("$out/sgp4.o")

"$cxx" "${flags[@]}" "${include[@]}" "$tests/test_exact_track_score_cache.cpp" \
  "$out/exact_track_score_cache.o" "$out/score.o" "$out/orbit.o" "$out/sgp4.o" \
  "${link[@]}" -lm -o "$out/test-exact-score-cache"
"$cxx" "${flags[@]}" "${include[@]}" "$tests/test_ds9_exact_score_reuse.cpp" \
  "${objects[@]}" "${link[@]}" -lm -o "$out/test-ds9-exact-score-reuse"

if [[ "$mode" != arm ]]; then
  "$out/test-exact-score-cache"
  candidates="$root/reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv"
  graph="$root/reports/2026_09_30_native_adaptive_deployment/tracking/graph-candidates.tsv"
  tles="$root/reports/2026_09_30_arm_location_prototype/local/tles.txt"
  "$out/test-ds9-exact-score-reuse" "$candidates" "$graph" "$tles" |
    tee "$out/ds9-exact-score-reuse.json"
fi

echo "$out"

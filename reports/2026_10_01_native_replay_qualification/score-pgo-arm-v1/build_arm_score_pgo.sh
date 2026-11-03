#!/usr/bin/env bash
# Train only the scorer on physical ARM, then rebuild at the identical path.
set -euo pipefail
mode="${1:?generate or use}"
library="${2:?qualified ARM location object directory}"
output="${3:?absolute output directory}"
[[ "$output" == /* ]] || { echo 'output must be absolute' >&2; exit 2; }
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
mkdir -p "$output"
case "$mode" in
  generate)
    [[ ! -e "$output/score.o" && ! -e "$output/score.gcda" ]] || {
      echo 'preserve existing training evidence; use a new build directory' >&2; exit 2; }
    (cd "$root"; sha256sum native/adaptive/location/score.cpp \
      native/adaptive/location/location.h native/adaptive/location/score_stencil_internal.hpp \
      native/adaptive/location/research/*.hpp) > "$output/source-sha256.txt"
    profile=(-fprofile-generate -fprofile-update=atomic)
    ;;
  use)
    [[ -s "$output/score.gcda" ]] || { echo 'missing physical ARM profile' >&2; exit 2; }
    (cd "$root"; sha256sum -c "$output/source-sha256.txt")
    profile=(-fprofile-use -Werror=coverage-mismatch)
    ;;
  *) exit 2;;
esac
flags=(-std=c++17 -O3 -fno-fast-math -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard
  -I "$root/native/adaptive/location")
research=(-DLEO_RESEARCH_HELDOUT_BOUND -DLEO_RESEARCH_SUBSET_BOUND
  -DLEO_RESEARCH_PLANNED_BOUND -DLEO_RESEARCH_HORIZON_PREFIX -DLEO_RESEARCH_ENDPOINT_BANK)
"$toolchain-g++" "${flags[@]}" "${research[@]}" "${profile[@]}" -c \
  "$root/native/adaptive/location/score.cpp" -o "$output/score.o"
"$toolchain-ar" rcs "$output/libleolocation.a" "$library/orbit.o" \
  "$library/search.o" "$library/sgp4.o" "$output/score.o"
link=(-pthread -static-libstdc++ -static-libgcc -lm)
if [[ "$mode" == generate ]]; then link+=(-fprofile-generate); fi
"$toolchain-g++" "${flags[@]}" -DLEO_RESEARCH_SCORE_WARM_START \
  -DLEO_RESEARCH_CAPPED_SEARCH -DLEO_RESEARCH_SEARCH_PROGRESS \
  "$root/native/adaptive/location/location_cli.cpp" "$output/libleolocation.a" \
  "${link[@]}" -o "$output/leo-location"
"$toolchain-g++" "${flags[@]}" \
  "$root/tests/native_adaptive/location/research/bench_search_sites.cpp" \
  "$output/libleolocation.a" "${link[@]}" -o "$output/bench-search-sites"
if [[ "$mode" == use ]]; then
  for test in test_location test_score_stencil; do
    "$toolchain-g++" "${flags[@]}" "$root/tests/native_adaptive/location/$test.cpp" \
      "$output/libleolocation.a" "${link[@]}" -o "$output/$test"
  done
fi

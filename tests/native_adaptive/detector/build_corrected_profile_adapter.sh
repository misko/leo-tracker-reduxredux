#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
output=${2:-"/var/tmp/leo-corrected-profile-adapter-$mode"}
source_root=${LEO_CORRECTED_SOURCE_ROOT:-"$root/reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/wideband-research/source/native/adaptive/detector"}
source_root=$(readlink -f "$source_root")
corrected_static=${LEO_CORRECTED_DETECTOR_STATIC:?set LEO_CORRECTED_DETECTOR_STATIC to the corrected-only archive}
corrected_sha=${LEO_CORRECTED_DETECTOR_SHA256:?set LEO_CORRECTED_DETECTOR_SHA256 to its expected digest}
fftw_float=${LEO_FFTW_FLOAT_STATIC:?set LEO_FFTW_FLOAT_STATIC}
fftw_double=${LEO_FFTW_DOUBLE:?set LEO_FFTW_DOUBLE}
mkdir -p "$output"

check_hash() {
  local expected=$1 path=$2 actual
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  if [[ $actual != "$expected" ]]; then
    echo "hash mismatch: $path expected=$expected actual=$actual" >&2
    exit 1
  fi
}

# These are the source hashes bound by corrected-wideband-arm-v1.  In
# particular presence.c carries the 22-slot storage declaration, while the
# reference source carries the 22-symbol peer fallback and 1.6 MHz guard.
check_hash cc41a7d49e9150d7d528be9a837239d3226bce108f2e54107af32b71f534ce76 \
  "$source_root/native_glrt_research.h"
check_hash 7a6aedac1f7b1587c70a87a6ac054f0abc0e0d20d0f03c1a5f82531458355496 \
  "$source_root/native_glrt_reference.c"
check_hash b1b74aecd47b730f214f8d44061a42a5d3200579220b017ab99301641633cb25 \
  "$source_root/kernel/private/full_search_reference.c"
check_hash 9f903b7d3498b1cf60997a5d8b914d741b74ee5fe91813fb19244f61c5d71157 \
  "$source_root/kernel/private/native_presence/presence.c"
check_hash "$corrected_sha" "$corrected_static"
test -f "$fftw_float" && test -f "$fftw_double"

case "$mode" in
  host)
    cc=${CC:-gcc}; cxx=${CXX:-g++}; ar=${AR:-ar}
    common=(-O2 -g -fPIC -fno-fast-math -ffp-contract=off)
    link=()
    ;;
  sanitize)
    cc=${CC:-gcc}; cxx=${CXX:-g++}; ar=${AR:-ar}
    common=(-O1 -g -fPIC -fno-fast-math -ffp-contract=off
      -fno-omit-frame-pointer -fsanitize=address,undefined)
    link=(-fsanitize=address,undefined)
    ;;
  tsan)
    cc=${CC:-gcc}; cxx=${CXX:-g++}; ar=${AR:-ar}
    common=(-O1 -g -fPIC -fno-fast-math -ffp-contract=off
      -fno-omit-frame-pointer -fsanitize=thread)
    link=(-fsanitize=thread)
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cc=${CC:-"$toolchain-gcc"}; cxx=${CXX:-"$toolchain-g++"}; ar=${AR:-"$toolchain-ar"}
    common=(-O2 -g -fPIC -fno-fast-math -ffp-contract=off
      -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|tsan|arm] [output-directory]" >&2
    exit 2
    ;;
esac

warnings=(-Wall -Wextra -Werror -Wpedantic)
include=(-I"$root/native/adaptive/detector" -I"$root/native/adaptive")
"$cc" -std=c11 "${common[@]}" "${warnings[@]}" -I"$source_root" \
  "${include[@]}" -MMD -MF "$output/corrected_profile_backend.d" \
  -c "$root/native/adaptive/detector/corrected_profile_backend.c" \
  -o "$output/corrected_profile_backend.o"
if ! grep -Fq "$source_root/native_glrt_research.h" \
    "$output/corrected_profile_backend.d"; then
  echo "backend did not bind frozen corrected header" >&2
  exit 1
fi
if grep -Fq "$root/native/adaptive/detector/native_glrt_research.h" \
    "$output/corrected_profile_backend.d"; then
  echo "backend resolved mutable worktree corrected header" >&2
  exit 1
fi
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${include[@]}" \
  -c "$root/native/adaptive/detector/corrected_profile_adapter.cpp" \
  -o "$output/corrected_profile_adapter.o"
"$ar" rcs "$output/libleocorrectedprofileadapter.a" \
  "$output/corrected_profile_adapter.o" "$output/corrected_profile_backend.o"
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${include[@]}" \
  "$root/tests/native_adaptive/detector/test_corrected_profile_adapter.cpp" \
  "$output/libleocorrectedprofileadapter.a" "$corrected_static" "$fftw_float" \
  "$fftw_double" "${link[@]}" -lpthread -lm \
  -o "$output/test-corrected-profile-adapter"

sha256sum "$source_root/native_glrt_research.h" \
  "$source_root/native_glrt_reference.c" \
  "$source_root/kernel/private/full_search_reference.c" \
  "$source_root/kernel/private/native_presence/presence.c" \
  "$output/corrected_profile_backend.d" \
  "$corrected_static" "$output/libleocorrectedprofileadapter.a" \
  "$output/test-corrected-profile-adapter" > "$output/build-sha256.txt"

if [[ "$mode" != arm ]]; then
  fixture="$root/reports/2026_09_30_native_adaptive_deployment/ds9"
  "$output/test-corrected-profile-adapter" \
    "$fixture/location-templates/lower-exact.c128" \
    "$fixture/location-templates/lower-control.c128" \
    "$fixture/location-selection/raw/scan-fw-3cfdaa6d75762cad-276.ci16"
fi
echo "$output"

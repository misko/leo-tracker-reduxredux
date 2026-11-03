#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
root=$(cd -- "$(dirname -- "$0")/../../../../.." && pwd)
dir="$root/native/adaptive/tracking/research/fast_tracks"
out=${2:-"$dir/build/$mode"}
mkdir -p "$out"

case "$mode" in
  host)
    cxx=${CXX:-g++}
    flags=(-std=c++17 -O3 -g -Wall -Wextra -Wpedantic -Werror -fno-fast-math -ffp-contract=off)
    link=()
    ;;
  sanitize)
    cxx=${CXX:-g++}
    flags=(-std=c++17 -O1 -g -Wall -Wextra -Wpedantic -Werror -fno-fast-math
      -ffp-contract=off -fsanitize=address,undefined -fno-omit-frame-pointer)
    link=()
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}
    flags=(-std=c++17 -O3 -g -Wall -Wextra -Wpedantic -Werror -fno-fast-math
      -ffp-contract=off -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 [host|sanitize|arm] [OUTPUT]" >&2; exit 2;;
esac

common=(-I "$dir" -I "$root/native/adaptive/tracking")
"$cxx" "${flags[@]}" "${common[@]}" "$dir/fast_tracks.cpp" \
  "$dir/test_fast_tracks.cpp" "${link[@]}" -o "$out/test-fast-tracks"
"$cxx" "${flags[@]}" "${common[@]}" "$dir/fast_tracks.cpp" \
  "$dir/fast_tracks_cli.cpp" "${link[@]}" -o "$out/leo-fast-tracks"
"$cxx" "${flags[@]}" -Wno-subobject-linkage "${common[@]}" \
  "$dir/seed_expand.cpp" "$dir/test_seed_expand.cpp" "${link[@]}" \
  -o "$out/test-seed-expand"
"$cxx" "${flags[@]}" -Wno-subobject-linkage "${common[@]}" \
  "$dir/seed_expand.cpp" "$dir/seed_expand_cli.cpp" "${link[@]}" \
  -o "$out/leo-seed-expand"
if [[ "$mode" != arm ]]; then
  "$out/test-fast-tracks"
  "$out/test-seed-expand"
fi
printf '%s\n' "$out"

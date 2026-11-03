#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../.." && pwd)"
source_dir="$root/native/adaptive/online"
runtime_dir="$root/native/adaptive/runtime"
tracking_dir="$root/native/adaptive/tracking"
pipeline_dir="$root/native/adaptive/pipeline"
location_dir="$root/native/adaptive/location"
test_dir="$root/tests/native_adaptive/online"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"

case "$mode" in
  host)
    cxx="${CXX:-g++}"; ar="${AR:-ar}"
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC)
    link=(-pthread)
    ;;
  sanitize)
    cxx="${CXX:-g++}"; ar="${AR:-ar}"
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math -fPIC
      -fsanitize=address,undefined)
    link=(-pthread)
    ;;
  thread)
    cxx="${CXX:-g++}"; ar="${AR:-ar}"
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math -fPIC
      -fsanitize=thread)
    link=(-pthread)
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cxx="${CXX:-$toolchain-g++}"; ar="${AR:-$toolchain-ar}"
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-pthread -static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 [host|sanitize|thread|arm] [output-directory]" >&2; exit 2;;
esac

include=(-I "$source_dir" -I "$runtime_dir" -I "$tracking_dir" -I "$pipeline_dir" \
  -I "$location_dir" -Wall -Wextra -Wpedantic)
declare -a objects=()
compile() {
  local name="$1" path="$2"
  "$cxx" "${flags[@]}" "${include[@]}" -c "$path" -o "$output/$name.o"
  objects+=("$output/$name.o")
}
compile online "$source_dir/online.cpp"
base_library="${LEO_ONLINE_BASE_LIBRARY:-}"
if [[ -n "$base_library" ]]; then
  [[ -f "$base_library" ]] || { echo "base online archive is absent" >&2; exit 3; }
  for member in tracking pipeline orbit score search sgp4; do
    archive_member="$member.o"
    "$ar" t "$base_library" | grep -qx "$archive_member" || archive_member="base-$member.o"
    "$ar" p "$base_library" "$archive_member" >"$output/base-$member.o"
    [[ -s "$output/base-$member.o" ]] || { echo "base archive lacks $member.o" >&2; exit 3; }
    objects+=("$output/base-$member.o")
  done
else
  compile tracking "$tracking_dir/tracking.cpp"
  compile pipeline "$pipeline_dir/pipeline.cpp"
  compile orbit "$location_dir/orbit.cpp"
  compile score "$location_dir/score.cpp"
  compile search "$location_dir/search.cpp"
  "$cxx" "${flags[@]}" -w -I "$location_dir" \
    -c "$location_dir/vendor/sgp4/SGP4.cpp" -o "$output/sgp4.o"
  objects+=("$output/sgp4.o")
fi

"$ar" rcs "$output/libleoonline.a" "${objects[@]}"
"$cxx" -shared "${flags[@]}" "${objects[@]}" "${link[@]}" -lm \
  -o "$output/libleoonline.so"
"$cxx" "${flags[@]}" "${include[@]}" "$test_dir/test_online.cpp" \
  "$output/libleoonline.a" "${link[@]}" -lm -o "$output/test_online"
"$cxx" "${flags[@]}" "${include[@]}" "$test_dir/test_ds9_online.cpp" \
  "$output/libleoonline.a" "${link[@]}" -lm \
  -Wl,--wrap=leo_search_submit -Wl,--wrap=leo_point_score_finish \
  -o "$output/leo-online-replay"
ln -sfn leo-online-replay "$output/test_ds9_online"

if [[ "$mode" != arm ]]; then
  tle="$root/reports/2026_09_30_arm_location_prototype/local/tles.txt"
  candidates="$root/reports/2026_09_30_native_adaptive_deployment/ds9/complete-scan-e1/candidates.tsv"
  graph="$root/reports/2026_09_30_native_adaptive_deployment/ds9/complete-scan-e1/graph-candidates.tsv"
  [[ -f "$tle" && -f "$candidates" && -f "$graph" ]] || {
    echo "required DS9 online component fixtures are absent" >&2; exit 3;
  }
  "$output/test_online" "$tle"
  "$output/leo-online-replay" "$candidates" "$graph" "$tle"
fi

echo "$output"

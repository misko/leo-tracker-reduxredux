#!/usr/bin/env bash
set -euo pipefail
mode=${1:?host, sanitize, or arm}
variant=${2:?view, candidate, or sidecar}
output=${3:?output directory}
base=$(cd -- "$(dirname -- "$0")" && pwd)
source_dir="$base/source"
mkdir -p "$output/tmp"
export TMPDIR="$output/tmp"
case "$mode" in
  host)
    compiler=${CXX:-g++}
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC)
    link=()
    ;;
  sanitize)
    compiler=${CXX:-g++}
    flags=(-std=c++17 -O1 -g -fno-omit-frame-pointer -fno-fast-math -fPIC
      -fsanitize=address,undefined)
    link=()
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    compiler=${CXX:-$toolchain-g++}
    flags=(-std=c++17 -O3 -fno-fast-math -fPIC -mcpu=cortex-a9 -mfpu=neon
      -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *) exit 2 ;;
esac
case "$variant" in
  view) implementation="$source_dir/view.cpp" ;;
  candidate) implementation="$source_dir/candidate.cpp" ;;
  sidecar) implementation="$source_dir/sidecar.cpp" ;;
  *) exit 2 ;;
esac
common=(-Wall -Wextra -Wpedantic -pthread -I "$source_dir")
"$compiler" "${flags[@]}" "${common[@]}" "$implementation" \
  "$source_dir/tracking_cli.cpp" "${link[@]}" -o "$output/tracking"
"$compiler" "${flags[@]}" "${common[@]}" "$implementation" \
  "$source_dir/tracking_prefix_benchmark.cpp" "${link[@]}" -o "$output/prefix"
if [[ "$variant" == candidate ]]; then
  "$compiler" "${flags[@]}" "${common[@]}" -I "$base" \
    "$base/test_dense_source_workspace.cpp" "${link[@]}" \
    -o "$output/test-dense-source-workspace"
elif [[ "$variant" == sidecar ]]; then
  "$compiler" "${flags[@]}" "${common[@]}" -I "$base" \
    "$base/test_sidecar_workspace.cpp" "${link[@]}" \
    -o "$output/test-sidecar-workspace"
fi

#!/usr/bin/env bash
set -euo pipefail
mode=${1:?host or arm}
variant=${2:?control or research}
output=${3:?output directory}
source_dir=$(cd -- "$(dirname -- "$0")/source" && pwd)
mkdir -p "$output/tmp"
export TMPDIR="$output/tmp"
flags=(-std=c++17 -O3 -fno-fast-math -pthread -I "$source_dir")
case "$mode" in
  host) compiler=${CXX:-g++} ;;
  arm)
    compiler=${CXX:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-g++}
    flags+=(-Wno-psabi -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard
      -static-libstdc++ -static-libgcc)
    ;;
  *) exit 2 ;;
esac
case "$variant" in
  control) implementation="$source_dir/control.cpp" ;;
  research) implementation="$source_dir/tracking.cpp" ;;
  *) exit 2 ;;
esac
"$compiler" "${flags[@]}" "$implementation" \
  "$source_dir/tracking_prefix_benchmark.cpp" -o "$output/prefix"
"$compiler" "${flags[@]}" "$implementation" \
  "$source_dir/tracking_cli.cpp" -o "$output/tracking"

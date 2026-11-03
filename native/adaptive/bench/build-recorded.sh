#!/usr/bin/env bash
set -euo pipefail
out=${1:?output executable}
header=${2:?exact detector header directory}
library=${3:?exact detector archive}
float_fft=${4:?ARM float FFT archive}
double_fft=${5:?ARM double FFT library}
dir=$(cd -- "$(dirname -- "$0")" && pwd)
cxx=${CXX:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-g++}
"$cxx" -std=c++17 -O2 -Wall -Wextra -Werror -Wno-error=lto-type-mismatch \
  -fno-fast-math -pthread -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard \
  -static-libstdc++ -static-libgcc -I"$header" "$dir/recorded_paced.cpp" \
  "$dir/../runtime/runtime.cpp" "$dir/../runtime/projection.cpp" \
  "$library" "$float_fft" "$double_fft" -lm -o "$out"

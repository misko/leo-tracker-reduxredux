#!/bin/sh
set -eu

mode=${1:-host}
out=${2:-/tmp/leo-server-pow3-$mode}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime=$(CDPATH= cd -- "$here/../.." && pwd)
mkdir -p "$out"

case "$mode" in
host)
    cc=${CC:-gcc}; cxx=${CXX:-g++}
    cflags="-O2 -ffp-contract=off -fPIC"
    cxxflags="-O2 -fno-fast-math -ffp-contract=off"
    link=""
    ;;
arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cc=${CC:-$toolchain-gcc}; cxx=${CXX:-$toolchain-g++}
    cflags="-O2 -ffp-contract=off -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard"
    cxxflags="-O2 -fno-fast-math -ffp-contract=off -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard"
    link="-static-libstdc++ -static-libgcc"
    ;;
*) echo "mode must be host or arm" >&2; exit 2 ;;
esac

$cc $cflags -shared -I"$here" -D__pow=pinned_pow -D__FP_FAST_FMA=1 \
    "$here/e_pow.c" "$here/e_pow_log_data.c" "$here/e_exp_data.c" \
    "$here/stubs.c" "$here/interpose.c" -lm -o "$out/libserver-pow3-fma.so"
$cxx -std=c++17 $cxxflags -I"$runtime" \
    "$here/runtime_server_moments.cpp" "$runtime/projection.cpp" \
    "$runtime/observations_cli.cpp" \
    -pthread -lm $link -o "$out/leo-server-moments"
sha256sum "$out/libserver-pow3-fma.so" "$out/leo-server-moments"

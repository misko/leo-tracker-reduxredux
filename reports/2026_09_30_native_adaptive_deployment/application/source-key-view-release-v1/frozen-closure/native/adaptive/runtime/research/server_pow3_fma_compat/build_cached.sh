#!/bin/sh
set -eu

mode=${1:-host}
out=${2:-/tmp/leo-server-pow3-cached-$mode}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime=$(CDPATH= cd -- "$here/../.." && pwd)
"$here/build.sh" "$mode" "$out"

case "$mode" in
host)
    cxx=${CXX:-g++}
    flags="-O2 -fno-fast-math -ffp-contract=off"
    link=""
    ;;
arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}
    flags="-O2 -fno-fast-math -ffp-contract=off -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard"
    link="-static-libstdc++ -static-libgcc"
    ;;
*) echo "mode must be host or arm" >&2; exit 2 ;;
esac

$cxx -std=c++17 $flags -I"$runtime" \
    "$here/runtime_server_moments_cached.cpp" "$runtime/projection.cpp" \
    "$runtime/observations_cli.cpp" -pthread -lm $link \
    -o "$out/leo-server-moments-cached"
sha256sum "$out/libserver-pow3-fma.so" "$out/leo-server-moments-cached"

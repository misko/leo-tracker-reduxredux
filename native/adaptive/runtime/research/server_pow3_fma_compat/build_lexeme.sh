#!/bin/sh
set -eu

mode=${1:-host}
out=${2:-/tmp/leo-server-python-float-$mode}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$out"

case "$mode" in
host)
    cxx=${CXX:-g++}
    flags="-O2"
    link=""
    ;;
arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cxx=${CXX:-$toolchain-g++}
    flags="-O2 -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard"
    link="-static-libstdc++ -static-libgcc"
    ;;
*) echo "mode must be host or arm" >&2; exit 2 ;;
esac

$cxx -std=c++17 $flags -Wall -Wextra -Wpedantic -Werror -I"$here" \
    "$here/python_float_repr_compat.cpp" \
    "$here/test_python_float_repr_compat.cpp" \
    $link -o "$out/test-python-float-repr"
$cxx -std=c++17 $flags -Wall -Wextra -Wpedantic -Werror -I"$here" \
    "$here/python_float_repr_compat.cpp" \
    "$here/test_python_float_repr_adversarial.cpp" \
    $link -o "$out/test-python-float-repr-adversarial"
$cxx -std=c++17 $flags -Wall -Wextra -Wpedantic -Werror -I"$here" \
    "$here/python_float_repr_compat.cpp" \
    "$here/build_server_graph_compat.cpp" \
    $link -o "$out/build-server-graph-compat"
sha256sum "$out/test-python-float-repr" "$out/test-python-float-repr-adversarial" \
    "$out/build-server-graph-compat"

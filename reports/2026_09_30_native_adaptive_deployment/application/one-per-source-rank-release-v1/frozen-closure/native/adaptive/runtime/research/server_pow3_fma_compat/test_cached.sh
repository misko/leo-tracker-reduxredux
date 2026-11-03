#!/bin/sh
set -eu

mode=${1:-host}
out=${2:-/tmp/leo-server-pow3-cached-$mode}
"$(dirname -- "$0")/test.sh" "$mode" "$out"
case "$mode" in
host) LD_PRELOAD="$out/libserver-pow3-fma.so" "$out/leo-server-moments-cached" < "$out/input.tsv" > "$out/actual-cached.tsv" ;;
arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    QEMU_LD_PREFIX=$($toolchain-gcc -print-sysroot) \
    LD_PRELOAD="$out/libserver-pow3-fma.so" \
        qemu-arm "$out/leo-server-moments-cached" < "$out/input.tsv" > "$out/actual-cached.tsv"
    ;;
*) echo "mode must be host or arm" >&2; exit 2 ;;
esac
cmp "$out/expected.tsv" "$out/actual-cached.tsv"
cmp "$out/actual.tsv" "$out/actual-cached.tsv"
echo "cached server pow3 compatibility: exact"

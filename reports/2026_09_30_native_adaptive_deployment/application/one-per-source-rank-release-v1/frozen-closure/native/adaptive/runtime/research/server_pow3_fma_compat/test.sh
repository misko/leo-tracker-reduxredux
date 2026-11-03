#!/bin/sh
set -eu

mode=${1:-host}
out=${2:-/tmp/leo-server-pow3-$mode}
root=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
fixture="$root/reports/2026_09_30_native_adaptive_deployment/tracking/projection-inputs.jsonl"
python3 "$(dirname -- "$0")/export_fixture.py" "$fixture" "$out/input.tsv" "$out/expected.tsv"
test "$(sha256sum "$out/input.tsv" | cut -d' ' -f1)" = 618fe88156d77b056548b08b49678aa3015ea050d005e26a34aa5ba7d80623de
test "$(sha256sum "$out/expected.tsv" | cut -d' ' -f1)" = 0a08994d2588c3f10f34dcb3daa4186434d39f59e601e32f51cb455a6aa44e38

case "$mode" in
host) LD_PRELOAD="$out/libserver-pow3-fma.so" "$out/leo-server-moments" < "$out/input.tsv" > "$out/actual.tsv" ;;
arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    QEMU_LD_PREFIX=$($toolchain-gcc -print-sysroot) \
    LD_PRELOAD="$out/libserver-pow3-fma.so" \
        qemu-arm "$out/leo-server-moments" < "$out/input.tsv" > "$out/actual.tsv"
    ;;
*) echo "mode must be host or arm" >&2; exit 2 ;;
esac
cmp "$out/expected.tsv" "$out/actual.tsv"
echo "server pow3 FMA compatibility: 24681 rows exact (11747 retained)"

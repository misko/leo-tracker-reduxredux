#!/bin/sh
set -eu

mode=${1:-host}
out=${2:-/tmp/leo-server-python-float-$mode}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../../../../.." && pwd)
fixture="$root/reports/2026_09_30_native_adaptive_deployment/tracking/projection-inputs.jsonl"
graph="$root/reports/2026_09_30_native_adaptive_deployment/tracking/graph-candidates.tsv"
values=${3:-$out/expected.tsv}
reference_python=${LEO_REFERENCE_PYTHON:-/var/tmp/leo-arm-realtime-publication/.venv/bin/python}

"$reference_python" "$here/export_fixture.py" "$fixture" "$out/input.tsv" "$out/expected.tsv"
"$reference_python" "$here/export_lexeme_fixture.py" "$fixture" "$out/lexemes.tsv" "$graph"
"$reference_python" "$here/export_python_repr_adversarial.py" "$out/adversarial.tsv"
test "$(sha256sum "$out/expected.tsv" | cut -d' ' -f1)" = \
    0a08994d2588c3f10f34dcb3daa4186434d39f59e601e32f51cb455a6aa44e38

case "$mode" in
host)
    "$out/test-python-float-repr" "$values" "$out/lexemes.tsv"
    "$out/test-python-float-repr-adversarial" "$out/adversarial.tsv"
    ;;
arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    QEMU_LD_PREFIX=$($toolchain-gcc -print-sysroot) \
        qemu-arm "$out/test-python-float-repr" "$values" "$out/lexemes.tsv"
    QEMU_LD_PREFIX=$($toolchain-gcc -print-sysroot) \
        qemu-arm "$out/test-python-float-repr-adversarial" "$out/adversarial.tsv"
    ;;
*) echo "mode must be host or arm" >&2; exit 2 ;;
esac

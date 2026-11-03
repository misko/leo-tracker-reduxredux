#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/runtime/server_compat"
test_dir="$root/tests/native_adaptive/runtime/server_compat"
tracking="$root/reports/2026_09_30_native_adaptive_deployment/tracking"
output="${2:-$source_dir/build/$mode}"
reference_python="${LEO_REFERENCE_PYTHON:-/var/tmp/leo-arm-realtime-publication/.venv/bin/python}"

profile_hash=$(sha256sum "$source_dir/profile.json" | awk '{print $1}')
test "$profile_hash" = '3847a5318ae80414d6cff060f04d305363e95bb6c86dbfbe9faca45f42b40cb5'
grep -Fq "sha256:$profile_hash" "$source_dir/server_compat.hpp"

"$reference_python" "$root/native/adaptive/runtime/research/server_pow3_fma_compat/export_fixture.py" \
    "$tracking/projection-inputs.jsonl" "$output/input.tsv" "$output/expected.tsv"
"$reference_python" "$root/native/adaptive/runtime/research/server_pow3_fma_compat/export_lexeme_fixture.py" \
    "$tracking/projection-inputs.jsonl" "$output/lexemes.tsv" "$tracking/graph-candidates.tsv"
"$reference_python" "$test_dir/export_python_repr_adversarial.py" "$output/adversarial.tsv"

defined=$(nm -D --defined-only "$output/libleo-server-pow3-fma.so" | awk '{print $3}')
test "$defined" = 'LEO_SERVER_POW3_1.0
leo_server_pow3_fma@@LEO_SERVER_POW3_1.0'
if nm -D "$output/libleo-server-pow3-fma.so" | grep -Eq '(^|[[:space:]])(__pow|pow)(@|$)'; then
    echo "pow DSO leaks a public/private pow symbol" >&2;exit 1
fi
if nm -D --defined-only "$output/libleoservercompat.so" |
    grep -Eq '(^|[[:space:]])(__pow|pow|__pow_log_data|__exp_data)(@|$)'; then
    echo "compatibility DSO leaks a pow/glibc-private symbol" >&2;exit 1
fi
if nm -u "$output/server_compat.o" | awk '{print $2}' | grep -Eq '^(__)?pow(@|$)'; then
    echo "support derivation references an unnamed system pow symbol" >&2;exit 1
fi
nm -u "$output/server_compat.o" | awk '{print $2}' | grep -qx 'leo_server_pow3_fma'

case "$mode" in
 host|sanitize)
    "$output/test-server-compat"
    "$output/test-ds9-server-compat" "$output/input.tsv" "$output/expected.tsv" "$output/lexemes.tsv"
    "$output/test-python-float-repr-adversarial" "$output/adversarial.tsv"
    ;;
 arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    prefix="$($toolchain-gcc -print-sysroot)"
    for test in test-server-compat test-ds9-server-compat test-python-float-repr-adversarial; do
        args=()
        if [[ "$test" == test-ds9-server-compat ]]; then
            args=("$output/input.tsv" "$output/expected.tsv" "$output/lexemes.tsv")
        elif [[ "$test" == test-python-float-repr-adversarial ]]; then
            args=("$output/adversarial.tsv")
        fi
        QEMU_LD_PREFIX="$prefix" LD_LIBRARY_PATH="$output" qemu-arm "$output/$test" "${args[@]}"
    done
    ;;
 *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2;exit 2;;
esac

echo "server compatibility module: $mode tests passed"

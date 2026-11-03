#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
output=${2:?usage: test_session_compat.sh MODE OUTPUT}
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
tracking="$root/reports/2026_09_30_native_adaptive_deployment/tracking"
research="$root/native/adaptive/runtime/research/server_pow3_fma_compat"
reference_python=${LEO_REFERENCE_PYTHON:-/var/tmp/leo-arm-realtime-publication/.venv/bin/python}

"$reference_python" "$research/export_fixture.py" "$tracking/projection-inputs.jsonl" \
  "$output/input.tsv" "$output/expected.tsv"

case "$mode" in
  host|sanitize)
    LD_LIBRARY_PATH="$output" "$output/test-ds9-session-compat" \
      "$output/input.tsv" "$output/session.tracks.tsv" | tee "$output/session-summary.json"
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    sysroot=$($toolchain-gcc -print-sysroot)
    QEMU_LD_PREFIX="$sysroot" LD_LIBRARY_PATH="$output" qemu-arm \
      "$output/test-ds9-session-compat" "$output/input.tsv" \
      "$output/session.tracks.tsv" | tee "$output/session-summary.json"
    ;;
  *) echo "usage: $0 host|sanitize|arm OUTPUT" >&2; exit 2;;
esac

"$reference_python" "$research/compare_recomputed_partitions.py" \
  "$tracking/oracle-tracks.json" "$tracking/graph-candidates.tsv" \
  "$output/session.tracks.tsv" | tee "$output/partition-comparison.json"

echo "server compatibility Session integration: $mode pass"

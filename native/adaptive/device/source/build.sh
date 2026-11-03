#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/device/source"
test_dir="$root/tests/native_adaptive/device/source"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"

case "$mode" in
  host)
    cc="${CC:-gcc}"; ar="${AR:-ar}"
    flags=(-O2 -fPIC)
    ;;
  sanitize)
    cc="${CC:-gcc}"; ar="${AR:-ar}"
    flags=(-O1 -g -fno-omit-frame-pointer -fPIC -fsanitize=address,undefined)
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cc="${CC:-$toolchain-gcc}"; ar="${AR:-$toolchain-ar}"
    flags=(-O2 -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    ;;
  *)
    echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2
    exit 2
    ;;
esac

warnings=(-Wall -Wextra -Werror -Wpedantic)
"$cc" -std=c11 "${flags[@]}" "${warnings[@]}" -I "$source_dir" \
  -c "$source_dir/source_port.c" -o "$output/source_port.o"
"$ar" rcs "$output/libleosourceport.a" "$output/source_port.o"
"$cc" -std=c11 "${flags[@]}" "${warnings[@]}" -pthread -I "$source_dir" \
  "$test_dir/test_source_port.c" "$output/libleosourceport.a" \
  -o "$output/test-source-port"

if [[ "$mode" != arm ]]; then
  "$output/test-source-port"
fi
echo "$output"

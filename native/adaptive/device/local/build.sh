#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/device/local"
port_dir="$root/native/adaptive/device/source"
test_dir="$root/tests/native_adaptive/device/local"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"

case "$mode" in
  host)
    cc="${CC:-gcc}"
    ar="${AR:-ar}"
    flags=(-std=c11 -D_GNU_SOURCE -O2 -fPIC)
    iio_link=(-Wl,-l:libiio.so.0)
    ;;
  sanitize)
    cc="${CC:-gcc}"
    ar="${AR:-ar}"
    flags=(-std=c11 -D_GNU_SOURCE -O1 -g -fno-omit-frame-pointer -fPIC
      -fsanitize=address,undefined)
    iio_link=(-Wl,-l:libiio.so.0)
    ;;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cc="${CC:-$toolchain-gcc}"
    ar="${AR:-$toolchain-ar}"
    flags=(-std=c11 -D_GNU_SOURCE -O2 -fPIC -mcpu=cortex-a9 -mfpu=neon
      -mfloat-abi=hard)
    iio_link=(-liio -static-libgcc)
    ;;
  *)
    echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2
    exit 2
    ;;
esac

warnings=(-Wall -Wextra -Werror -Wpedantic)
includes=(-I "$source_dir" -I "$source_dir/vendor")
includes+=(-I "$port_dir")
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  -c "$port_dir/source_port.c" -o "$output/source_port.o"
"$ar" rcs "$output/libleosourceport.a" "$output/source_port.o"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  -c "$source_dir/local_source_port.c" -o "$output/local_source_port.o"
"$ar" rcs "$output/libleolocalsourceport.a" "$output/local_source_port.o"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  -c "$source_dir/local_source.c" -o "$output/local_source.o"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  -c "$source_dir/local_iio_provider.c" -o "$output/local_iio_provider.o"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  -c "$source_dir/local_radio_prepare.c" -o "$output/local_radio_prepare.o"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  -c "$source_dir/local_radio_prepare_iio.c" -o "$output/local_radio_prepare_iio.o"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  -c "$source_dir/vendor/spf-scan-radio.c" -o "$output/spf-scan-radio.o"
"$ar" rcs "$output/libleolocal.a" "$output/local_source.o" \
  "$output/local_iio_provider.o" "$output/local_radio_prepare.o" \
  "$output/local_radio_prepare_iio.o" "$output/spf-scan-radio.o"
"$cc" -shared "${flags[@]}" "$output/local_source.o" \
  "$output/local_iio_provider.o" "$output/local_radio_prepare.o" \
  "$output/local_radio_prepare_iio.o" "$output/spf-scan-radio.o" \
  "${iio_link[@]}" -o "$output/libleolocal.so"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  "$source_dir/local_capture_cli.c" "$output/libleolocal.a" \
  "${iio_link[@]}" -o "$output/leo-local-capture"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  "$source_dir/local_radio_prepare_cli.c" "$output/libleolocal.a" \
  "${iio_link[@]}" -o "$output/leo-local-radio-prepare"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  "$test_dir/test_local_source.c" "$output/libleolocalsourceport.a" \
  "$output/libleosourceport.a" "$output/libleolocal.a" \
  -o "$output/test-local-source"
"$cc" "${flags[@]}" "${warnings[@]}" "${includes[@]}" \
  "$test_dir/test_local_radio_prepare.c" "$output/local_radio_prepare.o" \
  -o "$output/test-local-radio-prepare"

if [[ "$mode" != arm ]]; then
  "$output/test-local-source"
  "$output/test-local-radio-prepare"
  set +e
  "$output/leo-local-capture" >/dev/null 2>&1
  cli_status=$?
  set -e
  test "$cli_status" = 2
  set +e
  "$output/leo-local-radio-prepare" >/dev/null 2>&1
  cli_status=$?
  set -e
  test "$cli_status" = 2
fi
echo "$output"

#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
source_dir="$root/native/adaptive/scanner"
output=${2:-"$source_dir/build/$mode"}
mkdir -p "$output"

case "$mode" in
  host)
    cc=${CC:-gcc}; cxx=${CXX:-g++}; ar=${AR:-ar}
    common=(-O2 -g -fPIC -fno-fast-math -ffp-contract=off)
    cxx_link=()
    iio_link=(-Wl,-l:libiio.so.0)
    ;;
  sanitize)
    cc=${CC:-gcc}; cxx=${CXX:-g++}; ar=${AR:-ar}
    common=(-O1 -g -fPIC -fno-fast-math -ffp-contract=off -fno-omit-frame-pointer -fsanitize=address,undefined)
    cxx_link=(-fsanitize=address,undefined)
    iio_link=(-Wl,-l:libiio.so.0)
    ;;
  tsan)
    cc=${CC:-gcc}; cxx=${CXX:-g++}; ar=${AR:-ar}
    common=(-O1 -g -fPIC -fno-fast-math -ffp-contract=off -fno-omit-frame-pointer -fsanitize=thread)
    cxx_link=(-fsanitize=thread)
    iio_link=(-Wl,-l:libiio.so.0)
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    cc=${CC:-"$toolchain-gcc"}; cxx=${CXX:-"$toolchain-g++"}; ar=${AR:-"$toolchain-ar"}
    common=(-O2 -g -fPIC -fno-fast-math -ffp-contract=off -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    cxx_link=(-static-libstdc++ -static-libgcc)
    iio_link=(-liio)
    ;;
  *)
    echo "usage: $0 [host|sanitize|tsan|arm] [output-directory]" >&2
    exit 2
    ;;
esac

warnings=(-Wall -Wextra -Werror -Wpedantic)
scanner_include=(-I"$source_dir" -I"$root/native/adaptive")
local_include=(-I"$root/native/adaptive/device/local" -I"$root/native/adaptive/device/local/vendor")
source_include=(-I"$root/native/adaptive/device/source")

"$cc" -std=c11 -D_GNU_SOURCE "${common[@]}" "${warnings[@]}" "${local_include[@]}" \
  -c "$root/native/adaptive/device/local/local_source.c" -o "$output/local_source.o"
"$cc" -std=c11 "${common[@]}" "${warnings[@]}" "${source_include[@]}" \
  -c "$root/native/adaptive/device/source/source_port.c" -o "$output/source_port.o"
"$cc" -std=c11 "${common[@]}" "${warnings[@]}" "${source_include[@]}" \
  "${local_include[@]}" -c "$root/native/adaptive/device/local/local_source_port.c" \
  -o "$output/local_source_port.o"
"$cc" -std=c11 -D_GNU_SOURCE "${common[@]}" "${warnings[@]}" "${local_include[@]}" \
  -c "$root/native/adaptive/device/local/local_radio_prepare.c" -o "$output/local_radio_prepare.o"
"$cc" -std=c11 -D_GNU_SOURCE "${common[@]}" "${warnings[@]}" "${local_include[@]}" \
  -c "$root/native/adaptive/device/local/vendor/spf-scan-radio.c" -o "$output/spf-scan-radio.o"
"$cc" -std=c11 "${common[@]}" "${warnings[@]}" -I"$root/native/adaptive/policy" \
  -c "$root/native/adaptive/policy/spf-scan-policy.c" -o "$output/spf-scan-policy.o"
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
  -c "$root/native/adaptive/runtime/runtime.cpp" -o "$output/runtime.o"
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
  -c "$source_dir/scanner.cpp" -o "$output/scanner.o"

objects=("$output/scanner.o" "$output/runtime.o" "$output/spf-scan-policy.o"
  "$output/source_port.o" "$output/local_source_port.o" "$output/local_source.o"
  "$output/local_radio_prepare.o" "$output/spf-scan-radio.o")
"$ar" rcs "$output/libleoscanner.a" "${objects[@]}"
"$cxx" -shared "${common[@]}" "${cxx_link[@]}" "${objects[@]}" -lpthread -lm \
  -o "$output/libleoscanner.so"
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
  "${local_include[@]}" "$root/tests/native_adaptive/scanner/test_scanner.cpp" \
  "$output/libleoscanner.a" "${cxx_link[@]}" -lpthread -lm -o "$output/test-scanner"
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
  "$root/tests/native_adaptive/scanner/test_scanner_single_source.cpp" \
  "$output/libleoscanner.a" "${cxx_link[@]}" -lpthread -lm \
  -o "$output/test-scanner-single-source"
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
  "$root/tests/native_adaptive/scanner/test_scanner_profile.cpp" \
  "$output/libleoscanner.a" "${cxx_link[@]}" -lpthread -lm \
  -o "$output/test-scanner-profile"
"$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
  "$root/tests/native_adaptive/scanner/test_scanner_recorded_plan.cpp" \
  "$output/libleoscanner.a" "${cxx_link[@]}" -lpthread -lm \
  -o "$output/test-scanner-recorded-plan"

if [[ "$mode" != arm ]]; then
  "$output/test-scanner"
  "$output/test-scanner-single-source"
  "$output/test-scanner-profile"
  "$output/test-scanner-recorded-plan"
fi

if [[ ${LEO_REAL_DS9_TEST:-0} == 1 ]]; then
  real_detector_static=${LEO_DETECTOR_STATIC:?set LEO_DETECTOR_STATIC for real DS9 test}
  real_fftw_float=${LEO_FFTW_FLOAT_STATIC:?set LEO_FFTW_FLOAT_STATIC for real DS9 test}
  real_fftw_double=${LEO_FFTW_DOUBLE:?set LEO_FFTW_DOUBLE for real DS9 test}
  "$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
    "$root/tests/native_adaptive/scanner/test_scanner_real_multicontext.cpp" \
    "$output/libleoscanner.a" "$real_detector_static" "$real_fftw_float" \
    "$real_fftw_double" "${cxx_link[@]}" -lpthread -lm \
    -o "$output/test-scanner-real-multicontext"
  "$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
    "$root/tests/native_adaptive/scanner/test_scanner_single_ds9.cpp" \
    "$output/libleoscanner.a" "$real_detector_static" "$real_fftw_float" \
    "$real_fftw_double" "${cxx_link[@]}" -lpthread -lm \
    -o "$output/test-scanner-single-ds9"
  if [[ "$mode" != arm ]]; then
    fixture_root="$root/reports/2026_09_30_native_adaptive_deployment/ds9/portable80/fixtures"
    "$output/test-scanner-real-multicontext" \
      "$fixture_root/lower-exact.c128" "$fixture_root/lower-control.c128" \
      "$fixture_root/607957d70258c2ae53439f9b149821eea15ee95d1863ee5bb845412a2cc3fdc8.ci16" \
      "$fixture_root/d302949a8ce74cc8ef27d24acffe89266847a34c9795e895d086c7fd703443fd.ci16"
    "$output/test-scanner-single-ds9" \
      "$fixture_root/lower-exact.c128" "$fixture_root/lower-control.c128" \
      "$fixture_root/607957d70258c2ae53439f9b149821eea15ee95d1863ee5bb845412a2cc3fdc8.ci16"
  fi
fi

if [[ ${LEO_SKIP_SCANNER_CLI:-0} != 1 ]]; then
  detector_shared=${LEO_DETECTOR_SHARED:-}
  detector_static=${LEO_DETECTOR_STATIC:-}
  if [[ -n "$detector_shared" ]]; then
    test -f "$detector_shared"
    cp "$detector_shared" "$output/libleo-adaptive-detector.so"
    ln -sfn libleo-adaptive-detector.so "$output/libleo-adaptive-detector.so.1"
    detector_link=(-L"$output" -Wl,-l:libleo-adaptive-detector.so.1 '-Wl,-rpath,$ORIGIN')
  else
    detector_static=${detector_static:?set LEO_DETECTOR_SHARED or LEO_DETECTOR_STATIC}
    detector_link=("$detector_static")
  fi
  fftw_float=${LEO_FFTW_FLOAT_STATIC:?set LEO_FFTW_FLOAT_STATIC to libfftw3f.a}
  fftw_double=${LEO_FFTW_DOUBLE:?set LEO_FFTW_DOUBLE to target libfftw3.so}
  test -f "$fftw_float" && test -f "$fftw_double"
  "$cc" -std=c11 -D_GNU_SOURCE "${common[@]}" "${warnings[@]}" "${local_include[@]}" \
    -c "$root/native/adaptive/device/local/local_iio_provider.c" -o "$output/local_iio_provider.o"
  "$cc" -std=c11 -D_GNU_SOURCE "${common[@]}" "${warnings[@]}" "${local_include[@]}" \
    -c "$root/native/adaptive/device/local/local_radio_prepare_iio.c" \
    -o "$output/local_radio_prepare_iio.o"
  "$cxx" -std=c++17 "${common[@]}" "${warnings[@]}" "${scanner_include[@]}" \
    "${local_include[@]}" \
    -c "$source_dir/scanner_cli.cpp" -o "$output/scanner_cli.o"
  "$cxx" "${common[@]}" "$output/scanner_cli.o" "$output/libleoscanner.a" \
    "$output/local_iio_provider.o" "$output/local_radio_prepare_iio.o" \
    "${detector_link[@]}" "$fftw_float" "$fftw_double" \
    "${iio_link[@]}" "${cxx_link[@]}" -lpthread -lm -o "$output/leo-adaptive-scanner"
  if [[ "$mode" != arm ]]; then
    "$output/leo-adaptive-scanner"
    set +e
    "$output/leo-adaptive-scanner" --capture --duration-ms 1000 \
      --maximum-visits 1 --active-dwell-ms 120 \
      --exact-template /dev/null --control-template /dev/null \
      --target 0 2400000000 --block-ms 20 >/dev/null 2>&1
    valid_parse_status=$?
    "$output/leo-adaptive-scanner" --capture --duration-ms 1000 \
      --maximum-visits 1 --active-dwell-ms 120 \
      --exact-template /dev/null --control-template /dev/null \
      --target 0 2400000000 --block-ms 30 >/dev/null 2>&1
    invalid_parse_status=$?
    "$output/leo-adaptive-scanner" --capture --duration-ms 1000 \
      --maximum-visits 1 --active-dwell-ms 120 \
      --exact-template /dev/null --control-template /dev/null \
      --target 0 2400000000 >/dev/null 2>&1
    missing_parse_status=$?
    "$output/leo-adaptive-scanner" --capture --duration-ms 1000 \
      --maximum-visits 1 --active-dwell-ms 120 --block-ms 20 \
      --exact-template /dev/null --control-template /dev/null \
      --target 0 2400000000 --block-ms 20 >/dev/null 2>&1
    duplicate_parse_status=$?
    set -e
    if [[ $valid_parse_status != 3 || $invalid_parse_status != 2 || \
          $missing_parse_status != 2 || $duplicate_parse_status != 2 ]]; then
      echo "scanner CLI parser regression: valid=$valid_parse_status invalid=$invalid_parse_status missing=$missing_parse_status duplicate=$duplicate_parse_status" >&2
      exit 1
    fi
  fi
fi
echo "$output"

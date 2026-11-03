#!/usr/bin/env bash
set -euo pipefail

mode="${1:-host}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
source_dir="$root/native/adaptive/runtime/server_compat"
runtime_dir="$root/native/adaptive/runtime"
test_dir="$root/tests/native_adaptive/runtime/server_compat"
output="${2:-$source_dir/build/$mode}"
mkdir -p "$output"

case "$mode" in
 host)
    cc="${CC:-gcc}";cxx="${CXX:-g++}";ar="${AR:-ar}"
    cflags=(-O2 -ffp-contract=off -fPIC -fvisibility=hidden)
    cxxflags=(-std=c++17 -O2 -fno-fast-math -ffp-contract=off -fPIC)
    link=()
    ;;
 sanitize)
    cc="${CC:-gcc}";cxx="${CXX:-g++}";ar="${AR:-ar}"
    cflags=(-O1 -g -ffp-contract=off -fPIC -fvisibility=hidden -fsanitize=address,undefined)
    cxxflags=(-std=c++17 -O1 -g -fno-fast-math -ffp-contract=off -fPIC -fsanitize=address,undefined)
    link=()
    ;;
 arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    cc="${CC:-$toolchain-gcc}";cxx="${CXX:-$toolchain-g++}";ar="${AR:-$toolchain-ar}"
    cflags=(-O2 -ffp-contract=off -fPIC -fvisibility=hidden -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    cxxflags=(-std=c++17 -O2 -fno-fast-math -ffp-contract=off -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
 *) echo "usage: $0 [host|sanitize|arm] [output-directory]" >&2;exit 2;;
esac

glibc="$source_dir/glibc"
"$cc" "${cflags[@]}" -I"$glibc" -D__pow=leo_server_pow_core -D__FP_FAST_FMA=1 \
    -c "$glibc/e_pow.c" -o "$output/e_pow.o"
"$cc" "${cflags[@]}" -I"$glibc" -c "$glibc/e_pow_log_data.c" -o "$output/e_pow_log_data.o"
"$cc" "${cflags[@]}" -I"$glibc" -c "$glibc/e_exp_data.c" -o "$output/e_exp_data.o"
"$cc" "${cflags[@]}" -I"$glibc" -c "$glibc/stubs.c" -o "$output/stubs.o"
"$cc" "${cflags[@]}" -I"$source_dir" -c "$source_dir/pow3_entry.c" -o "$output/pow3_entry.o"
"$cc" -shared "${cflags[@]}" "$output/e_pow.o" "$output/e_pow_log_data.o" \
    "$output/e_exp_data.o" "$output/stubs.o" "$output/pow3_entry.o" -lm \
    -Wl,--version-script="$source_dir/pow3.map" -Wl,-soname,libleo-server-pow3-fma.so \
    -o "$output/libleo-server-pow3-fma.so"

include=(-I"$source_dir" -I"$runtime_dir" -Wall -Wextra -Wpedantic -Werror)
"$cxx" "${cxxflags[@]}" "${include[@]}" -c "$source_dir/python_float_repr.cpp" \
    -o "$output/python_float_repr.o"
"$cxx" "${cxxflags[@]}" "${include[@]}" -c "$source_dir/server_compat.cpp" \
    -o "$output/server_compat.o"
"$ar" rcs "$output/libleoservercompat.a" "$output/python_float_repr.o" "$output/server_compat.o"
"$cxx" -shared "${cxxflags[@]}" "$output/python_float_repr.o" "$output/server_compat.o" \
    -L"$output" -lleo-server-pow3-fma -Wl,-rpath,'$ORIGIN' -lm \
    -o "$output/libleoservercompat.so"

"$cxx" "${cxxflags[@]}" "${include[@]}" "$test_dir/test_server_compat.cpp" \
    "$runtime_dir/runtime.cpp" "$output/libleoservercompat.a" -L"$output" \
    -lleo-server-pow3-fma -Wl,-rpath,'$ORIGIN' -pthread -lm "${link[@]}" \
    -o "$output/test-server-compat"
"$cxx" "${cxxflags[@]}" "${include[@]}" "$test_dir/test_ds9_server_compat.cpp" \
    "$runtime_dir/runtime.cpp" "$output/libleoservercompat.a" -L"$output" \
    -lleo-server-pow3-fma -Wl,-rpath,'$ORIGIN' -pthread -lm "${link[@]}" \
    -o "$output/test-ds9-server-compat"
"$cxx" "${cxxflags[@]}" "${include[@]}" \
    "$test_dir/test_python_float_repr_adversarial.cpp" "$output/python_float_repr.o" \
    -lm "${link[@]}" -o "$output/test-python-float-repr-adversarial"

sha256sum "$output/libleo-server-pow3-fma.so" "$output/libleoservercompat.so" \
    "$output/test-server-compat" "$output/test-ds9-server-compat" \
    "$output/test-python-float-repr-adversarial"

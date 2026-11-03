#!/usr/bin/env bash
set -euo pipefail

mode=${1:-host}
output=${2:?usage: build_session_compat.sh MODE OUTPUT ONLINE_LIBRARY SERVER_COMPAT_LIBRARY}
online=${3:?prebuilt online library directory required}
compat=${4:?prebuilt server compatibility library directory required}
test_dir=$(cd -- "$(dirname -- "$0")" && pwd)
root=$(cd -- "$test_dir/../../.." && pwd)
application="$root/native/adaptive/application"
mkdir -p "$output"

case "$mode" in
  host)
    compiler=${CXX:-g++}
    flags=(-std=c++17 -O2 -g -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off -pthread)
    link=()
    ;;
  sanitize)
    compiler=${CXX:-g++}
    flags=(-std=c++17 -O1 -g -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off
      -pthread -fsanitize=address,undefined -fno-omit-frame-pointer)
    link=()
    ;;
  arm)
    toolchain=${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}
    compiler=${CXX:-$toolchain-g++}
    flags=(-std=c++17 -O2 -g -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off
      -pthread -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-static-libstdc++ -static-libgcc)
    ;;
  *) echo "usage: $0 host|sanitize|arm OUTPUT ONLINE_LIBRARY SERVER_COMPAT_LIBRARY" >&2; exit 2;;
esac

"$compiler" "${flags[@]}" -I"$application" -I"$root/native/adaptive/runtime" \
  -I"$root/native/adaptive/runtime/server_compat" -I"$root/native/adaptive/tracking" \
  -I"$root/native/adaptive/pipeline" -I"$root/native/adaptive/location" \
  "$test_dir/test_ds9_session_compat.cpp" "$application/session.cpp" \
  "$root/native/adaptive/ingest/ingest.cpp" "$root/native/adaptive/timing/timebase.cpp" \
  "$root/native/adaptive/runtime/runtime.cpp" "$root/native/adaptive/runtime/projection.cpp" \
  "$compat/libleoservercompat.a" "$online/libleoonline.a" -L"$compat" \
  -lleo-server-pow3-fma -Wl,-rpath,'$ORIGIN' -lm "${link[@]}" \
  -o "$output/test-ds9-session-compat"

cp "$compat/libleo-server-pow3-fma.so" "$output/"
sha256sum "$output/test-ds9-session-compat" "$output/libleo-server-pow3-fma.so"

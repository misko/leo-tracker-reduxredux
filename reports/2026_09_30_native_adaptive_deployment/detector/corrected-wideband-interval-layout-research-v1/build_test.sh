#!/bin/sh
set -eu

cc=${CC:-gcc}
mode=${1:-normal}
out=${2:-/var/tmp/leo-interval-bounds-layout-test}
flags="-std=c11 -O3 -Wall -Wextra -Werror"
if [ "$mode" = sanitize ]; then
    flags="$flags -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer"
elif [ "$mode" != normal ]; then
    echo "usage: $0 [normal|sanitize] [output]" >&2
    exit 2
fi
$cc $flags test_interval_bounds_layout.c -o "$out"
"$out"

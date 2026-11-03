#!/bin/sh
set -eu

cc=${CC:-gcc}
mode=${1:-normal}
out=${2:-/var/tmp/leo-correlate-eight-test}
flags="-std=c11 -O3 -Wall -Wextra -Werror -fno-fast-math ${CFLAGS:-}"
if [ "$mode" = sanitize ]; then
    flags="$flags -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer"
elif [ "$mode" != normal ]; then
    echo "usage: $0 [normal|sanitize] [output]" >&2
    exit 2
fi
$cc $flags test_correlate_eight_fp32.c -o "$out"
"$out"

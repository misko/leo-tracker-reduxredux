#!/bin/sh
set -eu

cc=${CC:-gcc}
mode=${1:-normal}
out=${2:-/var/tmp/leo-next-up-test}
flags="-std=c11 -O3 -Wall -Wextra -Werror -frounding-math -fno-fast-math -fno-builtin-nextafter"
if [ "$mode" = sanitize ]; then
    flags="$flags -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer"
elif [ "$mode" != normal ]; then
    echo "usage: $0 [normal|sanitize] [output]" >&2
    exit 2
fi
$cc $flags test_next_up_positive.c -lm -o "$out"
"$out"

#!/bin/sh
exec /usr/bin/gcc -fsanitize=address,undefined -fno-sanitize-recover=all "$@"

#!/bin/sh
exec /usr/bin/gcc -fsanitize=address,undefined -fno-omit-frame-pointer "$@"

# Corresponding source for optional support-profile tests

`corresponding-source.tar.gz` accompanies the separately replaceable
`libleo-server-pow3-fma.so` used by CPU-only compatibility tests. It contains
the exact module source, original notices, LGPL-2.1-or-later license, build
commands, portable runtime dependencies and component test source. The regular
live application does not link this DSO.

Extract on a development host, then run:

```sh
tar -xzf corresponding-source.tar.gz
LEO_ARM_TOOLCHAIN=/path/to/arm-linux-gnueabihf \
  bash native/adaptive/runtime/server_compat/build.sh arm /path/to/output
```

The build emits individual object files and the named DSO. A modified DSO can
replace the file beside the compatibility test executable without relinking
that executable; run with `LD_LIBRARY_PATH` pointing to that directory. It
does not interpose the system `pow` symbol. See the included module README
and `native/adaptive/runtime/server_compat/glibc/COPYING.LIB`.

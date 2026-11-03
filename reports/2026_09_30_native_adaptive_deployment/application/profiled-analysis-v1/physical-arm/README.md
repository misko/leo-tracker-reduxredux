# Physical profiled Analysis replay

`paced.log` is the original-speed PLUTO+ run. `comparison.json` checks its
scientific fields against the host background run. See the parent physical
receipt for fixture hashes, timing scope and remaining qualification gaps.

The companion test library remains replaceable. Extract
`corresponding-source.tar.gz` on a development host and run its included
`native/adaptive/runtime/server_compat/build.sh arm OUTPUT_DIRECTORY` with
`LEO_ARM_TOOLCHAIN` set to the cross-toolchain prefix. The source includes the
original LGPL notices and build/relink commands. A rebuilt
`libleo-server-pow3-fma.so` may replace the copy beside the test executable;
run with `LD_LIBRARY_PATH=.`. `COPYING.LIB` is included.

No radio capture was performed. The first invocation failed fixture-path
validation before playback; that terminal log is retained separately.

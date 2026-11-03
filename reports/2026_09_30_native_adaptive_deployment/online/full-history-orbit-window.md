# Full-history orbit cache feasibility

The physical PLUTO+ test used all 11,129 DS9 catalogue entries and a two-bank
96-knot orbit arena with ten-second spacing. Peak process RSS was 114,664 KiB.
Two successive builds took 9.920 and 9.899 seconds. Both generations preserved
catalogue identities and passed interpolation coverage checks at the first,
middle and last time for every satellite (66,774 checks total).

The 950-second span leaves approximately 320 seconds of reuse after allowing
600 seconds of observation history, tau offsets and interpolation guards.
Propagation into the future uses the local TLE, not future RF observations.
The cache is shared immutably with the scorer and rebuilt only when coverage
requires it. Rebuilding on every publication would discard this advantage.

This test establishes allocation and coverage feasibility, not a global
interpolation error bound or continuous application throughput. The earlier
ten-second-knot DS9 location experiment remains separate numerical evidence.
The full-history paced application must still test expiry, generation changes,
tracking cost, search freshness and contention with acquisition.

The benchmark source is
`tests/native_adaptive/location/bench_orbit_window.cpp`. The shared parser in
`native/adaptive/location/tle_id.hpp` handles actual decimal and Alpha-5 IDs;
array positions are not satellite identities. Component tests run through
`native/adaptive/location/build.sh`.

Example standalone rebuild using the component library:

```sh
native/adaptive/location/build.sh host /tmp/leo-location-orbit-host
g++ -std=c++17 -O3 -fno-fast-math -ffp-contract=off \
  -I native/adaptive/location \
  tests/native_adaptive/location/bench_orbit_window.cpp \
  /tmp/leo-location-orbit-host/libleolocation.a -pthread -lm \
  -o /tmp/leo-bench-orbit-window
/tmp/leo-bench-orbit-window \
  reports/2026_09_30_arm_location_prototype/local/tles.txt \
  1790557997299661326
```

For ARM, build the location library with `arm` and use the same ARM toolchain
with `-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard -static-libstdc++ -static-libgcc`.
The saved [receipt](full-history-orbit-window.json) binds the measured binary,
source, catalogue and device path. The device invocation was bounded by
`measure-run 120`; it opened no radio device.

# Online scoring execution qualification

The online coordinator now accepts an optional borrowed synchronous scoring
dispatcher. It splits the immutable catalogue into fixed contiguous satellite
ranges, gives each range a private score context and scratch array, and reduces
the results in ascending range order. One worker with no callback remains the
original serial path. Invalid worker configurations and thrown, duplicate, or
missing callbacks fail without submitting a point or changing the incumbent.

The component test compares complete one-, two-, and four-worker searches field
for field. Host, ASAN/UBSAN, ThreadSanitizer, ARM cross-build, qemu ARM, and two
physical ARM unit runs passed. ThreadSanitizer used a full-source build and ran
both the lifecycle unit and the DS9 replay; the release builds reused the
qualified optimized tracking, pipeline, orbit, stencil scorer, search, and SGP4
members recorded in `receipt.json`.

Reproduce the builds with:

```sh
LEO_ONLINE_BASE_LIBRARY=/tmp/leo-online-dispatch-fix-host/libleoonline.a \
  native/adaptive/online/build.sh host /tmp/leo-online-scoreexec-final2-host

LEO_ONLINE_BASE_LIBRARY=/tmp/leo-online-dispatch-fix-sanitize/libleoonline.a \
  native/adaptive/online/build.sh sanitize /tmp/leo-online-scoreexec-final2-sanitize

mkdir -p /var/tmp/leo-online-scoreexec-compiler-tmp
TMPDIR=/var/tmp/leo-online-scoreexec-compiler-tmp \
  native/adaptive/online/build.sh thread /tmp/leo-online-scoreexec-final2-thread

TMPDIR=/var/tmp/leo-online-scoreexec-compiler-tmp \
  LEO_ONLINE_BASE_LIBRARY=/tmp/leo-online-dispatch-fix-arm/libleoonline.a \
  native/adaptive/online/build.sh arm /tmp/leo-online-scoreexec-final2-arm

qemu-arm \
  -L /home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot \
  /tmp/leo-online-scoreexec-final2-arm/test_online \
  reports/2026_09_30_arm_location_prototype/local/tles.txt
```

The earlier and final2 ARM archives have different container hashes, but all
seven production object members are byte-identical. Final2 adds only the
missing-callback test; the replay executable is also byte-identical.

The deployed saved-event application replay confirms exact science between one
and two analysis workers over 11,747 observations, 64 tracks, and 11,129 TLEs,
with no queue drops. Its post-producer tail fell from 52.898 to 34.382 seconds.
That two-worker run reserves no detector lane and remains well outside the
five-second continuous gate. See
[`application/scoring-workers-v1/deployment.json`](../../application/scoring-workers-v1/deployment.json)
for the application evidence.

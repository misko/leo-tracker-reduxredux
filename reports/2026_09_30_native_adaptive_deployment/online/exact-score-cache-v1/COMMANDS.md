# Reproduction commands

Run from the repository root. The archived `source-v9/` tree contains the exact
production and test sources used by the final builds; it excludes build outputs
and Python caches.

```sh
native/adaptive/online/build.sh host /var/tmp/leo-online-exact-cache-host-v9
TMPDIR=/var/tmp/leo-cache-v9-compiler-tmp \
  native/adaptive/online/build.sh sanitize \
  /var/tmp/leo-online-exact-cache-sanitize-v9
native/adaptive/online/build.sh arm /var/tmp/leo-online-exact-cache-arm-v9
```

The build script runs the component unit and default DS9 replay in host and
sanitizer modes. The full host trace used:

```sh
/usr/bin/time -f 'wall=%e cpu_user=%U cpu_sys=%S rss_kib=%M exit=%x' \
  /var/tmp/leo-online-exact-cache-host-v7/leo-online-replay \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  reports/2026_09_30_native_adaptive_deployment/tracking/graph-candidates.tsv \
  reports/2026_09_30_arm_location_prototype/local/tles.txt \
  --cache400
```

`artifacts/host-v7/leo-online-replay` is the exact executable that produced the
retained full trace. The current v9 source retains the same full-trace mode and
changes diagnostic coordinator lifetimes in the shared full/bounded harness.
The build script's default DS9 regression uses the separate
`ds9/complete-scan-e1` fixtures; those are not the cache-trace input authority.
Both fixture sets are recorded in `INPUTS.sha256`.

The final bounded host command used the v9 executable with
`--cache-points 1`. The physical command used the same arguments and the ARM v9
executable; root-owned deployment wrappers supplied the 600-second watchdog and
measurement envelope recorded in `physical-receipt.json`.

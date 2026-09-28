# Build status

The direct build and its original-refinement control were built from the frozen
`/var/tmp/leo-host-verify-fusion-v1` source receipt.

| Receipt directory | Target | Unit result |
| --- | --- | --- |
| `/var/tmp/leo-host-direct-glrt-v1` | host | passed |
| `/var/tmp/leo-host-direct-glrt-asan-v1` | host ASAN/UBSAN | passed |
| `/var/tmp/leo-arm-direct-glrt-v1` | ARM cross build | compiled; not executed here |

The host and sanitizer units compile `LEO_FULL_DIRECT_GLRT=1` and cover 2.5,
5, 7.5, and 10 MS/s at the minimum accepted partial size, full 20-ms size,
and zero input. For every emitted candidate they compare exact score, control
score, margin, and tracking CFO with a separate `leo_presence_glrt` call at
the retained refined epoch and coarse CFO. They also require skipped-stage
timings and conditioned-bin counters to be zero.

Reproduce a host receipt with:

```
python3 reports/2026_09_28_arm_direct_glrt/build.py \
  --output /var/tmp/leo-host-direct-glrt-v1
```

`build.json` records both `cohort_direct`/`probe_direct` and
`cohort_control`/`probe_control`. No cohort or hardware execution is included
in this build status.

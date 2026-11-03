# Prepare vector rejection thresholds once per incumbent

The vector prefilter previously packed the same endpoint measurements, held-out
count and incumbent RMS for each satellite. The scorer now prepares that value
once per track partition and refreshes it whenever a better satellite replaces
the incumbent. Site packing, conservative rounding, rejection formulas, the
catalogue, time offsets and final double-precision scoring remain unchanged.
This affects only the optional vector/planned-bound build. The generic bound
entry point retains its on-demand preparation fallback.

Host component tests pass, including changing-incumbent comparisons of the
prepared and generic paths over cold/populated endpoint banks and extreme
int32 time offsets. Physical ARM held-out-bound, interval, location, session
and immutable-orbit tests pass. The full 400-point host search exactly matches
the frozen host result as parsed JSON.

An isolated ordinary-build control/new/new/control comparison on the same
16 held-out sites, one worker and 128 MiB endpoint-bank limit measures CPU
means of **10.973 seconds versus 10.769 seconds**, saving **1.85%**. Every output
byte matches the preceding qualified ARM control. Peak RSS stays about 114 MiB.
The pinned control is the prior ordinary 128 MiB build; current build logs and
changed source snapshots are retained here. This is a short benchmark, not a
full ARM search or concurrent-cadence qualification. A fresh profile is required
before replacing the existing PGO scorer.

Build and execute the host tests with:

```sh
TMPDIR=/var/tmp bash tests/native_adaptive/location/research/build_heldout_bound.sh \
  host /var/tmp/leo-modular-location-host /var/tmp/leo-threshold-host-v1 \
  warm progress subset planned capped horizon quiet uncached bank double-pair \
  immutable vector 128
```

Use `arm` and the qualified ARM object directory for the physical build.
`protocol.json` records every remote benchmark argument; `payloads.json` pins
the new executables. Per-run JSON, stderr timings and test output are adjacent.

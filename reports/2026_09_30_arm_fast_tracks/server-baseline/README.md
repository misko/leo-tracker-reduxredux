# Fresh f363 server tracking baseline

This baseline projects the fresh standard-server detector output for
`scan-fw-f363c7f29141d0b1` through the maintained server projection and tracking
functions. It does not rerun a detector, read cached candidate answers, use a
radio, or write to the public IQ store.

The maintained server path is:

1. `leo.application.scanner_trajectory.project_scanner_candidates`, including
   the standard fractional GLRT64 support geometry and the recording's saved UTC
   authority; then
2. `leo.analysis.persistent_hop_trajectory.reconstruct_persistent_hop_trajectories`
   with `PersistentHopTrajectoryConfig()`.

The fresh 10,066 passing server candidates produced 63 tracklets, 16 physical
groups, 16 bounded hypotheses, and 3,238 unique used observations. Tracking took
9.083 seconds on the host in the frozen run. `server-tracks.tsv` exposes this
Python oracle in the native CLI's exact `SUMMARY`/`CONFIG`/`TRACK`/`POINT` row
schema: 63 `TRACK` rows and 3,240 `POINT` rows. Two candidates participate in
more than one competing tracklet, hence 3,240 point rows and 3,238 unique used
candidate IDs.

The observation inputs are immediately reusable by the native tracker:

- `output/server-observations.tsv`: 10,066 fractional standard-server rows;
- `output/arm-observations.tsv`: 9,728 passing optimized-ordinary ARM rows,
  projected at their integer epochs with the maintained support geometry and an
  exact zero fractional offset; and
- side-specific `*-candidate-map.tsv` files binding every candidate and source
  group to its original visit, receiver, probe, rank, epoch kind, and detector
  side. Source availability comparisons must use this visit/RX/probe identity,
  rather than differing integer and fractional support-center times.

The current deployed standard server policy and the native fixture use different
minimum track thresholds. `ScannerTrackingService.run` constructs the maintained
Python default of a 4.0 second minimum span and eight observations. The native
tracker defaults to 3.0 seconds and six observations; the repository's
`export_ds9_oracle.py` explicitly makes that same 3/6 override. This is the
concrete reason the native default accepts 64 tracks and 3,245 unique points on
the server input while the actual server policy returns 63 tracks and 3,238
unique points. The Python result in `server-tracks.tsv` remains the oracle for
this comparison.

Reproduction command:

```sh
sudo -n /usr/bin/setsid /usr/bin/timeout --signal=TERM --kill-after=10s 600s \
  /usr/bin/env PYTHONPATH=/var/tmp/leo-arm-realtime-publication/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  reports/2026_09_30_arm_fast_tracks/server-baseline/export_baseline.py \
  --server reports/2026_09_30_arm_full_scan_comparison/server \
  --arm reports/2026_09_30_arm_full_scan_comparison/arm-v2 \
  --output reports/2026_09_30_arm_fast_tracks/server-baseline/output
```

`provenance.json` binds the clean maintained checkout, source modules, fresh
detector artifacts, both projected inputs, and every oracle output. Run
`validate_baseline.py` to verify candidate/map joins, finite values, the 0.025
gate, support ordering, and both JSON and native-row track accounting.

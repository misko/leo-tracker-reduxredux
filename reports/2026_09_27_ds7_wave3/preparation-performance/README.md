# DS7 combined preparation performance

`tools/ds7_combined_export.py` is a thin operational wrapper around the
unchanged `tools/ds7_export_baseline.py` scientific implementation. It loads
`ScannerTrackingInputStore` once and calls
`prepare_adaptive_tle_position_inputs` once. During the two unchanged exporter
calls, process-local hooks return those exact objects after validating the
session, bulk root, and input identity. A `finally` block restores both public
module attributes. Source stores and TLE archives remain read-only.

The wrapper does not cache serialized private storage, reconstruct paths, or
alter track, shortlist, catalogue, propagation, partition, or bank logic. Its
equivalence check compares track IDs, masks, times, measurements, shortlist
documents, manifests, NPZ keys, and every array value exactly. It ignores only
`elapsed_seconds` and the bank manifest's `tracks_sha256`, because the latter
changes when the elapsed field changes.

The already-prepared single-081 reference is
`scan-fw-cbbd87fc332c5f6e`. Its separate track and bank stages recorded 44.59
and 80.73 seconds, respectively. The combined operation completed in 108.62
seconds: 23.26 seconds for the sole real source load and preparation, 17.18
seconds in the unchanged track exporter, and 68.05 seconds in the unchanged
bank exporter. It eliminated one real public source load and one real
preparation call. The internal unchanged calls still constructed and closed
their expected adapters and invoked their expected preparation entry points;
the validated hooks returned the already prepared identities.

This wall-time comparison is descriptive. Host load differed between the
historical separate run and the combined run, so the observed 16.71-second
difference is not attributed entirely to the reuse change.

Exact science equivalence passed for 62 tracks and 187 NPZ arrays. Track
documents match after removing only elapsed time; shortlist JSON values match
exactly; bank manifests match after removing elapsed time and the track
digest induced by it. Each manifest was first verified against its own track
file. NPZ key sets, dtypes, shapes, candidate IDs, masks, timing grids,
measurements, positions, and velocities are exactly equal.

Source hashes before the benchmark:

- Combined wrapper: `6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729`
- Unchanged scientific exporter: `4d2e4bb96e687ca9fe1a035c138c87e55d2976d0136bffac182b1bc380c42dc4`
- Benchmark receipt: `3ac8ad056f180db0a5f3612d1e2dc8c32362127669114dfa779857f496848298`
- Combined bank NPZ: `cacb2dc722fd45e095f9595b5b8e0e4c0e6415c83e939ab983a375c43c83886a`

Four component tests cover exact cached object reuse, restoration after
success and failure, binding validation, and equality rules for scientific
outputs.

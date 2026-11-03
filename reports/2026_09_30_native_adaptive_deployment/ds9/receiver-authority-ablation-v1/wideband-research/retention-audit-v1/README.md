# Fixed-eight retention audit

The four apparent retention differences were caused by the receiver-frequency
authority supplied to the isolated replay.  They were not caused by a different
candidate insertion or canonical-retention rule.

The persisted Standard product is schema v9 with configuration schema v6,
analyzer `adaptive-hop-variable-dwell-fractional-glrt64-cfo-v1`, binding
`sha256:4ff246ba978647e28e725a2c55066b8f79aa685b3310df6f4ca7e4006d4bd702`,
7.5 MS/s, a 20 ms probe, a 120 ms stride, eight candidates, and a 0.025
fractional-margin gate.  It remains the parity target.  The public binding does
not identify the historical Python source or native acquisition DSO by hash, so
this audit does not claim a cryptographic historical executable match.

The current maintained server implementation at Git
`ea2756bda8101f5a231f38e1761747766a2e0572` independently reproduces every one
of the 43 persisted candidate rows on the fixed-eight visits bit for bit for
rank, epoch, gate outcome, and the five persisted fractional detector fields
when it compiles the capture geometry.  For channels 1 through 4, that geometry places
the lower-edge Qin pilot at IF centers 959,687,500, 1,209,687,500,
1,459,687,500, and 1,709,687,500 Hz against tuned IF centers 960,000,000,
1,210,000,000, 1,460,000,000, and 1,710,000,000 Hz.  The receiver calibration
is therefore **-312,500 Hz** on all eight visits.

That value comes from recording and configuration authority, never from a
candidate output: the repo-retained capture-manifest event copy and matching
persisted projection source rows supply tuned frequency, channel, and edge,
while the maintained Starlink frequency contract supplies the selected Qin
pilot center.  These records bind the original input-manifest hash, but the
original input-manifest content is not copied into this report.  The compilation is
`pilot_if_center_hz - tuned_if_hz`; subtracting the same 9.75 GHz LNB LO from
both RF values leaves -312,500 Hz.  The earlier isolated schedule construction
did not retain a geometry-compiler invocation and wrote `0,0` directly.  This
is equivalent to treating the tuned center as the selected pilot center and is
the concrete authority error.  The corrected diagnostic calls
`compile_pilot_search_geometry` with `actual_rf_hz - 9,750,000,000` as the
tuned IF and writes its `frequency_reference.center_hz` to the replay schedule.

The isolated wideband schedules passed receiver centers of `0,0`.  The coarse
search converts its 80 kHz residual grid to absolute CFO using the receiver
center before local-maximum selection and separated top-eight retention.  A
312.5 kHz translation changes the phase of that grid relative to the signal.
Retention uses the coarse coordinates (5 samples and 10 kHz separation), and
there is no post-refinement deduplication when different coarse paths later
converge.  This explains all four observations:

| Visit | Zero-center observation | Result with -312.5 kHz authority |
| --- | --- | --- |
| 126 | distinct extra and score/rank shift | the persisted ranks and values |
| 191 | one converged duplicate absent | two converged main paths plus the persisted nearby support |
| 193 | adjacent equivalent support differs | the persisted adjacent integer representations |
| 346 | an extra converged duplicate | one persisted second-support path |

The maintained coarse implementation uses 12 initial anchors
`range(2, 302, 26)`.  The adaptive peer-recovery configuration has 22 anchors
`range(2, 302, 14)`, but RX0 already passes the fractional gate on these eight
visits and is not rerun through peer recovery.  Anchor symbols are not fields in
the persisted schema-v9 binding; the exact replay establishes the selected-row
equivalence for this bounded audit.

Replaying the existing isolated native wideband artifact with only the receiver
center corrected produces the same rank, integer epoch, fractional status, and
nullability for all 64 retained candidates.  Across all 64 rows, the largest
native/server differences are 2.911e-9 Hz for CFO, 3.881e-13 samples for the
fractional epoch, and 1.817e-13 for a score or margin.  These are within the
frozen 1e-6 Hz and 1e-10 scalar tolerances.  The corrected native gate count is
23, exactly matching the 23 persisted passing rows, without threshold changes.
The current server and the original zero-center native run also retain identical
coarse `(epoch, CFO)` multisets; their largest coarse-score difference is
8.327e-17.  This second comparison isolates the authority error from the native
retention implementation.

[`diagnostic.json`](diagnostic.json) contains both server coarse inventories,
all current-server candidates, both native candidate sets, every numerical
delta, source and binary hashes, and the persisted-product configuration.
[`qualification.json`](qualification.json) records the bounded result and
inputs.  The corrected native calls are `visit-*.jsonl`; the original
zero-center calls remain under `../fixed8/`.

Reproduce the maintained-server diagnostic from this directory:

```sh
/usr/bin/time \
  -f '{"wall_seconds":%e,"user_seconds":%U,"system_seconds":%S,"maximum_rss_kib":%M}' \
  -o diagnostic.time \
  /var/tmp/leo-arm-realtime-publication/.venv/bin/python diagnose.py \
  2>diagnostic.stderr
```

Reproduce one corrected native call (replace the visit for the other seven):

```sh
../artifacts/host/leo-native-adaptive-replay \
  --manifest schedules/visit-0126.tsv \
  --deployed-server-interval-fractional \
  --thermal-path /nonexistent --thermal-scale 1 --thermal-offset 0
```

No production source, golden, threshold, raw data, hardware, or RF state was
changed.  The correction required for subsequent ordinary/full-scan parity is
to pass the source-bound receiver calibration into the native wrapper, rather
than to change matching or retention semantics.

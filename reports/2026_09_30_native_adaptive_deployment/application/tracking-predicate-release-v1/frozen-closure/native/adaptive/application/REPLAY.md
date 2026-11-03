# Recorded Session replay

`replay.cpp` is a bounded application executable over the public `Session`
composition. It reads the 24,681-row DS9 projection input, reconstructs the one
persisted counter/UTC bracket, emits scanner candidate events with explicit
historical target metadata, drains the 64-item Session queue, publishes the
first ten seconds, reconstructs tracks and location records, builds a
complete 11,129-satellite orbit, and evaluates one location point at the recorded pose.

The persisted projection input supplies the device counter, UTC center, bracket
width, source generation, RF channel/edge, candidate values, and input and
analysis digests. Replay constructs the Timebase bracket from that saved center
and width exactly, as the timing component fixture does. It does not substitute
host arrival time. The historical capture predates persisted Fast Lock CRCs, so
the target fixture declares `historical-unavailable` and the application selects
the ingress contract's explicit historical metadata mode. Live sessions remain
in the default mode and require nonzero prepared and recalled CRCs.

The saved tracking candidates are loaded only after Session publication. They
are a diagnostic membership comparison and never supply an observation, graph,
partition, track, location record, orbit, or score to the pipeline. The fixed
DS9 result is 394 projected observations, 11 reconstructed tracks, 11 location
records and exact reference membership. The one-point search scores every TLE
without an oracle shortlist, reports its native weighted MSE and match counts,
and fails unless at least one track matches. Saved graph support strings and
winners are not inputs, so the executable makes no server score parity claim.
Satellite identity comes from matching decimal or Space-Track Alpha-5 fields
in each TLE pair. Duplicate and mismatched catalogue identities are rejected;
catalogue row ordinals are never substituted for satellite IDs.

Input memory is bounded to exactly 24,681 projection rows, reference parsing is
bounded to 100,000 rows while retaining only the ten-second prefix, and the
Session queue is fixed at 64 observations. Input validation accepts at most
20,000 satellites, while the allocated orbit arena is exactly the saved 11,129
satellites by 32 knots and two state banks. A longer observation replay remains
a separate workload.

Build and run with explicit fixture and library authority:

```sh
export LEO_ONLINE_LIBRARY=/path/to/matching/host-online-build
export LEO_DS9_PROJECTION_INPUT=/path/to/leo-ingest-ds9.tsv
native/adaptive/application/build-replay.sh host /tmp/leo-recorded-replay-host
```

The projection TSV is the hash-bound native export recorded in
`reports/2026_09_30_native_adaptive_deployment/timing-ingest/receipt.json`
(`618fe88156d77b056548b08b49678aa3015ea050d005e26a34aa5ba7d80623de`).
The build fails if this explicit input, the four-target metadata, the causal TLE
catalogue, recorded search pose, or the diagnostic candidate fixture is absent. Sanitizer and ARM
builds use `sanitize` and `arm`; the latter does not execute automatically.

An optional final CLI argument writes a diagnostic TSV. Each native track point
then carries the public snapshot's support digest, partition seed, observation
identity, training mask, time and measured CFO beside the projected numeric
support moments in decimal and raw IEEE-754 bits. The diagnostic values do not
flow back into Session, reconstruction, partitioning or scoring. They exist to
localize cross-architecture score differences without changing inference.

The first full ARM execution exposed a scientific portability failure even
though all 394 observations and 11 track memberships matched: host and ARM
weighted MSE differed by about 18%. The preserved before-fix diagnostics in
`reports/2026_09_30_native_adaptive_deployment/application/` show that all 11
support digests and partition seeds differed, and 76 of 150 training-mask bits
changed. `qualification.json` records that failure and its executable hashes.

The corrected runtime computes support moments from translation-invariant
integer doubled centers with explicit binary64 rounding. In the subsequent
physical ARM replay, the 150-row diagnostic TSV was byte-identical to host,
including moment bits, support digests, partition seeds and masks. Host and ARM
RMSE differed by `1.284590211980685e-10` Hz, below the `1e-6` Hz acceptance
tolerance. `deterministic-qualification.json` records the corrected host,
sanitizer and physical ARM evidence. This is native cross-architecture
qualification; it does not add a server-score parity claim.

Replay output schema v2 adds diagnostic wall-clock stage measurements for
input loading and validation, all-row prefix projection, selected ingress and
drain, publication, reference comparison and diagnostic writing, orbit build,
search begin, and search resume. These monotonic measurements are taken only at
stage boundaries and never enter projection, reconstruction, partitioning,
orbit construction, or scoring. Whole-process ARM time includes the 24,681-row
projection pass and diagnostic reference reconstruction, so it is not a
steady-state inference latency measurement.

On the profiled PLUTO+ ARM run, the total recorded-fixture stage time was
29.205 seconds: 1.367 seconds loading and validating, 18.624 seconds projecting
the complete 24,681-row input to select the prefix, 0.429 seconds ingesting and
draining the selected prefix, 1.608 seconds publishing native tracks, 2.021
seconds reconstructing and comparing the diagnostic reference, 3.824 seconds
building all 11,129 satellite trajectories, and 1.332 seconds resuming the
single-point full-catalogue score. Search begin took 0.048 ms. The separately
measured whole process took 29.264 seconds. The projection and reference stages
are recorded-replay setup and diagnostics, so the 29.264-second value must not
be reported as per-point or steady-state inference latency.

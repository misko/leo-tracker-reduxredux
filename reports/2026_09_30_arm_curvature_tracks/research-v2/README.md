# Bounded local-curvature tracker research v2

This is an isolated research tracker. It does not change the maintained
tracking implementation or any published contract. It consumes the existing
13-column candidate TSV and emits the existing `SUMMARY`, `CONFIG`, `TRACK`,
and `POINT` records. `POINT` membership and dealiased CFO are the nonlinear
result. The `TRACK` rate, intercept, and residual fields are a final weighted
linear compatibility summary and are labeled as such in `CONFIG`.

For each lane, the tracker makes source-local seeds from candidates in adjacent
source groups. It traces each seed forward and backward with a bounded beam.
The state contains frequency, rate, a locally fitted acceleration, and
frequency/rate uncertainty. Association lifts CFO by the nearest alias to the
prediction, selects at most one candidate per source group, keeps two short
alternatives at crossings, caps gaps at four seconds, and requires eight
points over four seconds. Exact membership and alias-aware near duplicates are
consolidated; up to 16 alternatives per lane remain. No TLE, satellite,
reference-track, or oracle identity enters reconstruction.

The primary acceleration preset is 250 Hz/s². It is twice the rounded maximum
of the independent 421-second visible-orbit envelope in `../orbit-envelope.json`.
Local quadratic fitting starts with at least six points spanning four seconds,
uses at most 32 points over 12 seconds, and clips the fitted quadratic
coefficient to the configured bound. The fit RMS must remain at most 2,500 Hz,
and the association gate is capped at 5,000 Hz. Measurement updates can change
the local rate, so this is a bounded local-fit and prediction model, not proof
that every finite difference of the resulting trajectory obeys a hard physical
acceleration limit. Acceleration zero is a local-linear-state ablation with no
explicit quadratic prediction; it is not a global straight-line tracker.

Candidates in one source group may differ in support-center time by up to 20
ms. The actual time of each candidate is used for prediction and fitting. This
is required by the saved DS9 candidates, whose observed maximum same-source
spread is about 1.02 ms. Larger source-group spreads fail validation.

The component test covers curved truth, aliases, deterministic noise, a missing
visit, crossing alternatives, a linear-state ablation, a hard gap, excessive
curvature/noise runaway, malformed configuration, and same-source candidates
with a one-millisecond time offset. Host and ASAN/UBSAN runs passed. ARM files
are cross-built only here; physical results are recorded separately by the
root qualification owner.

The independent two-curve synthetic diagnostic has 117 members per curve,
75 Hz noise, aliases, two-second gaps, clutter, and a crossing. The primary
run retained a 117/117 pure track and a 117/120 track for the other curve. It
also retained one 121-point mixed crossing alternative (49 and 72 truth
members). This proves coverage on that fixture but does not prove unique
identities or server equivalence.

Build and run commands, from the repository root:

```sh
TMPDIR=/var/tmp/leo-curvature-host-tmp \
  native/adaptive/tracking/research/curvature_tracks/build.sh host \
  /var/tmp/leo-curvature-host-v8
TMPDIR=/var/tmp/leo-curvature-sanitize-v8-tmp \
  native/adaptive/tracking/research/curvature_tracks/build.sh sanitize \
  /var/tmp/leo-curvature-sanitize-v8
TMPDIR=/var/tmp/leo-curvature-arm-v8-tmp \
  native/adaptive/tracking/research/curvature_tracks/build.sh arm \
  /var/tmp/leo-curvature-arm-v8
/var/tmp/leo-curvature-host-v8/leo-curvature-tracks INPUT.tsv \
  --acceleration 250 > output.tsv 2> output.log
```

The CLI accepts only the frozen presets `0`, `125`, `250`, and `500` Hz/s².
The `TIMING reconstruct_s` record excludes TSV parsing and output formatting.

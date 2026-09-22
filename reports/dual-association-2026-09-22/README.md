# Dual association for adaptive scans

Status: implementation and local canary validation complete; deployment and HTTP/backfill coverage pending.

## Required outputs

Each adaptive scan retains two separate products. The existing Sausalito arm is site-assisted: it
uses the declared Sausalito observer position for visibility, catalogue association, and position
diagnostics. The additive `scanner-blind-regional-v1` arm excludes a known receiver position from
track construction, catalogue selection, association, and inference. It publishes association,
position, and alternative-position-mode PNGs plus the sealed JSON used to reproduce them.

The blind arm is regional rather than geographically prior-free. Its declared search region is a
14,484.096 km square centered on Denver, spanning nominal map coordinates of -7,242.048 km to
+7,242.048 km east and north. This broad Denver-centered boundary is a real geographic prior.

## Blind inputs and binding

RF tracks are reconstructed from qualified GLRT observations without using saved TLE reviews,
site-assisted candidate identities, or an observer coordinate. The input document binds the raw
input manifest, analysis manifest, deterministic track support, input configuration, and the full
eligible catalogue digest. TLE selection uses the latest archived snapshot collected before the
earliest selected observation minus the 505 second causal guard. Elements whose epoch is not before
the observations, labelled debris, and members that fail propagation are excluded with accounting.

Every retained Starlink member from that causal snapshot receives prior mass through the declared
full catalogue size. Visibility at a trial receiver location may make a member's likelihood zero,
but does not renormalize the remaining catalogue into a site-conditioned shortlist. Candidate
weights are composite, uncalibrated diagnostic mixture weights rather than posterior probabilities.

## Current bounded search

The input adapter selects at most 32 tracks, 128 observations per track, and requires at least 14
observations and 7 seconds of support. Association accepts at most 64 tracks. Coarse position search
uses the eight longest tracks, at most 64 deterministic observations per track, a 1,000 km grid,
and up to eight modes separated by 1,000 km. The leading two branches receive nested 9 by 9 searches
over 500 km and 100 km half-widths, followed by bounded continuous Nelder-Mead refinement with at
most 80 iterations and a 0.05 km coordinate tolerance.

The optimizer tolerance is a stopping control, not position accuracy or uncertainty. The composite
objective uses a 250 Hz signal scale, 30 kHz null scale, effective count 6, signal prior 0.5, and a
-1 degree minimum elevation. These fixed modeling choices and the regional boundary limit what can
be inferred. No sub-kilometer accuracy claim follows from grid spacing or optimizer convergence.

## Validation and publication

Training determines location and identity ranking. Held-out observations report predictive evidence
and do not reselect the solution. The sealed result records observation counts, track and exclusion
accounting, work counts, runtime, per-track measured and predicted frequency arrays, coarse-map
scores, alternative modes, source digests, and causal snapshot provenance. A user-provided reference
coordinate is attached only after inference as an evaluation object; it is never an estimator input.

The blind namespace is immutable and separate from the Sausalito products. Publication writes the
JSON and three PNGs atomically under a per-session writer lock and seals the manifest last. The API
serves only manifest-bound artifacts and checks their declared byte counts and SHA-256 digests.

Validation currently covers deterministic numerics, held-out isolation, causal input selection,
site-provenance flags, non-finite rejection, corrupt document and PNG bindings, interrupted unsealed
publication retry, API digest binding, and immutable publication conflicts.

## Canary and coverage

Two canaries demonstrate successful execution and a **negative positioning result**. The e3 row is
the immutable production publication copied under `evidence/e3`; the e31 row is an unsealed research
canary and is included only as exploratory context.

| Capture | Tracks / observations used | Catalogue | Analysis time | Leading position | Revealed error |
| --- | --- | --- | --- | --- | --- |
| `scan-hop-e31b77794a04c236` | 32 / 844 | 11,129 | 59.04 s | 20.69527°, -68.56986° | 5,483.6 km |
| `scan-fw-e3bc0741ecf02704` | 32 / 1,247 | 11,108 | 121.284 s | 36.62650°, 134.95654° | 8,540.3 km |

Both retain eight modes. The e31 input has 43 eligible tracks and 1,011 eligible observations;
167 observations are omitted by declared limits. Its measured peak RSS is about 1.25 GiB.
The e3 canary renders measured and predicted trajectories that look close despite a grossly wrong
location. Its leading mode has 26 tracks above the conditional 0.5 association-weight threshold.
Its production runtime was measured while the host was under concurrent load; a separate local run
took 76.675 seconds, so neither value is a throughput guarantee.
**That threshold does not validate identity or position.** Candidate weights are conditional on each
trial location and are not calibrated global identity probabilities. A different satellite and a
fitted constant offset can mimic a short Doppler arc at a distant receiver location.

The bounded coarse search also cannot certify the global optimum. These failures motivate longer,
shared-pass multi-scan evidence and stronger symmetric identity/model checks in the separate 12-hour
study. They must remain visible in the automatic results, rather than selecting the mode closest to
the reference or importing the Sausalito shortlist.

Local checks: 191 web tests passed; the focused integration suite passed 32 tests before the added
synthetic position-recovery test. Synthetic recovery uses six diverse 320-second orbital arcs,
recovers their identities and position within 5 km, and is not evidence of real-data accuracy.

- HTTP verification of all three PNGs: pending.
- Adaptive-scan backfill coverage: pending.

# Bounded positioning evidence for each adaptive scan

## Scope

Extend the existing queued tracking stage with a conditional per-scan position
diagnostic. Reuse time-separated sampling from the sparse-position experiments.
Do not introduce another queue or a new RF collection. Persist JSON and a PNG
for every terminal scan, including scans with insufficient positioning evidence.

This is not a blind location fix. Satellite identities were shortlisted using
the configured observer site. The position search itself must not receive that
site as a starting coordinate, prior centre, fitted target or evaluation truth.
Use a declared Denver-centred 9,000-mile square and fixed altitude for this
initial diagnostic. Report the identity conditioning prominently.

## Limited numerical model

- Stationary receiver, nominal causal SGP4 states and qualified recorded UTC.
- Two horizontal coordinates and one profiled constant frequency offset per
  independent track. No free slope, per-track timing correction or orbit update:
  a single short scan cannot reliably identify these alongside position.
- Frozen non-abstaining candidate identities, with duplicates across trajectory
  hypotheses removed. This diagnostic does not upgrade satellite identity claims.
- Metadata-only time-separated sampling: at most five fitting observations per
  track, 32 tracks. Evaluation observations cannot select location or parameters.
- Bounded coarse regional search and local refinement. Report local geometry,
  residuals, selected observations, boundary and numerical failure flags.
- Require at least three distinct satellite candidates and enough observations;
  insufficient, rank-deficient or ambiguous results are successful diagnostic
  outcomes, not a fabricated fix or a processing retry loop.

## Integration

1. Add an immutable position V1 contract inside a new tracking V12 publication;
   retain readers for all published tracking versions.
2. At the end of tracking, prepare position evidence from canonical measured
   observations and the frozen catalogue. Both catalogue availability and each
   selected element epoch must strictly precede capture start.
3. Run the bounded pure analyzer and render its PNG. Early tracking outcomes
   still publish an explicit positioning insufficiency reason and status figure.
4. Include positioning policy in the queue configuration digest so old products
   cannot masquerade as the new analysis. Reuse existing leases and work limits.
5. Serve the position JSON and PNG through the existing scanner page and
   artifact routes, with the conditional nature and insufficiency reasons visible.

## Verification

- Synthetic position recovery, held-out poisoning isolation, sampling bounds,
  rank deficiency, too-few-sources and search-boundary tests.
- Reject future element epochs and future catalogue snapshots; preserve input,
  policy and catalogue digests.
- Versioned persistence and legacy-reading tests, queue binding tests, and
  scanner-page/artifact-serving tests.
- Replay archived scans with sufficient and insufficient evidence; inspect the
  generated JSON and PNG. Verify work is bounded and capture continues unchanged.
- Document and verify production wiring before declaring the integration done.

## Scientific limit

The 48-hour experiments used hundreds of tracks. A single 300-second scan may
contain too little independent geometry for a useful location. Its useful output
may be a broad conditional region or an explicit insufficiency result. This
first integration must not inherit the multi-day sub-kilometre claim.

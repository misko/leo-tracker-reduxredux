# Recording-disjoint RX test: positive mean, failed consistency gate

**Decision: do not advance this unchanged model to geographic evaluation.**
The predeclared progression gate fails because only two of four recordings
improve in X→Y, below the required three. The reverse direction improves all
four. Neither the threshold nor cohort was changed after seeing results.

| Held-frequency gain relative to matched regularized baseline | X → Y | Y → X |
|---|---:|---:|
| Normal RX, occupied-second weighted | +0.0001571 | +0.0011782 |
| Normal RX, equal-recording average | +0.0003089 | +0.0011966 |
| Normal RX, recordings improving | **2/4 — fails** | 4/4 |
| Reversed RX, occupied-second weighted | −0.0012851 | −0.0033419 |
| Candidate-independent null | floating-point zero | floating-point zero |

Positive is a decrease in held-frequency NLL per observation, not a decrease
in location error. Normal beats reversal in the aggregate, suggesting some
direction information, but the incremental gains are small and inconsistent.
This is not evidence that receiver geometry is useless; it is insufficient
evidence to promote this particular association update.

## Complete recording results

| Recording | Rate MHz | Supported / retained tracks | Normal X → Y | Normal Y → X |
|---|---:|---:|---:|---:|
| scan-fw-e84e2f55976c0a8c | 2.5 | 31/64 | +0.0017528 | +0.0010592 |
| scan-fw-8f4f960d9db67798 | 10 | 44/60 | −0.0013133 | +0.0030580 |
| scan-fw-a077447f07d9f81f | 2.5 | 49/58 | +0.0014572 | +0.0004620 |
| scan-fw-127d8fc36e804ae2 | 2.5 | 55/59 | −0.0006613 | +0.0002072 |

All four runs completed. Of 241 topology-retained tracks, 179 support both
partitions and 62 fail the fixed minimum-observation criterion. This is 358
reciprocal predictions, not 358 independent observations. Unsupported tracks
remain explicitly listed in each shard. The results are conditional on this
support and on tracks reconstructed from the full recording.

## What was frozen and separated

- Dataset: frozen DS6 manifest, 43 captures. Excluded 28 prior RX membership
  IDs and captures lacking the required published completeness/attestation.
  Seven candidates remained; the four lowest SHA256(`20260928:session_id`)
  were selected before loading their RF-derived input observations.
- No replacements, no tuning on selected outcomes. Four metadata-selection
  tests passed before selection; the full selection/accounting is in
  `manifest.json`.
- All inputs were loaded through the public tracking/capture adapters, with
  capture-manifest, pose, full-visit and simultaneous-RX checks. Caches are
  immutable local copies; source stores were not modified.
- Frequency, receiver pairing, feature normalization, reception coefficients,
  and shared-effect scales use the frozen six-recording calibration, disjoint
  from all four selected recordings. The contract binds 196 input/model/code
  files and checks calibration membership. Capture time intervals also do not
  overlap calibration recordings.
- Grouping and scoring match the prior protocol: session-wide 10-second blocks
  joined by source overlap and RX pairing; seed 20260927; separately refitted
  X/Y shortlists and CFOs; 50% uniform support in both the frequency-only and
  RX-updated candidate posteriors. Frequency likelihood is counted once.

The selected recordings form two nearby-in-time pairs (01:46/01:53 UTC and
04:43/04:50 UTC). They must not be treated as four independent satellite passes.
They are unused by this RX development effort, not universally unseen in other
DS6 research. The coordinate reference remains operator-supplied rather than
surveyed GPS. These limitations preclude broad resolution claims even if the
small progression gate had passed.

## Verification and reporting correction

The scorer reconstructs posteriors, held scores, and aggregates; checks raw
partition membership and reciprocal accounting through the grouped verifier;
and verifies the frozen contract before scoring all four shards. Candidate-
independent null gains are below 2e-16 per recording. Six local selection/gate
tests pass; the underlying grouped replay suite has 23 passing tests.

`summary-v2.json` is the authoritative summary. The initial `summary.json`
counted tiny positive floating-point null residuals as improvements. Revision 2
uses a 1e-10 reporting tolerance. **No score, normal/reversed improvement count,
or progression decision changed.** The original receipt is retained for audit.

## Next action toward the goal

Keep this cohort as evaluated development data from now on; do not reuse it as
an untouched test. The next useful diagnostic is to explain the two X→Y
regressions and determine whether they arise from candidate-specific RX
miscalibration, residual frequency nonstationarity, or genuine directional
ambiguity. Do not sweep weights/seeds on these recordings and present the best
setting as confirmation. A materially changed model requires a new frozen test
before making a geographic-resolution claim.

No location search was run here. Better geographic resolution remains unproven.

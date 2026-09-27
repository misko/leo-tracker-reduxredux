# DS6 robust CFO transfer and receiver-drift diagnostic

**The 809 m single-development-scan result does not establish DS6-wide
sub-kilometre accuracy. None of these four additional scan estimates is below
1 km. The goal remains active.** This turn made progress by testing transfer
and identifying a nuisance-model experiment supported by held-data evidence.

## Frozen experiment

The four recordings and their randomized whole-visit partitions are reused
unchanged from the pre-existing rate-stratified common-rate validation study.
All outcomes are retained. They are development scans with previous analyses,
not an untouched final test set. DS6 membership and all supplied metadata seals
verify; no RF was collected or raw IQ modified.

The estimator is the prior Student-t4 CFO model, fixed at 100 Hz, with a
training-profiled offset per track, catalogue-identity marginalization, and
one shared timing offset marginalized over -5..5 seconds at 0.25-second
spacing. Candidate propagation at scored epochs is exact. Candidate shortlists
are unions of training-only top-eight candidates at the center and corners;
they are approximate, with their retained anchor masses recorded.

The local search starts at the **other scan's inferred** 37.856250, -122.484375
position. It does not read the supplied roof coordinate. Three seven-by-seven
grids have half-widths 0.05, 0.0125 and 0.003125 degrees. Each refinement is
centered on the preceding training-score winner. A boundary winner stops the
run rather than being described as convergence. This is a conditional local
transfer experiment, not a blind global-location evaluation.

`protocol.json` was frozen before execution and binds input, model, search
source and donor-result hashes. The original 43-scan dataset is not narrowed
to these four scans; this is one bounded diagnostic iteration.

## Geographic results

Errors are evaluated afterward against the operator-provided DS6 roof
coordinate. It is not a surveyed reference with known uncertainty.

| Scan | MS/s | Tracks | Error | Boundary stop? |
|---|---:|---:|---:|---|
| scan-fw-5eaaa2a8f8c995b3 | 2.5 | 61 | 3,602 m | No |
| scan-fw-c78fb2dba2465361 | 5 | 64 | 4,633 m | Yes |
| scan-fw-c7e37f65ae9e08b0 | 7.5 | 64 | 1,264 m | No |
| scan-fw-3221795d82a1c7ec | 10 | 32 | 6,500 m | Yes |

The smallest top-eight anchor mass is 97.097% on the 2.5 MS/s scan, so catalogue
truncation remains a material approximation. The two boundary results are not
final unconstrained estimates. Each run took approximately 32–200 seconds.

## Conditional receiver-drift diagnostic

At each inferred location and shared MAP timing, choose each track's catalogue
candidate using training data only. Fit one linear normalized-CFO drift per
receiver jointly with the track offsets, using Student-t IRLS. Freeze both
drifts and offsets for scoring held visits. This is a conditional diagnostic:
wrong position, imperfect identity selection, normalization and real hardware
drift can all contribute. It is not an RF oscillator calibration measurement.

| MS/s | RX0 slope, Hz/s | RX1 slope, Hz/s | Held log-score change |
|---|---:|---:|---:|
| 2.5 | -0.198 | -6.600 | +40.640 |
| 5 | +2.034 | -4.389 | +14.076 |
| 7.5 | +0.536 | +1.038 | -3.284 |
| 10 | unavailable | -2.119 | +5.322 |

Higher held log score is better, compared on identical observations with the
same Student-t density. The 10 MS/s input contains only RX1 positioning tracks;
RX0 absence is retained, not silently replaced. These improvements do not
demonstrate improved position accuracy: the geographic estimates were held
fixed for this diagnostic. Track likelihoods remain correlated/composite.

## Verification and next iteration

Nine checks pass: original input hashes, consistent randomized whole-visit
partitions across tracks/receivers, complete 49-point coverage for executed
stages, training-only location selection, and synthetic recovery of receiver
drift with arbitrary held-data perturbations. The eight previous robust-model
and exact-timing checks also pass.

Next, compare a predeclared joint position/receiver-drift model against this
frozen baseline on the same observations. Fit drift and catalogue choices only
on training evidence, examine identifiability and nuisance bounds, and score
held prediction without choosing configurations by roof-coordinate error.
Boundary scans need a training-directed search extension. Broader randomized
whole-scan validation over all 43 DS6 recordings is still outstanding.

Reproduction uses `PYTHONPATH=src`, one BLAS thread, and the existing scientific
runtime at `/home/mouse9911/gits/leo-adaptive-position-deploy/.venv/bin/python`.
`run.py --session SESSION_ID` requires read access to the protected causal TLE
archive; it refuses to overwrite an existing output. `summarize.py` is the only
new script that reads the roof coordinate. `clock_audit.py` computes the
conditional drift check; `pytest test_transfer.py` verifies the experiment.

# Broad-prior acquisition prototypes

The 64-scan comparison improved first-factor probability retention but produced
**no accepted new localization estimates**. Median retained probability rose
from **90.653% to 99.99924%**, and first-factor discarded-mass failures fell from
**48/64 to 8/64**. All new attempts stopped after the first factor on declared
approximation or support gates. The adaptive map also remains unresolved.

Three SOL workstreams implemented likelihood diagnostics, Gaussian mixture
reduction, and an adaptive spatial probability map. This experiment preserves
the original 64-scan baseline and uses its same independent DS9/DS10/DS11 scans,
observations, causal orbit catalogues, overlap exclusions, and Sacramento prior.

The intended prior is uniform within 250 km of Sacramento. The matched Gaussian
comparison uses the original 32 equal-area cell moment Gaussians, including its
documented 2.55% probability leakage outside that disk. Every scan starts fresh;
neither previous scans nor receiver reference coordinates initialize inference.
The map instead represents the disk by exact-area cells.

## Matched Gaussian comparison

Final metrics are in `comparison/comparison.json`; all attempted scans remain in
the denominator. A rejected prefix is not an accepted location estimate.

| Metric | Original Gaussian sum | New 128-to-32 reduction |
|---|---:|---:|
| Independent scans attempted | 64 | 64 |
| Accepted complete estimates | 0 | 0 |
| Median first-factor retained probability | 90.653% | 99.99924% |
| First-factor discarded mass above 1% | 48 | 8 |

New gate counts overlap: support envelope 59, component center outside the
intended disk 34, projected merge score 42, and discarded probability eight.
All 64 new attempts produced sealed receipts, with no exceptions or timeouts.
Median launch-inclusive runtime was 11.45 seconds (range 6.55–22.97 seconds).
Because these are rejected one-factor attempts, that runtime is not a full-scan
throughput estimate. The unchanged greedy baseline accepted 12/64 scans;
the unchanged prior-only control completed 64/64 without using observations.

The support diagnostic explains part of the rejection pattern: in 28 of the
59 support failures, all components triggering the five-sigma envelope check
together carry less than 1% mixture weight. This is not actual escaped
probability, and some other failures carry substantial weight. See
[SUPPORT_DIAGNOSTIC.md](SUPPORT_DIAGNOSTIC.md) before changing that gate.

![First-factor retained probability](comparison/retention-scatter.png)

![Completion and overlapping rejection reasons](comparison/completion-and-gates.png)

The new reducer temporarily materializes up to 128 children before merging to
32 retained components. It preserves full joint first and second moments,
including location/nuisance cross-covariance. Its pair-selection score uses six
coordinates for speed. That projected score is a heuristic, not a full-state
KL certificate. The unchanged discarded-mass and physical-support checks plus
a frozen 0.1-nat projected merge-score limit can reject the result. Increasing
temporary capacity and changing reduction both contribute to this comparison;
it does not isolate merging at equal peak memory.

See `MERGING_FREEZE.json`, `PROTOCOL.md`, sealed receipts in `runs/merging/`, and
the final audit for provenance and limits. Each attempt has a 90-second external
budget. At most two fits run concurrently with one numerical thread each.

## Likelihood checks

On 64 development tracks from eight DS9 scans, candidate/background prior mass
normalizes to within 2.23e-16. At Sacramento, background posterior probability
is below 0.01 for 55 tracks and above 0.99 for nine; none are intermediate.
Conditional signal identity is usually concentrated on one candidate despite
roughly 500–640 visible candidates. Saturation motivates calibration tests but
does not alone establish miscalibration.

An independent closed-form forward generator selects the known satellite on a
clean synthetic track; an injected frequency outlier makes the background
branch win. These are bounded identity checks, not real-data accuracy or
coverage validation. See `diagnostics/README.md` and `synthetic-results.json`.

## Adaptive spatial map

The prototype integrates satellite identities and background at each spatial
node, keeps shared nuisance hypotheses consistent across tracks, and replays
all previous factors whenever cells split. Tests catch the incorrect product
of cell-average likelihoods and refinement based only on nuisance variation.
Its vectorized RF callback agrees with the frozen physics to 4.075e-10 in log
likelihood on the development check.

The corrected 512-cell pilot processed eight DS9-F001 tracks in 34.40 seconds.
It exhausted spatial resolution after the first track, and a same-partition
quadrature check failed on track four. Its status is therefore
`spatial_convergence_unresolved`. This pilot fixes height, clock, receiver
drift, and satellite epoch offsets to zero: it is a conditional diagnostic,
not a matched substitute for the Gaussian nuisance posterior. It was not
expanded to 64 scans or scored against the receiver reference.

![Conditional spatial map; convergence unresolved](spatial/corrected512-conditional-spatial-mass.png)

![Spatial and quadrature diagnostics](spatial/corrected512-convergence.png)

`spatial/README.md` documents interrupted development attempts and the initial
128-cell artifact that predates correctness fixes. That earlier artifact must
not be interpreted as a Bayesian posterior; exact source snapshots were not
preserved for it. The corrected pilot has matching source snapshots and seals.

## Validation and next experiment

The two new analysis components and report diagnostics have 31 passing tests.
The original Gaussian-sum component and 64-scan receipts remain unchanged.
The independent [audit](AUDIT.md) verified all 64 new seals, code/input/state
hashes, fresh priors, observation selection and exclusion rules. Exact test and
regeneration commands are in [VALIDATION.md](VALIDATION.md).

The next experiment should establish numerical convergence of broad spatial
acquisition before claiming localization improvement. A mass-preserving
coarsen-and-refine map or locally adaptive quadrature can spend resolution on
narrow spatial likelihood features. Shared nuisance integration must then be
restored before a matched 64-scan comparison. Separately, independently measure
likelihood coverage and background residual scales before adopting a robust
likelihood or tempering. Any replacement support check must quantify escaped
probability and preserve missing-catalogue safeguards; simply disabling the
existing checks would not validate these estimates.

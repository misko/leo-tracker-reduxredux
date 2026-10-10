# Conditional predictive sensitivity: preparation only

This is a source-based proposal, not a frozen experiment or an authorized run.
Synthetic unit tests have been executed, as recorded in README.md. No recording
evaluations or fits have been performed for it.
The standalone mean-position-error goal remains 0.4 km. No accuracy or
frequency-fit benefit is promised.

Iteration 158 exhausted the declared integration budget at all 24 endpoints
without meeting its target. That route stops under its protocol; this proposal
asks a different question rather than extending the integrator.

## Question and interpretation

Can parameters fitted to one subset of acquisition groups predict another
subset under the existing B7 likelihood? The minimal experiment tests
**conditional calibration consistency**. It cannot establish that a geometry
is correct merely because its held-group frequency likelihood is good.

The stronger question is whether held-group likelihood can distinguish
**alternative ordinary geometry hypotheses**. Answering that requires an
explicit, reference-free inventory of competing ordinary regions, with matched
training budgets and a sealed selection rule. A single geometry, or a single
joint fit initialized from the selected endpoint, does not answer it. No such
expanded experiment is proposed for execution here.

## Smallest proposed measurement

Use the same 12 consumed recordings and original selected observations as the
completed endpoint diagnostics. Form two complementary folds by a fixed seeded
hash of acquisition-group identity, without using frequencies, residuals,
satellite assignments, convergence or position errors to choose membership.
Freeze the seed and exact memberships before any fit.

An initial group contains all selected observations from one visit, including
both receivers. Merge groups transitively if their physical sample support
overlaps within the same recording and stream. Do not split the two receivers
using the existing receiver-specific `acquisition_id`. Missing support authority
must remain an explicit preparation failure; do not replace or silently omit
those observations. Every original row must occur in exactly one fold.

The public mapping is already available in
[the iteration 136 support adapter](../2026_10_10_position_error_iter136/adapter.py):
selected candidate and probe identities map to visit indices, receiver, stream,
device-sample boundaries, RF/channel and UTC support. These groups prevent
direct sample overlap across folds; they are **not statistically independent**.
Receiver drift, satellite errors and temporally correlated measurements can
span distinct visits.

For each complementary training fold, fit the two final c arms with identical
observations, bank, physical start, nuisance start, other priors and budgets,
apart from the static and time-dependent RF locks required by c = 0. The
proposed scope is 48 fits: 12 recordings × two folds × two arms, each with the
existing 90-second soft budget, 600 maximum iterations and independent 0.001
stationarity gate. This is a proposed cap, not authorization.

Score the opposite fold using those fitted parameters without any held-fold
clock correction, satellite-parameter update or optimizer. Recomputing mixture
responsibilities as part of evaluating the fixed predictive likelihood is
permitted; using them to update parameters is not. Report training likelihood,
training penalties and held likelihood separately. Held scores contain the
normalized observation likelihood, not another copy of the training priors.
Preserve all failed fits and incomplete coverage; do not introduce replacement
members or report fallback fits as successful training.

## Preserve the model across folds

The [clean public loader](../2026_10_09_position_error_iter131/inference_loader.py)
can provide the original observations and causal orbital input authority.
Construct the clock nodes, interpolation/nullspace basis, receiver design,
time/RF centering, satellite basis and prior precision once on the whole
recording. Slice rows of these fixed arrays for training and prediction. Do not
rebuild a subset model that changes its centers, clock support or gauge.

[DynamicRFObjective](../../src/leo/analysis/hard60_dynamic_rf.py) defines the
piecewise-linear clock interpolation and receiver RF-time columns;
[SatelliteCorrection](../../src/leo/analysis/hard60_satellite_correction.py)
defines the satellite slope basis and time centers. Training must evaluate only
the selected rows of the normalized mixture plus the unchanged priors once.
Subtracting a held score from a full-data objective is not a substitute for
preventing held rows from influencing gradients or nuisance fitting.

Describe held-time interpolation and any extrapolation separately. Sparse
training support can leave clock modes constrained mainly by their priors; this
is a limitation to report, not a reason to adjust folds after observing results.

## Conditioning and leakage limits

The proposed bank, starting state and retained region were selected using the
full recording. Moreover,
[B7 construction](../../src/leo/application/hard60_b7.py) computes satellite
time centers from full-data responsibilities. Preserving those centers keeps
the original model fixed, but conditions the diagnostic on held-data-informed
structure. This is consumed-data sensitivity, **not independent validation**,
and not an entirely training-only inference pipeline. Changing the centers to
training-only estimates would be a separately specified model experiment.

Do not infer additional leakage solely from the saved receiver baseline:
[receiver calibration](../../src/leo/analysis/regional_position_calibration.py)
constructs that baseline from the smooth knots, and `DynamicRFObjective`
subtracts the interpolated original knots when it introduces fitted clock
coefficients. In the genuine B7 chain these contributions cancel algebraically,
up to floating arithmetic. A future adapter should verify this source-bound
identity rather than assume either a learned fixed correction or exact zero.

Reference coordinates and position errors have no role in grouping, starts,
bank construction, fitting or predictive selection. Frequency prediction results
must remain separate from position accuracy. Any later localization assessment
requires a separately reviewed evaluation protocol; neither improved held
likelihood nor a positive result on these consumed recordings changes the
standalone positioning goal or establishes generalization.

## Preparation findings and remaining design decisions

`grouping.py` now implements whole-visit and true sample-overlap components;
it does not merge empty gaps merely because two intervals belong to one visit.
`rows.py` provides an explicit joint-only evaluation adapter. It exposes full
observation metadata to physical constraints and slices the likelihood's
observation and design rows without reconstructing the model. Unknown inherited
callable methods are refused. This is necessary because `_Problem` computes
timing support from observation min/max times; using a fold's times changes its
reported coverage margins. A subsequent source review clarified that the current
strict margin checks force every accepted `_Problem` to retain exactly +/-20
second timing limits: a larger accepted feasible range was not demonstrated.
Keeping full metadata still preserves the original constraint authority. A
subset's terms have fewer rows: any diagnostics must use
`selected_observations`, not the full metadata inventory exposed to constraints.

The proposed 48 fits above are not yet sufficient for a controlled before/after
comparison with fresh full-data fitting. Both c arms must start from one declared
common physical/nuisance state with only the required c locks differing, rather
than their separately selected original endpoints. One reference-free option is
the original zero-c endpoint as the common state. Adding a same-start, same-budget
full-data control would add 24 fits (72 total). This start/control policy remains
unfrozen; do not execute the smaller experiment and claim equivalent controls.
No outcome or reference-coordinate access is needed to decide it.

Before a recording run, require full source/input/runtime and fold-membership
binding, actual-model row-decomposition parity, original full-constraint parity,
explicit handling of incomplete support/empty folds, training-support reports
using the selected rows, and a fixed convergence/failure policy. An actual fit
budget, fold seed and criterion for advancing to geometry discrimination must
be reviewed and frozen. This source preparation authorizes no automatic fits.

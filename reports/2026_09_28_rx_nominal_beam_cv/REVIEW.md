# Independent review: nominal-beam leave-one-record-out design

## Design decision

The proposed six-fold calibration-record experiment is an appropriate diagnostic of whether one
predeclared nominal receiver projection transfers across recordings under the successful
short-horizon orbit-increment frequency kernel. D, E and B have dimensions 3, 4 and 4. D is nested
in both E and B at fourth coefficient zero; E and B are equal-capacity alternatives, not nested in
one another. `B - E` therefore compares two one-dimensional geometry summaries and must not be
described as an incremental beam term.

For receiver sign `s_r` under the provisional RX0-west/RX1-east convention, the B feature

```text
b_hir = cos(10 deg) * up_hi + s_r * sin(10 deg) * east_hi
```

is the dot product with the documented nominal boresight. Constraining its shared slope `eta >= 0`
tests the prespecified monotonic convention: greater nominal alignment cannot reduce modeled signal
probability. E uses centered `up` alone with the same nonnegative constraint, training-only RMS
scale and `N(0, 0.5^2)` penalty. This equalizes capacity and regularization. The mount orientation,
world tilt, phase centers and physical receiver mapping remain unmeasured or provisional, so B is a
nominal feature test rather than a calibrated antenna-response model.

## Isolation and preprocessing gates

For each omitted calibration record, physically build the training document from reception windows
of the other five records before fitting the background, feature scaler, orbit histories,
coefficient normalizers, occupancy or persistence. The omitted record and all held windows must be
absent from these operations. Persist exact five-record IDs and source-window IDs in each fold.

Center `up` and nominal projection separately for every `(lane, track, candidate, receiver)` using
that lane's reception forecast covariates. Carry the resulting offset unchanged into its held
windows. For the omitted record this may use its reception **forecast covariates**, because they are
known without detector outcomes; it must not use observed counts, frequencies, marks or held
covariates to choose the offset. Compute the shared feature RMS only from centered reception
features of the five training records, and apply that frozen value to the omitted record.

This centering removes every component that is constant over a lane/candidate/receiver reception
arc, including much of the absolute RX0/RX1 boresight separation. B consequently tests whether
within-arc changes in the nominal projection predict reception. It does not test absolute antenna
gain, absolute beam centers, a physical crossing time or static receiver offset. That limitation is
acceptable because it matches the earlier within-geometry convention, but it must remain explicit.

The orbit-increment target and causal reference must be constructed with the unchanged settings and
strict score-before-update history. Reception observations in the omitted record may condition its
held prediction after their own scores are recorded; they may not change fitted coefficients,
normalizers, background, bandwidths or hyperparameters.

## Fit and nesting requirements

Fit D/E/B independently with two deterministic starts. D uses the established neutral and nested-D
starts. E and B use the same neutral nuisance start and the selected D parameters extended by
`eta=0`; they receive identical beta priors, occupancy/log-tau priors, parameter bounds, optimizer
tolerances and null-selection rule. The fourth coefficient bound must be exactly `[0, 12]` in both
E and B, while their penalty remains half the squared coefficient divided by 0.5 squared. Record
boundary selection explicitly because `eta=0` is a scientifically meaningful nested result.

The likelihood, absent state, one-present-state approximation, background, shortlist priors,
visibility and causal history are identical across D/E/B. Only the fourth feature changes between E
and B. Calibration objective receipts should be independently recomputed, including MAP penalties
and the chosen start.

## Controls

Score every control on the same omitted-record windows with the selected B parameters frozen:

- **B swap:** flip the receiver sign in the east term while keeping receiver labels, offsets,
  observations and orbit frequency density unchanged.
- **Geometry reversal:** reverse only geometry covariates within each role and candidate; preserve
  observation order, actual time gaps, causal histories and orbital increments.
- **Candidate geometry permutation:** cyclically permute centered B feature trajectories among
  candidates while preserving frequency targets, priors, visibility and nuisance terms.
- **Zero/reversed orbital motion:** change only the orbit increment while preserving B geometry.

For swap, construct and center the swapped nominal feature under the same reception-only rule. Using
the original B center after flipping east can inject an unintended constant offset and would no
longer be a clean label control. Reversal preserves a role's mean by permutation, and candidate
permutation should operate after per-candidate centering. Runtime assertions should require that
swap/reversal/permutation leave the orbit signal ratios and causal reference unchanged, and that
zero/reversed motion leave B geometry unchanged.

## Outcomes and interpretation

The primary score is omitted-record held log predictive density, normalized within record and
averaged equally over the six folds. Report B-D, E-D and B-E with all six per-record signs. Also
report B relative to the causal reference and all controls. Reception scores are replay and
conditioning diagnostics, not a model-selection endpoint.

A useful nominal-beam result requires B to beat D and E, a positive fitted slope that transfers
across folds, and B to beat swap, reversal and candidate permutation on the same held population.
Passing zero/reversed-motion controls establishes the frequency mechanism, not beam geometry. If E
matches or beats B, the evidence supports a generic elevation relation rather than receiver-specific
nominal pointing. If B loses after centering, the experiment cannot distinguish lack of beam effect
from removal of an absolute receiver offset.

No DS8 result belongs in this stage. The six folds reuse calibration recordings for development and
uncertainty is limited to six recording clusters. Even a consistent result would support a frozen
nominal feature for a subsequent disjoint panel; it would not validate the 10-degree mount angle,
receiver cable mapping, satellite identity, geographic direction or localization accuracy.

## Source gate

The implementation follows the specified dimensions, common raw-up scale, nonnegative fourth
coefficient, identical E/B priors and bounds, and selected-D nesting.  The training document is
physically restricted to the other five records' reception windows before background, nuisance
scaler, causal history, beam scale, or fit construction.  The omitted record is prepared separately;
its reception forecast geometry supplies its per-nominee centering offset, which is then carried
into held scoring.  The swap implementation flips the sign after separately centering east and up;
by linearity this is exactly the same as centering the swapped projection and does not introduce the
constant-offset problem described above.

The component suite passed under the installed API (`10 passed`), and Ruff passed for both modules,
their tests, and the launcher.  Before freezing, the driver should strengthen its control assertions:
the geometry controls currently verify signal ratios and references but do not explicitly compare
visibility and priors, while the two motion controls do not explicitly compare their fourth geometry
feature with B.  The current construction appears to preserve these arrays, but the protocol states
these invariants as runtime requirements, so they should be enforced and covered before launch.

The first bounded fold attempt was correctly preserved and failed before fitting: the five-record
restricted document was passed to `prepare_families`, whose calibration-row validator still required
the six-record full-calibration cardinality.  This is an adapter validation defect, not a numerical
outcome.  A corrected attempt needs an explicit five-record preparation path (while retaining the
six-record default for full calibration), a real-chain regression, and a separately bound receipt.

That defect is resolved in the corrected source.  The fold now has a local preparation path that
calls the row validator with exactly five expected records, then fits the joint background and
nuisance scaler and prepares only that physically restricted reception document.  The full-
calibration helper retains its six-record default.  Runtime guards now also compare visibility and
nominee priors for every geometry control and compare the complete fourth feature for both motion
controls.  The focused installed-API suite passes (`12 passed`) and Ruff passes after these changes.
The failed first receipt remains an auditable pre-fit attempt and must not be overwritten.

## Independent outcome audit

The corrected six-fold run completed, and the independent audit is `pass`.  It reconstructs each
fold's exact five training sessions and source-window IDs, joint background, nuisance center and
scale, and raw-up beam scale from the frozen dataset.  Using the shared frozen preparation, kernel,
and likelihood code, it replays all 36 calibration objectives; it independently recomputes the MAP
penalties and selected-start comparisons.  All 36 starts converged.  For evaluation scores it does
not implement a second likelihood: it independently sums every exported per-window relative and
reference score into role totals and denominators, checks the common reference and window population
across all arms and controls, and forms the equal-record contrasts.  Its arithmetic agrees with
`results-summary.json` to rounding.

The reception result does not transfer to held frequency.  On reception, B minus E is
`+0.05235991` nats/window (6/6 positive), B minus D is `+0.07240301` (5/6), and B beats the nominee
permutation by `+0.05755724` (6/6).  On held frequency, B minus E is `-0.01726792` (2/6 positive),
B minus D is `-0.07759585` (2/6), B minus swap is `-0.04927866` (2/6), and B minus nominee
permutation is `-0.00180149` (3/6).  B beats geometry reversal by `+0.03754939`, but only 3/6
records are positive.  Thus no geometry-specific control pattern transfers consistently.

B remains above its causal frequency reference on held windows by `+0.08964633` nats/window, with
5/6 records positive.  Its margins over zero and reversed orbital motion are `+0.07742667` and
`+0.09204603`, each 5/6 positive.  Those comparisons support the already observed short-horizon
frequency mechanism; they do not rescue the nominal beam interpretation.  Every training fold
selects a positive E and B slope, yet held B loses to both D and E and to the swapped sign.  This is
the expected signature of a reception-associated geometry relation that does not provide the
required out-of-period specificity.

The nominal beam feature should not be promoted.  The result is compatible with reception-role
selection, detector-role changes, centering that removes absolute beam offsets, or an inaccurate
nominal pose/mapping, and it does not choose among them.  A next diagnostic should separate the
paired receiver amplitude/count response from frequency association on partial arcs and should
verify the physical receiver geometry before another directional model is treated as an identity
test.  The six records remain an explored development cohort, so these values are diagnostic rather
than fresh confirmation.

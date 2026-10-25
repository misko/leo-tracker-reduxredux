# Independent preflight and outcome audit

The original-parent checks pass. Scientific launch remains gated on the new
adapter's frozen inputs, protocol, construction tests and independent Gaussian
algebra audit, plus a separate coordinator go receipt.

## Original objective and inputs

`parent_audit.py` performed 72 fixed-position evaluations: two original saved
parent contexts and their two saved phase-only support controls, both c arms,
each at its saved endpoint and eight axial offsets of 0.05/0.5 km. Phase
references remained fixed. No position fit, phase refresh, IQ read or geographic
evaluation was performed. Position-fit entry points were explicitly blocked.

The actual optimizer scalar obeys

`||p.residual(x)||² - reported_ELBO(x) = fixed_noise_volume - normalization_constant + visibility_penalty(x)`.

The visibility term is the squared below-horizon residual for active curved
observations, with the original factor of one half. Predictive normalization
and covariance terms are included through the original predictive residual.
The maximum equation discrepancy is 7.28e-12; the maximum variation of the
visibility-adjusted offset within a fixed context is 1.10e-11. Thus these
contexts show no position-dependent optimizer/ELBO inconsistency. This does
not establish a global optimum or justify changing the objective.

Original saved endpoint objectives replay within the inherited absolute and
relative tolerances. Exact frozen scan-file/baseline hashes, original observation
ownership, causal catalogue epochs/collection times, historical phase inputs
and signed prior reconstruction pass. The target bindings retain native CFO,
graph values, time, RF, identity, alias and physical observation IDs. The 49
DS24-0095 and 43 DS24-0087 target IDs are unique and disjoint from every original
parent accepted/likelihood ID. Neither target is a protected active incumbent.

Receipts: `parent_audit.json`, `DS24-0095_target_binding.json`, and
`DS24-0087_target_binding.json`. The audit used one numerical thread and took
8.56 seconds. Its receipt explicitly does not approve scientific launch.

## Interpretation required for the new branches

The new target is a predictive factor, so it can move position while leaving
fixed-position parent calibration and Gamma estimates unchanged. This changes
its evidence role relative to the earlier active-curved support control. Only
the two new branches' mutual comparison isolates target shape covariance.
Preserving target prior uncertainty does not establish independently supported
orbit calibration or verified emitter identity. The ordinary graph control
retains its original failed support status. No geographic branch selector or
new accepted-association claim follows from a lower predictive score.

## Preflight findings on the first adapter draft

The independent phase check in `../math_audit/phase_linearization.json` finds
that first-order Gaussian phase uncertainty is inadequate for interpreting
this mechanism test. On 0095, at plus/minus one causal phase standard deviation,
the direct-minus-linear Doppler discrepancy remaining after removal of constant
and local phase directions is approximately 115–129 Hz, versus approximately
34 Hz projected shape-prior uncertainty. On 0087, approximately 1.42 Hz phase
linearization discrepancy also exceeds the approximately 0.855 Hz shape scale.
The Student prior is unbounded; 0095 has approximately 2.85% probability outside
the existing plus/minus 15-second physical domain. Silently truncating or
narrowing that prior would change the experiment.

Both independent reviewers therefore withhold launch approval for the
first-order phase adapter. A separately versioned direct-phase integration
requires explicit prior/domain semantics and numerical convergence checks
before any position fit. The original-parent audit above remains valid.

Source review also caught mutable cached-parent state in the draft adapter:
when no original predictive entries exist, the original curved calculation is
cached. Updating its returned dictionary in place would repeatedly append the
new factor and contaminate parent replay. The implementation owner changed
this to a fresh dictionary before updates and added repeated-position and
parent-before/after regression checks across both cases, arms and branches.
This was found before source freeze or scientific launch; no fit used that
draft. The new adapter tests and seals must demonstrate the corrected behavior.

## Nonlinear construction and numerical-decision checks

`preparation01_audit.json` verifies the preserved first preparation's exact
inputs and source hashes. An independent rerun of all nine construction tests
passes, including the cache regression. This approves construction only;
its receipt retains failed physical phase adequacy and prohibits launch.

`nonlinear_scalar_audit.json` checks 64 fixed positions across both cases,
c arms and covariance branches under amendment02. It verifies that the full
normalized target conditional mixture NLL enters the residual scalar exactly
once, while parent normalization remains unchanged. The maximum scalar identity
error is 7.28e-12 and visibility-adjusted offset variation is 1.46e-11. Repeated
evaluation and a 999 Hz target-value intervention leave original parent
coefficients, Gamma precisions, state phases and reference arrays unchanged.
All tested phase nodes and domain endpoints remain above 41.26 degrees.
This construction test uses 81 nodes and explicitly makes no quadrature-accuracy
claim; the integration rule is qualified separately.

`quadrature_preparation_audit.json` independently reconstructs every decision
from 160 per-position records and 32 center/branch gradient checks. The source,
protocol, amendment and input hashes match. Of the candidate rules below the
2561-node comparison rule, only 1281 passes every frozen criterion. At that
order, maximum score error is 6.08e-5 against adaptive integration and 4.97e-5
against the denser rule; maximum position-gradient error is 1.13e-4/9.81e-5
loss units per km, respectively. Prior mass error is 2.05e-13. Preparation took
137.54 seconds under the 600-second cap. Separate independent mathematical
evaluation and final endpoint qualification remain required before interpreting
new endpoints. None of these receipts authorizes a position fit.

`saved_control_reference.csv` copies 12 original control rows from the previous
publication's hash-verified tables. It includes the invalid ordinary graph
trials without relabeling them as qualified. No new geographic evaluation
occurred while preparing that table.

## Execution preflight

`preflight02.json` approves the narrowly bounded diagnostic protocol03,
SHA-256 `b57bba7dab4616866354b185cf6d6415ace6ba513da906f74e082b7b496ee137`.
The independent mathematical audit and coordinator go remain separate required
receipts. Source/input bindings, 88 fixed branch-position evaluations, at most
eight cold fits, two workers, one numerical thread each, 180 seconds per arm and
1200 seconds total are verified. Raw endpoints are checkpointed before final
numerical checks. Every final endpoint must pass the declared score/gradient
comparison under its final parent reference; failure cannot trigger a retry.

A second runner-level issue was found before any scientific run: execution02
checked clipped phase-reference convergence but omitted the original absolute
posterior-phase bound, along with some other original endpoint validity and
declared-file verification predicates. Execution03 reuses the exact original
`r.valid` single-arm predicates and verifies every declared binding. The
execution02 bytes and protocol remain preserved with zero runs; likelihood,
quadrature, input factors and budgets did not change. All seven repaired runner
tests pass independently, including four real baseline arm contexts and the
otherwise hidden absolute-phase violation.

The reporter explicitly removes every target ID from endpoint compatible
association coverage, even if the old postfit extension helper would re-admit
one. Experimental target likelihood counts remain separate. Both c arms and
both covariance branches retain the saved baseline as the operational output.

## Terminal RF and reporting audits

`terminal_audit.json` passes all 175 sealed-file bindings, 88 fixed profile
records, eight completed fits, raw/round/endpoint bookkeeping and four paired
qualifications. It reconstructs the normalized mixture objective from saved
node scores and weights at all 96 profile/endpoints, without propagation or
refitting. The reconstruction discrepancy is zero to stored precision.
Parent-only gates and exact original observation ownership remain preserved;
all experimental target IDs remain excluded from qualified associations.
The complete scientific run took 100.70 seconds, with arm runtimes between
17.98 and 25.97 seconds, and used no retry, rescue or additional candidate.

The separate mathematical terminal audit independently replays all eight final
parent-reference contexts, including 40 center/axis probes, with an alternate
adaptive phase integral and dense observation-space node oracle. Maximum score
and gradient errors including reference bounds are 1.90e-5 and 5.06e-5 per km;
the final endpoint quadrature qualifications all pass. Its receipt is
`../math_audit/terminal03_audit.json`.

Only after both terminal audits passed did `../evaluation/evaluate.py` read
the previously exposed same-site geographic reference. On 0095, retaining
physical covariance reduces diagnostic error from 1.6025 to 0.5869 km (c=0)
and 1.7823 to 0.5374 km (fitted c), but the saved baselines remain better at
0.3602 and 0.4386 km. On 0087, the two new branches differ by only 2.19/1.69 m
in their endpoints; retaining covariance changes error by +1.10/+0.58 m.
These are two examined cases with frozen hard identity/alias choices, not
new-location or identity validation. No target becomes operationally accepted.

`../evaluation/reporting_audit.json` independently verifies all eight new rows,
12 unchanged saved-control rows, four paired comparisons and 14 PNG/PDF files.
A unit-vector geographic-distance formula agrees with the reporter's
haversine formula within 3.97e-13 km. All 368 native-CFO plot-point identities
agree within 5.83e-11 Hz, and profile components close within 2.06e-11 objective
units. An initial reporting-check draft added the shared conditional mean twice
in its independent identity; the already-saved base residual includes that
subtraction. Correcting this audit equation did not change any scientific
output, geographic table or figure.

The two new branches isolate the full covariance of three physical modes.
Those modes include level and phase-like components as well as curvature.
The result does not establish that the approximately 34 Hz component orthogonal
to constant/phase directions alone causes the 0095 effect. CFO figures show
descriptive residuals before target-local constant/shape mean adjustments;
they are not whitened residuals, full-fit RMS or held-out predictions.

The read-only follow-up inventory found zero fully bound transfer-ready sources
in the other 22 scans. Its 97 provisional rejected graph bindings lack complete
archived both-arm accepted-ID ledgers including postfit-only extensions; none
was promoted into a screened recovery proposal or a new experiment.

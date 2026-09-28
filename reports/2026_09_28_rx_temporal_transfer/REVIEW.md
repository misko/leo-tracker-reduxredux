# Independent pre-fit review: temporal transfer of frozen fold models

## Decision

The proposed experiment is a valid no-refit diagnostic of how the six recording-held-out models
transfer from each omitted recording's reception segment to its later held-frequency segment. It
may proceed after the replay, source-binding and role-isolation gates below pass. No coefficient,
background, scaler, signal width, occupancy or persistence parameter may change.

The diagnostic can show whether predictive gains differ across the two temporal roles within the
same omitted recordings. It cannot uniquely attribute a difference to forecast age. Reception and
held-frequency windows also differ in role construction, detector outcomes, target intermittency,
nomination validity and possibly candidate-set composition.

## Frozen fold binding

For fold `k`, load only the checkpoint and result row whose held session is the omitted recording
assigned to `k`. Verify the checkpoint schema, dataset digest, five training sessions, held
session, source fingerprints and experiment seal against the original within-geometry CV launch
receipt. Recompute every source/input hash in that receipt before accepting the opaque seal.

Use the fold's saved joint background, feature center/scale and selected D/E/S/T beta, occupancy
and tau exactly. Sigma remains 500 Hz. Do not rerun optimization, choose between starts, widen the
tau bound, update the empirical reference, or recompute a scaler on six records.

Read only calibration lanes from the original dataset and retain their reception and
held-frequency windows. Reject evaluation lanes before accessing observation payloads. Preserve
source-window IDs, strict UTC ordering and actual elapsed time, especially the last-reception to
first-held gap. Start each exact lane at its frozen conditional nomination prior, filter reception,
carry the resulting state through the real boundary, and score each held window before consuming
its observation.

## Absolute and within features

Absolute features use the saved fold scaler without further transformation. For within features,
compute the standardized columns 3 through 7 mean separately for every omitted lane, nominee and
receiver using **reception forecasts only**, including invisible forecasts. Subtract that one
reception-derived offset from both reception and held-frequency rows. Leave columns 0 through 2
unchanged. This is an online-available transformation at the role boundary and differs
intentionally from centering with held covariates.

For a controlled geometry, transform the forecasts first and calculate that control's centering
offset from its controlled reception rows only. Swap uses the frozen sign reversal. Reverse uses
the frozen role-wise trajectory reversal, then reception-derived centering. The quarter-period
nomination shift changes predicted frequency but not geometry, so it retains the corresponding
base-family centering offset.

## Replay gate

Before reading a held-frequency score, reconstruct the completed cross-validation reception score.
For every fold, family and arm, require the reference score, relative score, full score, window
denominator and selected state to match the saved CV result with absolute tolerance at most
`1e-8`. Check each cell separately; a grand-total comparison is insufficient because errors could
cancel. The saved absolute and within D cells must remain exactly identical.

The replay establishes that adapter reconstruction, centering, time origin, nomination order and
state recursion are unchanged. Failure stops the run before reporting held results.

## Controls and reporting

Score base D/E/S/T and a fixed quarter-period nomination shift for every arm. Score T with the
fixed swap and reversal controls. No control may refit any quantity. Require identical source IDs
and denominators across arms and controls. Absolute and within D must remain identical for the base
and frequency-shift variants.

For each role, record and arm/control, report reference, relative and full log density with window
denominators. The comparable diagnostic is relative gain versus that role's fold-specific
reference in nats per window. Do not subtract raw absolute densities across roles because their
candidate counts, frequencies and denominators differ.

Aggregate six recordings equally and report signs for:

- each arm versus reference in reception and held frequency;
- E-minus-D, S-minus-D, S-minus-E and T-minus-S;
- T-minus-swap and T-minus-reverse;
- every arm minus its quarter-period shift;
- held-frequency minus reception for each relative contrast.

Keep reception and held scores visible separately. A paired role difference is descriptive and
must not become a selection criterion for changing the completed CV models.

## Required executable gates

1. Recompute and verify the complete original CV launch hash map and experiment seal, then verify
   checkpoint fold provenance and membership.
2. Require six distinct held recordings and an exact, unique partition of their reception and
   held-frequency source-window IDs.
3. Test cellwise CV reception replay within `1e-8`, including reference, relative/full score,
   denominator and state parameters.
4. Test reception-only centering, unchanged D columns, application of the same offset to held
   rows, invisible-forecast inclusion, and controlled-feature centering order.
5. Test the actual role-boundary time gap and score-before-update recursion against a scalar short
   sequence.
6. Require exact D-family equality for base and shifted forecasts, and equal denominators for every
   arm/control.
7. Perturb calibration held outcomes and require reception replay and all frozen parameters to
   remain unchanged. Perturb original evaluation/confirmation outcomes and require the entire
   result to remain unchanged.
8. Independently recompute every per-record mean, paired role difference, equal-record aggregate
   and sign count. Fail on nonfinite density or any partial record.

## Interpretation limit

A held-frequency decline with stable reception replay would establish temporal-role loss under
the frozen models. It would not identify forecast age as the cause. A stable held result would
show transfer across this particular boundary, while the same provisional pose, catalogue
ambiguity, mixed observational reference and reused historical corpus continue to limit physical
interpretation. This stage performs no model selection and cannot promote geometry or satellite
identity.

## Executable pre-launch review

The reviewed adapter reconstructs each omitted calibration record independently, prepares the
full reception-plus-held sequence with the saved scaler/reference, and calls the same forward
filter once per lane. This preserves the actual role-boundary gap, reception posterior carry and
score-before-update behavior. It computes within offsets from reception rows and applies them to
the complete sequence. Swap/reversal controls rebuild their own features before centering;
frequency shift leaves geometry unchanged. No optimizer is imported or invoked.

The launcher correctly recomputes every hash in the original CV launch map and its experiment
seal before freezing the CV result as a new input. Remaining pre-launch gates, several already in
the implementation handoff, are:

1. Require exactly six CV fold rows before constructing the held-session dictionary. Otherwise a
   duplicated held-session row could be overwritten while the six unique keys still match.
   Validate every fold's five training sessions, saved sigma, background row count and saved
   background hash.
2. Make reception replay cellwise for reference, relative and full score, denominator and selected
   state parameters; do not accept only relative and reference totals. Retain the `1e-8` bound.
3. Add sign counts and paired held-minus-reception results for all declared arm, nested and control
   contrasts, not only arm-versus-reference values.
4. Add regressions for controlled within centering and exact shifted-D identity. Clear the current
   Ruff import-order finding before source freeze.

No additional likelihood, centering, state-carry or control defect was found. Evaluation lanes are
filtered by split and session before observation payloads are copied. The source is ready once
these pending validations, focused installed tests and Ruff all pass. No real temporal score was
run during this review.

## Final source gate

The finalized source closes all four pending items above. It rejects anything other than six
unique folds, verifies each five-record training membership, requires the saved 500 Hz sigma, and
binds the empirical background mode, row count and content hash. Reception replay is checked per
cell for denominator, reference, relative and full density within `1e-8`. The earlier CV artifact
did not export filter posteriors, so this review makes no independent state-replay claim; the full
sequence call still carries the computed reception posterior across the real boundary gap.

The output now covers every declared arm and control comparison, their signs, and the paired
held-minus-reception differences. Runtime assertions enforce exact D equality between absolute
and within families for both base and shifted forecasts. Tests cover controlled-feature centering
and the fixed reception offset carried into held rows. The launcher also binds the CV results to
the completed evidence index in addition to checking its source hashes and experiment seal.

The focused six-test suite reported by the implementation review passes, and Ruff passes on the
runner, tests and launcher. I find no remaining source-level blocker to the bounded launch. This
gate does not include or imply a temporal-transfer outcome.

## Outcome review

The frozen run completed with exit code 0 in 11.03 seconds and 152,380 KiB maximum resident
memory. The current files named in `launch.json` reproduce every frozen launch digest, and the
result binds the expected dataset and completed CV-result digests. It contains six distinct
omitted-record folds.

Independent arithmetic from the exported per-fold role scores confirms the equal-record results.
For the within family on held-frequency windows, T-minus-D is `+0.0738496591` nats/window with
five of six records positive, and T-minus-S is `+0.0515368666` with four positive. However,
T-minus-swap is `+0.1317073663` with all six positive and T-minus-reverse is `+0.0317805570` with
all six positive. T itself beats the empirical reference by `+0.1245333662`, but only two of six
records are positive. The absolute-family held T-minus-reverse result is negative at
`-0.0154297710`. These controls and sign patterns do not support a blanket geometry enhancement,
receiver-tilt claim, or satellite-identity claim.

Within the same six omitted records and frozen fits, D-minus-reference falls from
`+3.7380661762` on reception to `+0.0506837071` on held-frequency windows. This is strong evidence
of role-boundary transfer loss for this fitted model. The experiment does not isolate its cause:
forecast horizon, detector role, target availability, intermittency, and nomination support all
change or may change across that boundary.

The independent audit helper initially rejected 75 derived record cells because it compared
floating-point dictionaries for exact equality. Recomputing those cells showed a maximum
discrepancy of `4.44e-16`, caused by subtraction order; exported means recompute within
`8.88e-16`, and all exported signs agree. The helper now applies a `1e-12` numeric tolerance and
the published audit passes without changing the source or results. It independently covers 1,356
reception and 1,363 held-frequency windows; its maximum posterior-normalization error is
`9.47e-16`, and it binds results digest
`7e32bb8f965d4286fa8e6a41f4dcc58df3680c518bb2630ae3ff2de4559ab8d8`.

The next bounded diagnostic should measure target-support alignment against forecast horizon:
report nomination support/abstention and predictive score by elapsed time from the reception
anchor, using these frozen folds and parameters. It must retain a reference/absence comparison
and the swap/reversal controls, avoid retuning bins or coefficients on later observations, and
keep horizon and detector-role interpretations separate where the existing schedule permits.

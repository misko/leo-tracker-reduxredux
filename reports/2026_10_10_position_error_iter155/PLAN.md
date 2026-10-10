# Actual-objective conditional-mode parity and cost preflight

Draft preparation only. No freeze, model evaluation, recording read, test,
quadrature, position stencil or optimizer run is authorized here. Iteration 154
is complete; its negative positioning result is not changed by this proposal.

Use all twelve members of the sealed 154 panel, uniformly selecting the
**control condition / native discovery** receipt, and inspect its original
selected endpoint in each final c arm. These 24 entries are consumed-data
development, not new validation. Historical 151 native parity is supporting
provenance, not permission to substitute an endpoint. Do not import either
experiment's evaluation summary, reference coordinates or error fields.

The goal is narrow: establish whether [152 ConditionalModes](../2026_10_10_position_error_iter152/conditional.py)
matches the actual final likelihood and is cheap enough to justify further work.
No integration, marginal score, profile optimum or localization improvement is
estimated. The eleven conditional synthetic tests have passed under parent
execution; that does not establish recording-model equivalence.

## Existing ports and reconstruction

Reuse the uniform public [131 InferenceLoader](../2026_10_09_position_error_iter131/inference_loader.py)
through the clean [151 inference binding](../2026_10_10_position_error_iter151/inference_binding.py).
These reconstruct original prepared observations, causal ephemeris bank and
prior with bound physical signatures. No IQ read or new acquisition is needed.
Bind the original observation content/order and both receivers, not just row
counts. The selected support remains unchanged.

[132 reconstruction](../2026_10_10_position_error_iter132/reconstruct.py) is a
useful constructor reference, but cannot be used blindly: it consumes a different
archive schema, assumes particular qualified stages, rederives pruning and
evaluates the dynamic model to calculate satellite centers. For this preflight,
prefer the values already persisted by
[run_joint_stages](../../src/leo/application/hard60_b7.py): each accepted B7
`joint_state` records centers, baseline, nodes, vector and clock state. The region
calibration records the original correction knots and receiver baseline. This
permits reuse of [137 construct](../2026_10_10_position_error_iter137/parity.py)
with a small explicit selection-schema projection and no preliminary objective
evaluation:

1. Locate the endpoint's selected `region_source`, `basin`, ordered satellites,
   accepted stage and full vector/clock state from its original control/native
   receipt. Bind the corresponding regional calibration and joint-stage receipts.
2. Project 154's top-level operation fields into 137's explicit
   `selection={accepted_stage,satellites,...}` plus `fit` schema; do not assume
   those layouts are identical. Construct `Hard60Objective` on exactly that
   satellite subset with the saved **final-model** receiver baseline, then
   `SlopePrior(base, nodes, zero_knots, saved_satellite_centers, 0.5)`, following
   137. Zero constructor knots avoid subtracting the original correction twice;
   saved clock coefficients, not constructor initial coefficients, define the
   evaluated state. An alternative using original regional baseline and original
   correction knots is algebraically consistent, but mixing the two conventions
   is not. Freeze one route, preferably the existing 137 implementation.
3. Before numerical calls, verify the constructed final baseline, clock design
   layout, precision, nodes and satellite centers against persisted state and
   source-defined expectations. Use the saved clock coefficients as the state;
   do not reinterpret saved fitted `clock_knots_hz` as original calibration knots.
4. If an arm selected an earlier fallback, has no selected endpoint, or lacks
   any required model-defining state, retain that entry as explicitly unsupported
   or missing. Do not force a B7 constructor onto another accepted model, silently
   substitute the other arm, or select a replacement member. A later extension
   to another stage would require a declared matching constructor.

The existing public inference loader and direct numerical constructors suffice;
do not call `run_joint_stages`, any fitter, a legacy reference-bearing loader or
the reporting/evaluation module. All reconstruction and failed admission cost
must be recorded separately from callback cost.

## Original physical feasibility and c-arm comparability

Independently audit the supplied endpoint's full physical constraints, exact
static/RF-time c locks, clock coefficient bounds and finite state before
ConditionalModes use. The local 25 km constraint must use the original joint-fit
seed as center, recovered from the frozen stage path: B5's qualified fitted state
if used, otherwise the declared B4W/B4 predecessor. Do not center the constraint
on the final endpoint merely to make it feasible. Operational `seed_audit` is
inherited regional metadata, not B7 seed-center authority. Record `_Problem`'s
private start projection delta, but audit and retain the original vector. A
nonzero helper delta alone is not a failure if the original is feasible.
Preserve original source-state
and stage identities. The first joint call supplies gradients for a separate
same-arm stationarity audit; no repair is performed on failure.

Original selected arms may have different banks or accepted fallback stages.
Record ordered bank IDs, observation signatures, calibration/baseline identity,
model stage, score/prior parameters and selected mode dimensions for **each** arm.
Report whether they actually match. An unmatched pair is still an honest parity
entry but cannot support a controlled c-effect comparison. This preflight makes
no such comparison even for matching pairs. Any future c-ablation must explicitly
freeze a common model/bank/observations/prior/support and matched start/budget;
it cannot infer matching from two labels in an operational receipt.

## Six deterministic joint calls per admitted endpoint

The initial ConditionalModes construction evaluates the original endpoint once.
Require absolute objective difference at most `1e-6` against both stored fit and
joint-state totals, finite physical/clock gradients and original lock parity.
No nuisance coefficient may change in this anchor call.

For each receiver choose the same prior-defined mode as 152. Define a symmetric
step from its original amplitude and exact feasible interval:

`h_r = min(0.001/sqrt(lambda), (a_r-lower_r)/4, (upper_r-a_r)/4)`.

Require finite `h_r >= 1e-6`; otherwise mark symmetric-check unsupported without
moving the anchor. This is a numerical geometry rule, not residual/position-error
tuning. One amplitude unit has the original coefficient's Hz units. Evaluate:

1. Original anchor: one call, already made by the constructor.
2. Receiver 0 at `a0 ± h0`, holding all else fixed: two calls.
3. Receiver 1 at `a1 ± h1`, holding all else fixed: two calls.
4. Both receivers at their positive step: one full-model call.

Use the symmetric differences to check anchor projected clock gradients. Check
the mixed-call additive identity against the two positive scalar differences.
Proposed fixed acceptance tolerances for review: additive identity `1e-6` NLL;
gradient discrepancy `<= 1e-5 + 1e-4*abs(anchor_gradient)` per receiver. Record
the actual discrepancy and step. These are numerical parity tests, not claims
that a derivative is globally valid across visibility or wrapping changes.
Inspect unchanged physical vector, other clock entries and the explicit inference
arrays: observations, bank orbital arrays, nodes, baseline, physical/clock design,
precision and satellite centers. Private evaluation caches are outside this
immutability claim. No shared inference state may mutate.

At most six full `evaluate_joint` calls per endpoint, or 144 across complete
coverage. Failed prerequisites consume fewer calls and remain visible. A future
protocol should impose a 30-second soft callback budget per endpoint, checked
before calls; in-flight work may overrun. Measure each call and total callback
wall time separately from input reconstruction. No adaptive extra probes,
automatic retries or coordinate selection from observed gradients are allowed.

## Binding and completion requirements

A later freezer must bind the published 154 protocol bytes and canonical receipt
digest separately; all twelve selected control/native terminal receipts; original
stage/calibration/selected state and seed provenance; clean inference projections;
public input/evidence/observation/bank identities; numerical source closure and
immutable 47e interpreter/native/dependency identities; and this fixed call policy.
Inference fields must be projected by an explicit allowlist, with no reference
or evaluation-module dependency. Original failed/unsupported entries are part of
membership, not a readiness filter.

All 24 entries must receive terminal receipts before any aggregate claim. Report
objective parity, feasibility/qualification, mode existence, actual c-pair model
matching, gradient/factorization discrepancies, failures and per-call/reconstruction
costs. No position errors or reference port is needed at any stage. If full-model
callbacks are expensive or parity fails, stop before quadrature. Only a separately
reviewed cached fixed-geometry likelihood adapter could then reduce cost while
preserving the same equations; this draft implements none.

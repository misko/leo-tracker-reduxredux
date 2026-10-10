# One bounded endpoint-integration diagnostic

Execution requires this protocol's source/input/runtime freeze to be published
before launch. Preserve immutable 155/156/157. Use the same twelve consumed recordings
and original 154 control/native selected endpoints as 155, both final c arms;
do not choose endpoints using errors, readiness or previous envelope behavior.
No references, position stencil, localization fitting or alternate prior modes.

The purpose is one bounded check of whether the existing conservative scalar
envelopes can resolve actual conditional integrals. Synthetic affine/Gaussian
checks passed, while the remote narrow peak exhausted its budget; neither result
predicts success on recordings. If the real cohort remains unresolved at the
declared cap, stop this lean integration route rather than expand the integrator.

## Minimal successor implementation

Reuse [155 reconstruction](../2026_10_10_position_error_iter155/reconstruction.py)
and its clean public-input/dependency ports. Keep original projected endpoint
authority, physical signatures, actual B7 seed-centered local constraints,
same-arm live KKT, exact clock locks and observation order. A new small `integrate_endpoint`
adapter should consume the reconstructed endpoint; a thin runner should reuse
155's member loader, dependency construction, fingerprints and append-only
claim policy rather than copy its numerical implementation. The new runner must
declare its own protocol and two-shard terminal receipts, not alter or resume
155 results. Preserve each arm's failures independently.

The freezer can inherit the exact 155 numerical/input/runtime identities and
add only the new source, policy and immutable 156/157 helper identities. Preserve
the original 155 result provenance separately; it is evidence of parity, not a
source of selected new nuisance states. All twelve members/24 arms remain in the
terminal inventory. No silent crash retry or fallback integral is allowed.

## Exact fixed-geometry inputs for the bounds

Require the production nearest-image branch: `0 < sigma_hz <= 1000`, positive
finite clutter rate, bank count greater than detection budget, and the same
source-defined alias period. A different likelihood branch is explicitly
unsupported, not approximated by these inequalities.

For the original endpoint compute physical satellite timing shifts from its
unchanged vector and call the existing `hard60_score.predict_orbits(...,
derivatives=False)` once to obtain the exact visibility mask. Do not infer
visibility from nonzero responsibilities, which can underflow or be small for
off-frequency candidates. This is one separately counted orbital call, not an
optimizer or an extra joint-value call. Geometry remains fixed throughout the
conditional integration; source-bound production joint callbacks recompute the
same geometry rather than a new approximate cache.

With `K=bank_count`, `q=detection_budget/K`, `b=clutter_rate/ALIAS_HZ`, and visible
count `V_i`, construct

`rho_i = V_i * q / ((1-q)*sigma*sqrt(2*pi)*b)`.

This is total visible peak density over positive clutter, including the existing
mixture weights. Conditioned detection normalization is amplitude-constant and
remains in the full objective; it is not discarded from the marginal score.
For receiver r use `d_i = clock_design[i, receiver_slice] @ direction` on its
rows, and the validated selected prior precision lambda. Obtain H/U from frozen
156 `curvature_bounds`. Each cell supplies frozen `seam_log_bound(d,rho,sigma,
ALIAS_HZ,half_width)`, including the conservative maximum crossings per component.
Keep finite logarithmic tiny-jump evidence; do not set mathematical jumps to
zero because production probabilities underflow.

## Callback, budget and result semantics

Start the 30-second soft endpoint deadline **before** model construction and
visibility/conditional setup. Public input and orbit-bank reconstruction is
recorded separately before this deadline. Check time before every objective or
orbital call and before other bounded stages. In-flight calls can overrun; retain
their complete measured cost. Do not present this as a hard wall-time cap.

Construct ConditionalModes once at the original endpoint, making one shared
anchor joint call. Check both stored objective authorities, original full-state
feasibility, c locks, actual anchor gradients/KKT and unchanged inference arrays.
No six-call derivative preflight is repeated: 155 established that callback path,
and a new mismatch or source/input change is a failed admission, not a refit.

For each receiver define the integrator callback as
`(L(a),L'(a))=(-scalar(a).difference,-scalar(a).gradient)` and use the complete
original finite amplitude interval. Invoke frozen157 once with maximum512 calls
and target log width `5e-5` for that receiver. Every value/gradient call, including
failed calls and discarded parent evaluations, counts. Frozen157 currently uses
one root plus two per split, hence can use at most511 calls under that cap.
The shared anchor is separate and explicit: at most1023 actual joint calls per
endpoint in the present algorithm (1025 if a future implementation used every
allowed scalar slot; such a change is outside this protocol).

The endpoint target requires both receivers' envelopes to meet their declared
targets and combined width at most `1e-4`. Combine normalized marginal score
bounds using the original anchor and lambda exactly once, as in152. If either
axis hits the shared deadline, exhausts its call budget, fails callback parity or
returns invalid bounds, preserve both axes' attempted/unattempted status and
retain the endpoint as unresolved. Do not turn a previously computed axis into a
complete endpoint. The other c arm still receives its own independent admission
and budget. Target attainment is a conservative numerical-envelope statement,
not rigorous floating-point certification or a position improvement.

Record source/input/model identities, per-axis H/U and seam policy, full finite
interval, calls, complete parent/child partition ledger, log bounds/widths,
original-state qualification, actual objective/orbit-call cost, fingerprint/audit
overhead and total endpoint/input reconstruction time. No conditional minimum,
integration-minus-profile correction or spatial ordering is inferred here.

## Potential blockers before a freeze

- The 155 loader currently constructs one physical case per member and one model
  per arm. The new timer must wrap model construction, not start only after it.
- An empty/ambiguous smooth mode, unsupported accepted stage or unmatched c-arm
  bank/model remains explicit. Recheck exact model/bank/prior/input matching as155;
  do not report controlled c effects if a pair differs.
- Actual callback cost is modest, but repeated fingerprinting and loose global
  curvature/seam bounds can dominate. Keep cost accounting honest and the fixed
  cap unchanged; no cache implementation is justified before this single trial.
- The integrator requires a callback exception to stop an in-progress axis. The
  endpoint adapter must preserve the resulting ledger and classify deadline
  exhaustion explicitly, rather than losing it in a broad outer exception.
- Freeze every numerical source, the projected original endpoints and runtime
  before recording work. Independent source review and synthetic adapter tests
  must establish sign, rho, per-axis call counting, prior normalization and full
  coverage/failure semantics first.

The endpoint adapter and thin orchestration are implemented. Nineteen synthetic
adapter/orchestration tests passed in 0.40 seconds under pinned47e, with all
numerical libraries single-threaded. Tests include actual adaptive integration
of an analytic Gaussian, prior normalization, hard call guards, nonfinite and
unsupported admission, deadline-ledger preservation, matching claims and orphan
claim refusal. Independent source review confirmed the visibility timing, mixture
bound, signs, normalization and two-receiver width gate. No recording execution
occurred before this freeze preparation. Completion/results will be reported in
a separate README, keeping this scientific protocol immutable.

The original155 protocol is bound by SHA256
`c713a3a4c33a422feedf73915aea1e3e236c7ed1daa6a85064ac0c5d7b79f292`.
Its source/input/runtime closure is inherited strictly; no mismatches are
rehash-approved. The twelve155 matched-pair parity receipts are also hash-bound.
The successor adds explicit numerical source files; later reporting code is
outside the frozen scientific closure. Existing terminal reuse requires a
matching claim and protocol; an orphan claim never authorizes a retry.

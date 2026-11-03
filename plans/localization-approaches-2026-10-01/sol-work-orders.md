# Dispatchable SOL work orders

Use `gpt-5.6-sol`, one coordinator plus at most three workers. Each agent first
reads the [main plan](README.md), [benchmark manifest](benchmark.json), repository
AGENTS.md instructions, and [model review](../../reports/2026_10_01_localization_model_review/README.md).
These are plans for later dispatch, not evidence that implementations exist.

## Common instruction for every worker

Implement only your assigned component and its owned tests. Preserve frozen
reports, numerical oracles, unrelated work, and public persisted contracts.
Use apply_patch for handwritten changes. Pure analysis cannot import storage,
HTTP, CLI, or database implementations. Communicate through the coordinator's
small evaluation protocol. No RF collection, raw-IQ campaign, QNAP mutation,
or unbounded benchmark. Never inspect evaluator coordinates for initialization,
model choice, or acceptance. Report assumptions, tests, changed files, remaining
limitations, and an exact bounded replay command in your handoff.

Do not independently launch real fits. Request a slot from the coordinator,
who enforces at most two fits globally, one numerical thread each, and one
bounded batch. Run synthetic/owned tests locally. No worker edits another's
owned module without an explicit coordinator handoff. A blocked interface is
resolved with a minimal synthetic stub, not a parallel competing interface.

## SOL 1: A1 and common physics evaluation

Own proposed new `src/leo/analysis/localization_evaluation.py`,
`src/leo/analysis/localization_fast.py`, and matching owned tests. Confirm paths
are free. Design the minimal immutable track/branch/state-facing interface with
the coordinator before other workers integrate. Preserve existing contracts;
the report adapter handles frozen input conversion.

Expose full normalized branch scoring and selected-branch prediction with an
explicit Jacobian request. Keep callable visibility/background priors correct.
Implement mean-only line searches, selected-satellite derivatives, state-safe
caching, and constant covariance-factor reuse. Preserve original hard-assignment
objective, priors, iteration caps, stopping rules, and budget policy.

Required handoff: protocol spec, differential numerical tests and tolerances,
background/boundary/cache invalidation tests, call-count instrumentation, and
source-bound three-scan replay command. Explain every objective/state/status
difference. No speed claim from a kernel alone. SOL 2 independently reviews
equivalence before official runs. After handoff, finish this task; a fresh SOL
agent who authored no admitted estimator or shared physics takes the verifier
slot. The coordinator freezes the final shared protocol signature.

## SOL 2: B1 soft joint association

Own proposed new `src/leo/analysis/localization_soft.py` and its tests. Develop
against a synthetic evaluation port while SOL 1 implements shared physics.
Implement full-catalogue per-track log-sum-exp with background, responsibilities,
Student-t generalized EM/IRLS steps, shared prior once, and line search against
the actual soft objective. Include state-dependent prior behavior explicitly.

Tests: exact enumeration, responsibility normalization/underflow, dominant-branch
limit, ambiguous and missing identities, outliers, shared timing, objective
descent, horizon changes, retained omitted mass and omitted-gradient bounds, duplicate-basin deduplication,
and distant-basin preservation. Three seeds only initially. No top-k
renormalization or raw objective-gap posterior probabilities.

Required handoff: objective derivation, approximation ledger, tests, default
working-set policy, deterministic bounded replay command, and outputs suitable
for common receipts. Integrate the reviewed common port, then review SOL 1's
equivalence tests. Real pilot fits only in coordinator-granted slots.

## SOL 3: C1 nuisance reduction

Own proposed new `src/leo/analysis/localization_profiled.py` and its tests.
Implement effective shifts d_s=τ+δ_s and their rank-one correlated prior,
profile/reconstruction maps, and a shared receiver-drift solve conditional on
nonlinear state and IRLS weights. Match A1's hard robust MAP objective, including
candidate/background prior normalization and original-coordinate convergence
diagnostics. Use all-catalogue semantics until nuisance exclusion is proven safe.

Tests: gauge invariance, dense prior oracle, profile-minimum equality, original
objective reconstruction, drift normal equations, shared covariance, inactive
nuisance treatment, and ill-conditioned cases. Preserve the original MAP prior
constant; normalized marginal evidence is a different objective. Do not claim
exact profiling or marginalization of Student-t drift terms: their quadratic
solve is an IRLS proposal. Gaussian integrated likelihood with determinant terms is a
separate model if explored at all.

Required handoff: derivation, exact-versus-approximate ledger, tests, conditioning
diagnostics, original-objective differential results, and bounded replay command.
If no pilot benefit appears, document the result instead of launching all 64.
After C1, D1 synthetic work may be assigned separately by the coordinator.

## Verifier: common benchmark and reporting

Use a fresh SOL agent who authored no admitted estimator or shared physics.
It does not change scientific fits while auditing them. Include SOL 2's A1
equivalence review as additional evidence. Read the separate evaluator bindings
provided by the coordinator; do not give evaluator files to fit workers.
Own only new experiment audit/evaluation/plot code and tests, under the
coordinator's agreed report directory.

Validate manifest authority hashes, exact 64 session IDs, source/config/seed
bindings, physical observation uniqueness, per-scan resets, prior/height and
orbit support, no fitted cross-scan state, receipt completeness, and timeout
accounting. Audit fit-side file accesses/configuration for reference-coordinate
use; shared-workspace interface separation is not a security guarantee.
Recompute sampled objective values and compare frozen numerical outcomes.

Freeze predictions before the evaluator reads reference coordinates. Publish
90 s and two-stage results separately, retain all 64 denominators and not-run
statuses, and preserve every failed attempt. Reproduce tables and figures from
receipts. Never select a worse converged mode to conceal an unresolved winner.
Only report posterior coverage for a properly defined distribution; fit scores
are not posterior probabilities.

Required handoff: audit JSON with every pass/failure, per-scan metrics CSV,
failure-inclusive figures, timing policy, complete reproduction commands, and
a concise recommendation with unresolved limitations. Audit failures require
coordinator review, not silent receipt or fixture repair.

## Later work order: D1 sequential mixture

Assign to a free SOL worker only after A/B gates. Own a separate pure module
and tests. Prototype completed-track updates using a small spatial hypothesis
bank, shared conditional nuisance state, predictive evidence, and explicit
mass accounting. Follow the ordering, eight-component cap, and acquisition
evidence-use requirements in the main plan.

Use a genuine prefix posterior followed only by later tracks, or an explicitly
offline batch optimizer. Never initialize data-centered Gaussian priors from
the whole scan and replay it as independent Bayesian evidence. Any importance
proposal requires an explicit density/selection correction.

First deliver a linear-Gaussian oracle, ambiguous-identity simulation, shared
clock test, order-permutation diagnostics, merge/prune accounting, and a proof
that acquisition/prefix observations enter once. Label offline full-scan
initialization separately from causal online inference. Only then propose the
three-scan replay and method-specific completion/approximation gates. The final
benchmark, if admitted, uses the same 64 scans and per-scan budgets.

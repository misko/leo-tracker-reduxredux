# A: solver-only phase-reference repair

Half-damped phase refresh closes all four DS26-0070/0309 c-arm fits under the existing 15-round budget. It repairs DS26-0070 phase nonclosure but leaves its position about 6 km from the evaluation site. This is a useful numerical repair, not a localization rescue or a new identity validation. No production code, ownership, catalogue, observation mask, noise model, likelihood power, or prior was changed.

| Case | Arm | Published error km | Legacy 15-round error km | Half-damped error km | Legacy phase gap s | Half-damped phase gap s | Half-damped rounds |
|---|---|---:|---:|---:|---:|---:|---:|
| DS26-0070 | c=0 | 7.269 | 7.597 | 6.223 | 0.447555 | 0.005339 | 4 |
| DS26-0070 | fitted c | 6.716 | 6.152 | 5.991 | 0.040821 | 0.002935 | 3 |
| DS26-0309 | c=0 | 3.162 | 3.162 | 3.162 | 0.001032 | 0.008479 | 4 |
| DS26-0309 | fitted c | 3.127 | 3.127 | 3.127 | 0.000124 | 0.000124 | 1 |

Both new DS26-0070 endpoints pass the base, exact-orbit replay, and mixture gates, with successful final position optimizers. All four new fits retain every fixed native identity and observation: 2,023 points for 0070 and 3,008 for 0309. The 0309 likelihood has 2,659 curved points plus 349 conditional/mixture predictive points. Per-arm `fixed_evidence.json` files independently verify the exact native-ID list and SHA-256 against the matched controls.

The inherited post-fit membership screen proposes another 485 points in 0070. These are **unadopted proposals** and never enter any fit here. It proposes no lost or reassigned published owners in either case. The published owner mapping remains immutable; `evidence_manifest.json` contains hashes of both the published mapping and the separate proposal mapping, so `unchanged_owner_mapping=false` in 0070 refers only to that proposal comparison.

## Model and solver audit

`JointMarginal.calculate` uses the absolute-phase linearization `f(reference) - f'(reference)*reference + f'(reference)*phase`. The standardized coefficient is **absolute phase / phase sigma**, and its fixed prior mean is **phase mean / phase sigma**. A new reference therefore needs no shift of this absolute-phase prior. Replacing it with a delta-phase prior without transforming the mean would change the model.

For nonlinear orbit geometry, changing the reference changes the frequency derivative and physical orbit-mode design. The resulting per-reference ELBO surfaces are **not mathematically invariant**, and their differences are not gains in one exact nonlinear marginal likelihood. No exact nonlinear phase profile or approximation-invariance claim is made here. The experiment changes only the fixed-point schedule: after the unchanged bounded position solve, refresh with `reference + 0.5 * (clip(posterior_phase, ±30 s) - reference)`. The closure check uses the **unclipped posterior/reference difference**, with tolerance 0.01 s. Damping has the same unclipped fixed points as legacy full refresh.

Each c arm and solver uses the same published fitted-c position and phase-reference start for its case, a 25 × 25 km regional position box centered at the pre-existing search center, and the same maximum 15 rounds, 35 L-BFGS iterations, 140 objective evaluations per position solve, tolerances, and line search policy. Early stopping is identical at the raw 0.01 s phase threshold. The saved published c=0 endpoints are separate historical baselines; the matched legacy and half-damped controls share the common start. The frozen archived legacy controls are reused rather than rerun. A quarter-damped alternative was preregistered only if either half-damped arm failed closure; that trigger did not occur, so the second variant was not executed.

In 0070 the final exact-versus-linearized orbit discrepancies shrink sharply while localization remains poor. The matched frequency fit changes are small: c=0 RMS 83.398 → 83.313 Hz and fitted-c RMS 83.235 → 83.225 Hz, legacy → half-damped. These improvements in residual fit do not establish position accuracy. In 0309, fitted-c is unchanged and half damping takes more evaluations to meet the c=0 phase tolerance than the already stable full refresh. This does not support applying damping indiscriminately as a speed optimization.

## Evidence and limits

The experiment has fixed identities and the causal TLE bank already sealed by composed ALGO06/ALGO07 reconstruction. It does not perform a new catalogue search, compare later TLEs, establish identity uniqueness, or supply held-group predictive validation. Those remain separate analyses. Every per-family exact replay replaces one family's orbital curve at a time with all fitted coefficients fixed and checks every surviving gate; it is not a simultaneous exact nonlinear refit. Base, exact, and mixture gate passes are conditional screening results, not complete production acceptance. The published optimizer status is unavailable as a comparable L-BFGS result and remains null in the table. The saved source optimizer history is under the prior diagnostics directory.

GPS enters only after `fit_without_truth.json` is written. It does not choose the start, identities, priors, damping, phase reference, objective, or endpoint. Results are reported for both c arms without selecting an arm by position error. No known-site grid was searched. The earlier 0070 NORAD 62320 omission result is outside this solver-only protocol and is not used as a default.

The protocol freezes the input JSON, source code, and common-start hashes before new scoring. The hashed input receipts carry the causal catalogue/bank and latest/previous TLE hashes; the per-arm runtime manifests additionally record the native observation export hash, prior means/sigmas, likelihood powers, and mask hash. The final report independently rebuilds endpoints and verifies native IDs. Native payload hashes are recorded during the run, rather than claimed to have been freshly computed before the protocol timestamp.

## Artifacts and reproduction

- [Frozen protocol](protocol.json), [full results CSV](results.csv), [JSON](results.json), and [round-by-round trajectory/cost CSV](trajectories.csv).
- [Phase closure and evaluation cost](figures/closure_and_cost.png), [frequency fit versus position error](figures/frequency_and_position.png), and [all fixed native residuals](figures/native_residuals.png). Residual colors distinguish satellite families; the exact IDs and NORAD values are in the prediction tables. These compact panels supplement the unchanged native context, polynomial audit, score panels, and nuisance-pull figures in `../../2026_11_02_algo07_top10_outliers/diagnostics/`.
- Dense native prediction/residual files `native_predictions.csv` and `native_predictions.json`, plus each arm's compact `native_fit.npz`, remain local with their hashes in the published artifact manifest. In the local CSV, `orbit_at_reference_hz` is nominal orbit at the linearization reference, **not** the exact fitted-phase orbit. Conditional/mixture raw CFO and orbital-only fields are null because those curves use different lifting contexts; the exact residual and native IDs are preserved.
- [Completion](completion.json), [artifact hashes](artifact_manifest.json), per-arm sealed `fit_without_truth.json`, final fits, fixed-evidence ledgers, and input/owner/prior manifests.

Run from `/srv/bulk/leo-dev/algo06-promotion-20261101` with Python `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python`, `PYTHONPATH=src:tools:reports/2026_11_02_family_reliability/solver`, and `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`.

```sh
python -m unittest discover -s reports/2026_11_02_family_reliability/solver -p 'test_solver.py' -v
python reports/2026_11_02_family_reliability/solver/run.py --case DS26-0070 --arm c0
python reports/2026_11_02_family_reliability/solver/run.py --case DS26-0070 --arm fitted_c
python reports/2026_11_02_family_reliability/solver/run.py --case DS26-0309 --arm c0
python reports/2026_11_02_family_reliability/solver/run.py --case DS26-0309 --arm fitted_c
python reports/2026_11_02_family_reliability/solver/report.py
```

The existing protocol must remain frozen; `--freeze` deliberately refuses to overwrite it. The reusable no-GPS API is `solver.fit(d, z, arm, variant='damped_half', start=..., reference=..., max_rounds=15, maxiter=35, maxfun=140)`. It honors `d['problem_factory']` via unchanged `e.build`, so the family-covariance prototype can compose with it. Four CPU tests pass: absolute-phase prior/reference consistency for affine geometry, explicit nonlinear noninvariance, stabilization of an oscillatory fixed point while retaining the actual fitted reference, and rejection of clipped-reference stagnation as closure.

The later [independent integration review](REVIEW.md) and [combined-evidence audit](combined_evidence_audit.py) cover the full curved+conditional-entry+phase-mixture native union at all 30 combined endpoints. The [0070](combined_evidence_audit_DS26-0070.json) and [0309](combined_evidence_audit_DS26-0309.json) audits pass, with two additional inventory/duplicate tests bringing the component total to six. The [publication manifest](publication_manifest.json) lists the reviewable artifacts; dense numerical outputs remain local and hashed.

The final [population receipt review](population_final_review.json) independently verifies all 205 sealed decisions, their source/input/worker bindings, 410 published case-arm rows, exact fallbacks, and accepted RF guards. Three additional receipt/guard tests bring the final component total to nine. The [review](REVIEW.md) distinguishes the 205-decision ledger from completed fits and documents inherited baseline-contract limitations and orchestration corrections.

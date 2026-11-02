# Independent frozen-protocol audit

**The frozen implementation and final RF decisions pass this audit.** All five cases remain **inconclusive** under the predeclared rule. Qualified partitions are DS26-0070 **0/5**, DS26-0309 **4/5**, DS26-0040 **3/5**, DS26-0044 **1/5**, and FRSH-0004 **3/5**. No failed, contradictory, or structurally unsupported cell was removed to obtain a preference. This does not establish that SD1 and SD4 are equivalent; the declared comparison cannot select between them on this challenge panel.

The protocol SHA-256 is `72be3047c7ca499931efbd6b680b71210444f9d66710a5725e25e28e131b01ff`. [Decision binding](decision_binding.json) verifies the frozen reducer hash, decision seal, input and conditioning RF-receipt hashes, all frozen source hashes, and exact equality between independently recomputed decisions and the parent's sealed `decisions.json`. No evaluation geography is used by these checks.

## Numerical replay

The [fixed-endpoint audit](final_audit.json), run by [final_audit.py](final_audit.py), independently reconstructs all **68 completed numerical cells**. It evaluates the sealed endpoints without optimization or phase refresh. It verifies:

- Training objectives against the last recorded fit objective, and raw phase/reference differences.
- Training-only Gamma counts, shapes, precision means and inverse-precision moments.
- The training-objective Hessian, position covariance, and all four training-only covariance-axis probe values and pass/fail flags.
- Conditional coefficient covariance, the derivative of the total training predictive mean, and normalized joint Gaussian densities for all/target/other held subsets.
- The bounded-box correction within that local Gaussian model and its numerical qualification.
- Exact native train/held hashes, fixed 150 Hz noise, unit powers, and omission of ancillary predictive likelihoods.

The maximum replay difference in bounded predictive score is **exactly zero**. All 100 individual cell files match their aggregate rows and protocol. The three random partitions and both directional transfer-support checks regenerate exactly from the real contexts, independent of CFO values. The 32 remaining cells are explicit structural-support exclusions, not failed or completed numerical fits. Execution used 140.24 seconds of the 600-second fitting window; all workers joined and no fitting deadline termination occurred. No numerical runner processes remain.

The final engine uses the same training objective, including its training-only horizon penalty, for fitting, local Hessian calculation and the covariance-axis probes. The Gamma inverse-moment formula is correct for the actual bound: `alpha=2+n_train/2` with unit powers, `E[1/tau]=alpha/[(alpha-1)*E[tau]]`, and unseen fragments use the prior inverse moment 2. Neither that correction nor the exact local-Gaussian box integral constitutes full integration of Gamma tails or the nonlinear phase/position posterior.

## Real-context held-outcome perturbation

The [leakage audit](leakage_audit.json), run by [leakage_audit.py](leakage_audit.py), covers **28 model/arm/split cells and 56 fixed-position evaluations**: the first randomized fold of each of the five real contexts, plus both eligible DS26-0309 receiver-transfer directions, for both SD models and both c arms.

It changes every held CFO by approximately 100,000 Hz in copied contexts, leaves the native identities/times/aliases/masks fixed, rebuilds the clean training problem, and compares the numerical result. Training objectives, coefficient and latent means, Gamma precisions, coefficient-prior precision, likelihood normalization, features, and convergence metadata remain **exactly unchanged**. Separate training-CFO perturbations change the objective in every cell, demonstrating that the modified observations reach the tested implementation rather than an ignored copy. The original contexts remain untouched. No optimizer, regional search, phase-reference iteration, or known-site evaluation is invoked by the audit.

Source inspection explains an otherwise suspicious intermediate: `JointMarginal.calculate` computes an all-row Gaussian intermediate, but the calibrated problem replaces the data-dependent posterior/objective fields with its training-subset bound. The actual training outputs do not inherit the intermediate's held-data fit. The real perturbation audit confirms this for the tested contexts and points; it is not a claim that the upstream full-data graph discovery is independent of held observations.

## Scope and limits

The receiver experiment withholds a **target-family × receiver cell**, retains that family on the other receiver, and retains other same-band families on the held receiver for hardware calibration. This is conditional cross-receiver family prediction, not transfer to a wholly uncalibrated receiver. Only DS26-0309 satisfies both predeclared directional support checks. The other four cases therefore cannot receive a model preference under the all-five-partition rule, regardless of their numerical time-fold scores.

The clean adapter uses regional-center/zero-reference starts and training-only coefficient/Gamma fitting. Fixed graph nomination, aliases, masks, identities, causal priors and nominal physical-mode support remain inherited conditioning inputs. The [pre-outcome design review](DESIGN_REVIEW.md) identified these limits before scoring. The five cases were selected for known previous localization contrasts, so the panel is explanatory rather than independent generalization evidence.

Predictive densities retain shared nuisance and local position covariance, use a bounded-box correction within that Gaussian approximation, and exclude boundary, floored-curvature, nonconverged, or locally nonquadratic fits from qualified votes. Residual short-time correlation and Gamma-mixture tails remain unintegrated. Marginal all/target/other scores are not additive because their uncertainties are shared. No predictive score or transformed weight should be called a calibrated identity probability, exact Bayes factor, or guarantee of improved localization.

No frozen inference source, prior, split, threshold, start, model roster, or decision rule was changed during this audit. The result supports the implementation's conditional train/held separation and honest abstention. It does not validate a production selector or establish a localization improvement.

## Reproduction

From the worktree root, with `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python`, `PYTHONPATH=src:tools`, and `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`:

```sh
python reports/2026_11_02_predictive_reliability/review/leakage_audit.py
python reports/2026_11_02_predictive_reliability/review/final_audit.py
python reports/2026_11_02_predictive_reliability/review/decision_binding.py
```

The first two commands rebuild existing contexts and evaluate frozen numerical models; they do not refit them. They require the recorded local input corpus. The final command checks the sealed decisions and audit bindings. A changed frozen source or input invalidates the audit rather than authorizing a silent rerun with new settings.

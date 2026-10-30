# ALGO03: causal predictive track recovery

**Current frozen candidate: `ALGO03-2026-10-30-r1`.** This release names the systematic annotation and predictive-inclusion work built on the production-equivalent ALGO02 causal-family reference. It is a research release for evaluation; the production service remains `algo02-causal-family-v1`.

The user requested promotion to the ALGO03 series on 2026-10-30. Earlier reports used “ALGO03” informally for [family-excluded satellite replacement](../2026_10_22_ds23_family_cavity_full_assessment/README.md). That work and its results remain unchanged. Use the explicit release identifier when distinguishing this predictive-recovery candidate from those historical experiments. Published ALGO02 contracts, golden fixtures and production outputs are unchanged.

## What is promoted

ALGO03 separates three questions: which satellite plausibly explains an unassociated curve, whether its prediction remains physically and statistically consistent, and whether several recovered curves can enter the same position fit together. It preserves ambiguous and rejected curves in an inventory instead of forcing every curve into a satellite label.

The frozen workflow adds:

- Predictive-only annotation of native graph curves, including those omitted from the calibration engine. The target does not calibrate receiver nuisance terms while its identity is assessed.
- Reproducible randomized physical-block validation with distinct held sets, seeded block origins and guards against nearby training observations.
- Broader causal satellite competition before inclusion; a lower RMS or a winning satellite alone does not establish sufficient identity separation.
- Matched control/addition position fits in both `c=0` and fitted-c, with exact physical-orbit replay, unchanged residual gates and observation-ownership checks.
- One-new-family phase integration, and an exact two-new-family joint likelihood retaining cross-family receiver covariance. Independently accepted additions are not silently summed into a combined scan result.
- Bounded numerical-only retries using matched Powell controls and additions. Physical failures, ambiguous identities and unsuccessful executions stay recorded.

The release freezes the implementation and evidence. It does **not** claim full-DS24 improvement, 90% association, or completion of the all-large-track inventory.

## Evidence at release

| Evidence | Result | Scope |
|---|---|---|
| Joint two-family recovery, AUTO-20cb1fdb | 58 points recovered; 67.91% → 69.00% associated | One studied fast scan; both c arms pass final checks |
| Joint position, c=0 | 0.493 → 0.413 km | Matched Powell control and addition |
| Joint position, fitted-c | 0.477 → 0.398 km | Same observations, candidate identities and budgets as c=0 |
| Latest inventory batch | 32 annotations; 19 position trials; 15 qualified curves / 399 points | Individual trials; 14 fast curves / 372 points and one adaptive curve / 27 points |
| Latest qualified position changes | 10 improve and 5 worsen fitted-c error | These trials do not establish joint cohort improvement |
| Full combined ALGO03 cohort | Not yet evaluated | Production promotion remains outstanding |

![Joint position comparison](../2026_10_30_joint_family_likelihood/figures/position_comparison.png)

![Recovered curves and residuals](../2026_10_30_joint_family_likelihood/figures/joint_curves.png)

See the [joint-likelihood report](../2026_10_30_joint_family_likelihood/README.md) for exact calculations, all original failures and retries, runtimes and numerical audits. See [batch five](../2026_10_30_shifted_annotation_batch5/README.md) for every annotation, individual inclusion, regression and residual plot. The latest comprehensive ledger is [here](../2026_10_30_joint_family_likelihood/annotation_ledger.csv).

The earlier 24-scan support-backoff result—mean fitted-c error 1.220 → 1.169 km—is a separate, narrower experiment. It is **not** the full ALGO03 benchmark. The [more aggressive recovery comparison](../2026_10_29_combined_family_reentry/README.md) and [eight-recording qualification](../2026_10_29_joint_attachment_promotion/README.md) demonstrate that additional associated points can worsen localization. Their results are not replaced by the positive joint example.

## Frozen execution definition

1. **Acquisition and GLRT.** Reuse qualified on-disk observations and acquisition provenance from the existing pipeline. Preserve physical receiver/channel, actual RF, sample rate, timing and original observation IDs. Polynomial samples are not new GLRT observations. This release introduces no new RF collection or sample-rate change.
2. **Graph and incumbent position.** Reuse the alias-aware graph and its recorded incumbent policy. The production reference is ALGO02 with causal signed phase priors and equal-prior family comparison. Research inventories can contain explicitly recorded preceding guarded-recovery policies; preserve that provenance and replay the supplied incumbent. Do not describe a guarded incumbent as an untouched ALGO02 baseline. Regional cold fits use a 25 × 25 km box centered at 37.906, -122.545 and start at its center.
3. **Inventory.** Enumerate native large unused curves and disjoint unused fragments with immutable IDs. Preserve partial ownership, previous assessments and acquisition mode. Rank eligible work by the frozen scope/point-count/ID policy, never by evaluation GPS error. Reconciled queues prevent duplicate work. `tools/run_annotation_inventory.py` owns bounded execution and immutable attempt receipts.
4. **Annotation.** Use `tools/annotate_predictive_only.py` in the intended predictive-only role. Randomize scanwide 12-second physical blocks with 2-second guards; choose seeded origins from timestamps only. Require at least eight training and four held target points and three distinct held-index sets. They overlap and are not three independent replications. Hold receiver calibration out of target fitting; include its uncertainty in prediction. Retain the existing identity-consensus and absolute predictive checks.
5. **Satellite competition.** `tools/review_annotation_competition.py` expands the causal geometry shortlist to a cap of twelve and replays original scores under the same observations, aliases, priors, training budgets and partitions. Actual candidate counts may be smaller. This is a bounded nomination search, not exhaustive full-catalogue marginal-likelihood evaluation. Require consistent identity and the existing margin threshold of ten across the recorded folds and c arms. Ambiguous, unstable or mismatched curves remain unassociated.
6. **Single-family inclusion.** `tools/run_predictive_queue_inclusions.py` routes supported identities to existing-family conditional inclusion or `tools/include_new_predictive_family.py`. New-family phase integration uses 0.025 s in the latest inventory series, the existing causal phase priors, physical orbital modes and 300 Hz fragment-bias prior. Targets enter as predictive evidence. Both c arms use matched observations, candidates, priors and budgets; final fits include all target observations.
7. **Joint inclusion.** For two distinct, independently qualified new families in one scan, `tools/fit_two_predictive_families.py` stacks their observation likelihoods. The base covariance is `blockdiag(N1,N2) + H Sigma H.T`, preserving shared receiver uncertainty; each satellite retains its independent causal phase prior and three physical orbit modes. Phase integration uses 0.0625 s with local 0.03125/0.015625 s audits in the current experiment. Compare against both the unchanged control and the factorized likelihood. This exact implementation supports two new families; arbitrary larger joint sets remain unqualified and must not be assembled by summing separate trials.
8. **Optimization and verification.** Use five phase-refresh rounds, 48 position iterations and nominal 240 function evaluations per round, with a 600-second execution cap per stage. Require optimizer completion, phase change ≤0.01 s, local integration agreement, small boundary mass, exact incumbent orbit replay and unchanged ownership. Target physical checks retain RMS ≤450 Hz, absolute bias ≤3,000 Hz, zero additional alias, nonnegative elevation and the existing mean/slope/curvature/step/autocorrelation gates. Check continuously refined phases as well as grid values. `tools/audit_two_predictive_families.py` performs the two-family replay.
9. **Numerical retries and fallback.** A numerical-only failure can trigger matched Powell controls/additions under the same 48-iteration/240-evaluation/five-round budget. It cannot waive a physical or identity failure. The two-family implementation is `tools/retry_two_family_positions.py`; the single-family selector is `tools/retry_predictive_numerical_failures.py`. If either c arm fails the final audit, retain the preceding qualified policy and keep the failed proposal in the ledger. Exclude incidental unscored post-fit extensions from reported recovery gains.
10. **Evaluation.** Report original-ID association counts, residual/likelihood effects and position accuracy separately. GPS 37.849061591561885, -122.48574968092912 is evaluation-only for the confirmed same-site recordings. No evaluation position selects satellites, partitions, priors, targets or accepted endpoints. TLEs after observation are excluded from inference. Preserve every tested scan and terminal execution outcome in cohort denominators.

## Reproduction and release identity

The [release manifest](releases/2026-10-30-r1/manifest.json) records implementation and test hashes, source baseline, entrypoints, data/evidence locations and qualification status. The Git commit containing that manifest pins the remaining repository dependencies. The scientific corpus is external to Git; its source digests and execution commands are retained in the linked reports' `sources.json` and compressed evidence archives. Those artifacts allow reproduction with the same local corpus; this is not a standalone data download.

Nineteen focused tests pass, covering the joint Gaussian oracle, physical single-phase projection, predictive likelihood, competition replay, phase-resolution checks and target membership scope. Full position experiments and final audits are complete for the reported pair. No public storage contract or production worker is changed by this release.

## Next qualification work

Continue the 274 remaining shifted-origin assessments and 821 older-role reassessments; these queues overlap. Test additional same-scan qualified recoveries jointly, then freeze a scan-level recovery policy and compare it with the production reference across a matched cohort. Include association coverage, mean/median/tail position error, runtime, execution failures and both c settings. Keep all regressions. This release is the named candidate for that work, not evidence that the full objective is already achieved.

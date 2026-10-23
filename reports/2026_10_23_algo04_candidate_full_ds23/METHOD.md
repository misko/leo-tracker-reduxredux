# ALGO04 candidate: frozen evaluation specification

This is a candidate, not a promoted ALGO release. It combines the existing whole-curve graph recovery and persistent native-GLRT recovery used in DBG01 iteration018. The rejected identity-conflict replacements, diagnostic phase-prior changes, receiver-step experiments and scan-specific GPS choices are excluded.

## Inputs and reference

Use all 410 available scans in the published DS23 family-cavity reference, with the original acquisition, GLRT winners, polynomial graph, noise estimates and causal catalogue. DS23 has 413 manifest members; 0012, 0184 and 0286 are unavailable. The inherited reference's strict-phase exception is retained and disclosed, rather than dropped from evaluation. Do not collect RF or reprocess IQ.

The reference is the published equal-assignment-prior family-cavity policy built on ALGO02/03. It is not the original unmodified ALGO02 baseline. The candidate uses no evaluation GPS for nomination, fitting or selection. It starts new fits at [0,0] in the 25×25 km region centered at 37.906, −122.545. All catalogue elements must satisfy both element-epoch and collection-time causality at that scan's cutoff.

## Frozen recovery sequence

1. Replay the reference objectives and gates. Construct its accepted original GLRT ID set. If the reference already fails the original qualification, retain and explicitly label it; do not silently make that case eligible by relaxing a gate.
2. Nominate the three longest wholly unused actively curved graph sources with at least12 points. Exclude partially used components and components already contributing calibration. Screen the full causal catalogue under receiver-calibration uncertainty; refine the best seven plus the original nominee. Linear sources do not calibrate offsets, drifts or orbital nuisance terms.
3. Cold-fit all nonempty combinations of the best qualified nominees and the original-identity single-source controls. Keep the existing Student/Gamma priors, alias requirements, visibility, residual-structure gates, phase bound and convergence checks. Use five phase-refresh rounds of48 position steps, with the existing near-feasible rescue when its unchanged trigger applies.
4. Apply the existing bounded support-aware model control to at most two otherwise failed proposals. Newly active one-owner families can lose unsupported orbital-shape coordinates; incumbent family definitions remain protected. Test one union of disjoint already valid additions when applicable. Select the valid graph result with maximum added curved points using the existing deterministic tie rules. Do not compare unnormalized objective values across different observation masks.
5. Require the selected graph result to retain every original accepted measurement ID in both c arms. If it loses one, keep the original graph parent. This membership guard is explicit and independent of geographic error.
6. Predict unused original GLRT winners from the frozen graph parent using the full shared calibration covariance and the numerically matching receiver basis. Search temporal paths with the existing five-second persistence HMM. Retain the independent-state search only as a control; it never replaces the primary because its GPS error happens to be smaller.
7. Retain the existing lane permutation control, candidate-versus-clutter penalty, ≥0.99 conditional identity requirement in both c arms, alias agreement, uncertainty limit, visibility, minimum8 points, minimum6 s duration, maximum10 s gap and maximum24 paths. These conditional probabilities are model scores, not empirically calibrated identity probabilities.
8. Gate complete paths once at the graph parent; do not prune individual residual outliers. Cold-refit the same selected paths in both c arms. New native paths remain predictive-only, including their shared covariance, and cannot recalibrate nuisance coefficients. Accept only if the original gates pass and every parent accepted ID survives. The existing near-feasible primary-path rescue uses five rounds of40 steps and unchanged slack thresholds. Otherwise keep the graph parent.
9. Independently replay accepted endpoint objectives, density calculations and original gates, and verify final association IDs. Preserve rejected proposals and explicit execution failures separately from valid unchanged fallbacks.

The graph parent may vary by scan, but the selection rule is identical. No scan-specific thresholds or truth-selected identities are introduced. Observations, candidates, aliases, other priors and optimization budgets are matched between c=0 and fitted-c for every hypothesis. RF-derived calibration coefficient c is the sole intended arm difference.

## Evaluation fixed before the full run

Report the reference, graph-only intermediate and final candidate on the same410 scans. Include all unchanged fallbacks. Explicit failures cannot be omitted or reported as scientifically accepted candidates. Separately show fast and adaptive formats, unique original GLRT association, fragment counts, frequency RMS and position accuracy.

Report mean, median, p90, p95, maximum and the number below0.5 km; paired per-scan changes; all regressions above500 m; the worst regressions and improvements; and empirical CDFs. Use chronological moving-block bootstrap intervals at10- and20-scan block lengths as sensitivity to dependence, not proof of independent samples or generalization to a new location.

Promotion requires completed valid numerical audits, improved mean and median in both c arms, no increase in either arm's p95 or worst error, and no individual regression above0.5 km in either arm. Uncertainty intervals inform confidence in any apparent gain. Increased GLRT association or a lower frequency residual alone cannot justify promotion.

DS23 has already informed substantial algorithm development. This full-population comparison is a regression/generalization check across its scans, not a blinded test or a new-location evaluation. A failed promotion criterion leaves the existing reference unchanged. Further changes require a new frozen candidate and an explicit report, not retuning this candidate after seeing its position errors.

## Execution and reproducibility

The driver and reused scientific sources are hashed in `protocol.json` before the full run. Two validation scans,0239 and0261, must reproduce the iteration018 endpoints and accepted IDs exactly.24 process workers run with one BLAS/OpenMP thread each; there are24 logical CPUs on this host. Results and checkpoints use bulk local storage because the root filesystem has no free capacity. QNAP is read-only.

Any implementation repair must preserve the failed attempt, state the narrow cause, retain the scientific policy, and record its own source hash. The empty-predictive audit adapter repair supplies empty slice/gate lists only when no predictive entries exist. It changes no likelihood, fit, gate or selection rule. Report execution time including retries separately from any deployment-speed claim.

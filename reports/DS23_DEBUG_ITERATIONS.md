# DS23 debug iterations and ALGO promotion

Continue from the existing ALGO02 and ALGO03 implementations. Each bounded
iteration selects the next **two** worst position-error scans from the latest
full-DS23 published benchmark, runs DBG01, examines unused GLRT evidence,
records hypotheses, prototypes and controlled results, and publishes an MD
report with figures and tables to remote main. Negative results are included.
Close a batch after its bounded tests; move to the next cases when progress
stalls. Revisit a closed case only for a new transferable hypothesis.

Aim for **90% supported original GLRT association**, while preserving noise,
structure, alias, visibility and physical-prior checks. Report graph-coverage
ceilings and unique measurement IDs. Do not force association or confuse a
better in-sample frequency fit with better position.

All inference uses causal TLEs, the original 25 × 25 km regional box, and no
evaluation GPS or manually selected identities. GPS may rank debug priorities
and evaluate frozen outcomes. Keep c=0 and fitted-c observations, candidates,
other priors and search budgets matched. A moving trajectory and stationary
history pooling are outside the current work.

| Iteration | Scans | Result and decision | Next batch |
| --- | --- | --- | --- |
| [001](2026_10_22_ds23_dbg01_iteration_001/README.md) | 0081, 0326 | Conditional calibration/support fixes recover 97 and 21 points; large boundary errors remain. No new ALGO release. | 0035, 0041 |
| [002](2026_10_22_ds23_dbg01_iteration_002/README.md) | 0035, 0041 | Recover 52 and 31 points; fitted-c errors become 3.741 and 2.835 km. A 30-point existing curved association enters position; conflicting shared-family merges remain rejected. No new ALGO release. | 0111, 0390 |

0405 remains in the full evaluation. It is skipped in the next **debug queue**
because prior DBG01 and bounded recovery controls already document its stalled
case; see the [full assessment](2026_10_22_ds23_family_cavity_full_assessment/README.md).
Queue order is not an evaluation exclusion or a change to its reported error.

New **ALGO series** versions are separate from debug-iteration reports. Promote
one only when improvements are credible across the **full DS23** population:
matched c arms and availability, mean/median/tail accuracy, GLRT coverage,
individual regressions, gate failures and computational cost. Report unavailable
scans and use comparable baselines; do not select a release using only the
inspected difficult cases. This replaces the earlier positive-only iteration
publication policy, while retaining a higher bar for an algorithm release.

Current full-population reference:
[410-scan family-replacement assessment](2026_10_22_ds23_family_cavity_full_assessment/README.md),
fitted-c mean **1.469461 km**, median **1.178102 km**. The mean-and-median
**0.5 km goal remains unmet**. These data are from the existing site; full-DS23
improvement alone does not establish generalization to other locations.

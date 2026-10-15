# A053 low-view repair and confirmed hard-visibility discontinuity

Four bounded repair trials produced no newly accepted CH1–4 endpoint. The accepted 0.190263 km incumbent remains selected, but its search is demonstrably incomplete: an unchanged-model feasible state scores 215.496518 better. The failed repair is now traced to a hard-visibility discontinuity involving a satellite with zero association responsibility, rather than ordinary floating-point stationarity error.

The four calls crossed two existing complete states (the fresh failed low endpoint and the current full endpoint) with two existing methods (SLSQP repeat and positive-tangent Newton polishing). All used the unchanged fitted-c, 59-satellite propensity model and original 50 km disk. Each allowed 20 seconds and at most 600 actual objective evaluations. The previous accepted low incumbent was requalified and retained. No failed source or scientific model was edited, and no reference was read until all four outcomes sealed.

| Initial state / method | Result | Actual objective calls | Complete fitting seconds |
| --- | --- | ---: | ---: |
| Failed low / SLSQP repeat | Evaluation cap exhausted; no accepted returned state | 600 | 2.827 |
| Failed low / PD polish | Outside near-stationary scope, KKT 0.898129 | 2 | 0.012 |
| Full / SLSQP repeat | Same rejected low endpoint, J 12871.457168, KKT 0.898129 | 446 | 2.144 |
| Full / PD polish | Outside near-stationary scope, KKT 585.122986 | 2 | 0.012 |

No threshold or polishing scope was relaxed. The old accepted low objective is 13086.953686. Repeating the full-state initialization exactly recovers the failed low endpoint, which motivates diagnosing the likelihood at that point instead of allocating another identical search budget.

The next zero-fit audit used 25 objective calls in 4.236 seconds, probing tangent-projected X, Y, the strongest physical gradient (common timing, coordinate 7), and the strongest nuisance gradient (coordinate 106). At X, the analytic scaled derivative is 0.213078, but central differences at steps 1e-4, 1e-5 and 1e-6 are -70.9221, -711.139 and -7113.305. The forward differences converge toward the analytic derivative; the opposite side crosses an approximately 0.014227 objective jump. Y and common timing show the same jump behavior. Nuisance coordinate 106 has analytic derivative -0.028576242 and matching central differences across all three scales. This is a discontinuity, not a smooth finite-difference mismatch that vanishes with a smaller step.

A separate three-point audit used three objective and three explicit orbit calls in 4.618 seconds. At a minus-X scaled step of 1e-6, satellite **48356** enters the visibility set for low-mask rows 16 and 17. Neither the center nor the plus-X point includes it. Its responsibility is exactly zero at all three points, but its visibility changes the conditional likelihood normalization. The center objective is 12871.457167744; plus-X gives 12871.457167961; minus-X gives 12871.471394570. The affected event-mass log terms each change from -1.219942840 to -1.230543177. Full window identifiers and posterior arrays are retained in the result artifact.

This establishes a concrete optimization/model interface problem: the smooth gradient conditions on a fixed visibility pattern, while the actual objective jumps at a visibility boundary even for an unassociated satellite. It explains this stalled endpoint, not the complete localization error or the accuracy of any alternative model. It is not grounds to accept the failed fit under a relaxed KKT threshold.

Next model alternatives are (1) a continuous visibility/detection probability with consistent physical derivatives, tested against exact hard-model limits away from the boundary, and (2) an explicit event-aware search that compares both sides and retains the original discrete likelihood. Either requires new scientific qualification and matched channel-view controls. No soft-model accuracy improvement is claimed yet.

Sources: `575b74b3f` (four-call control, two tests), `4e6964eed` (gradient audit, one test), `8bead8434` (visibility event audit, one test); Ruff passes. Evidence namespaces under `/srv/bulk/leo-research-ds21-ds22/2026_10_14`: `model-a053-low-repair-v1`, `model-a053-low-gradient-audit-v1`, and `model-a053-visibility-event-v1`. All outcomes are sealed, and the two diagnostics access no references or held observations.

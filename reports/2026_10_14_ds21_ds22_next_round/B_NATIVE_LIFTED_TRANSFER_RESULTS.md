# Audited receiver lifts in complete B-state transfer

Applying the separately audited receiver ambiguity integers before native-C refinement resolves the poor native scores of the direct, unlifted B transfer. Both new native endpoints are stationary and beat the previously tested native-clock basins on training objective. Neither case meets the localization target, and DS22-001 still moves away from B's configured-reference location.

This is a new prespecified experiment, not a retry or modification of the unlifted controls. Source `6a0b4d6e1` binds both original B training winners, the sealed unlifted pair, and the zero-fit alias audit. The only seed changes are receiver offsets by `(-1, +2) * ALIAS_HZ`; geography, c, slopes, group contrasts, common clocks, satellite timings and the original B disk remain unchanged. The old B likelihood is invariant under these two lifts. Exact original-vector/nuisance matching, ephemeris/evidence equality, calibration-function transport and audited lifted-objective replay are required before fitting.

| Case | Arm | Training objective | NLL | Independent KKT | Configured-reference distance, km |
|---|---|---:|---:|---:|---:|
| 001 | Lifted B repeat | 40400.444399 | 39952.540287 | 0.000811620 | 0.785018 |
| 001 | Lifted B → native C | 40240.278465 | 39854.588269 | 0.000125907 | 5.847635 |
| 019 | Lifted B repeat | 40936.599243 | 40336.216081 | 0.000500476 | 113.239176 |
| 019 | Lifted B → native C | 41212.351696 | 40654.720213 | 0.000138108 | 113.153762 |

B and C have different likelihoods; their objective values are not a common ranking. Within native C, 001 improves from the unlifted-transfer objective 50845.079211 and the previous best tested low-anchor objective 40896.026658 to 40240.278465. Its configured-reference distance improves over the old full C winner (21.266493 km) and previous native low-anchor result (6.928778 km), but remains worse than the original B winner. For 019, the new objective 41212.351696 beats the previous native-clock selected objective of approximately 41242.43; configured distance falls from that model's approximately 151.943 km to 113.153762 km. These are experimental basin controls, not a promoted production selection rule.

All four fits passed the unchanged independent stationarity test. Native paths used 339 actual evaluations/14.042 seconds for 001 and 265/6.714 seconds for 019, within the prespecified 20-second/600-actual-evaluation cap. SLSQP was already stationary; optional gradient finishing was unused. B repeats used 37 evaluations/0.265 seconds and 12/0.068 seconds under their original 20-second/600-iteration limits. Five component tests cover offset-only changes, complete state binding and invalid receiver/audit mutations.

The alias error was in the new direct B-to-C transfer experiment. The original C initialization already applies its own receiver lifts; this result does not identify a missing-lift bug in that original pipeline. The controls isolate the benefit of using the full B calibration and timing state with the correct native representative. They also show that even this better initialization leaves an objective-driven geographic difference on 001. A frequency-fit improvement alone is not proof of localization improvement.

Both case seals preceded reference parsing. The evaluator (`4fee35dbe`) rejects the unlifted protocol and incomplete pairs. The configured station reference remains unconfirmed, no reference-based endpoint selection occurred, and no held observations were used. Local evidence is in `local/ds22-b-lifted-transfer-v1` and `local/ds22-b-lifted-comparison-v1`; all original unlifted controls remain intact.

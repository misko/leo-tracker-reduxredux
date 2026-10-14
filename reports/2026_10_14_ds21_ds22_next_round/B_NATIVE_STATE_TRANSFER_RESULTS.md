# Complete B-state transfer into native C

The unchanged training-selected B-all state can be transported exactly into native C with B's common receiver clock model. Both cases reached stationary native-C endpoints, but those endpoints have substantially worse native training objectives than existing native-C solutions. This experiment does not justify replacing the training-selected model.

The prespecified cases are DS22-001 and DS22-019. Source `054001b5c` freezes both original sealed parents before fitting. Each paired control starts from the same complete B vector and nuisance state: geography, RF coefficient c, receiver offsets/slopes, common clock coefficients, receiver/group contrasts, and satellite timing. Both retain the original selected B disk of radius 25 km. No receiver ambiguity integer is changed. B uses its original 20-second/600-iteration fitter; native C uses a maximum of 20 seconds and 600 actual objective calls across SLSQP and the qualified optional gradient finish. No retries or acceptance-threshold changes occurred.

| Case | Arm | Training objective | NLL | Independent KKT | Configured-reference distance, km |
|---|---|---:|---:|---:|---:|
| 001 | B repeat | 40400.444399 | 39952.540287 | 0.000749640 | 0.785018 |
| 001 | Native C from B | 50845.079211 | 50546.339336 | 0.000134322 | 3.839507 |
| 019 | B repeat | 40936.599243 | 40336.216081 | 0.000480961 | 113.239176 |
| 019 | Native C from B | 48744.669864 | 48294.355001 | 0.000068393 | 114.119663 |

Objectives across B and C are different likelihoods and must not be compared as a common score. Within native C, the 001 transferred endpoint is worse than the previously stationary original-clock warm solution (41418.038343) and low-anchor solution (40896.026658). The 019 transferred endpoint is worse than its original six-start native-clock winner (41242.43). Thus a geographically closer stationary endpoint can still lose the native training ranking. The configured station reference remains unconfirmed; these distances are conditional comparisons, not verified accuracy. Both case seals existed before reference parsing, and there was no reference-based endpoint selection.

Native-C's complete numerical paths used 344 objective calls/15.065 seconds for 001 and 266 calls/6.908 seconds for 019. SLSQP itself returned stationary in both; the gradient finish was not invoked. B repeats used 26 evaluations/0.191 seconds and 20 evaluations/0.111 seconds. The two bounded case processes completed in 50.624 and 38.577 seconds, including authority and preparation.

Qualification checked the exact candidate ordering, timing basis, prior, score configuration, receiver design/baseline, group frame and precision, clock nodes/null basis/design, and coefficient ordering. The complete correction function replayed at native candidate times within 7.28e-12 Hz and 1.46e-11 Hz. Both B states were strictly feasible in their original disks without projection. A separately source-bound zero-fit supplement (`b4c415131`) verified exact orbit-node/position/velocity arrays and observation IDs/times/RF/receiver/channel/measured-frequency arrays for both cases. Six tests include same-ID ephemeris mutation rejection. The supplement preserves the original frozen experiment and does not repeat any numerical fit.

An unresolved distinction is the ambiguity representative: B's wrapped likelihood can treat receiver-offset shifts by an alias period as equivalent, while C scores finite native CFO branches. Exact calibration-function transport deliberately preserved the original representative; it did not make that representative optimal for C. A separate training-only receiver-integer lifting diagnostic is therefore warranted before attributing the poor native score entirely to continuous calibration or geography. No such lift has been retroactively applied to these results.

Local evidence: `local/ds22-b-native-transfer-v1`, `local/ds22-b-native-evidence-v1`, and `local/ds22-b-native-transfer-comparison-v1`. Evaluator source `0538fda3b` requires both complete pair seals before reading the configured reference. No held observations were used.

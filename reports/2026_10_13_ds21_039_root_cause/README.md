# DS21-039: four prioritized root-cause investigations

The user requested four parallel investigations of DS21-039, followed by full
DS21 evaluation, targeting **less than 0.5 km for every eligible CH1–8 recording**.
This is an acceptance target, not an achieved result. New experiments use fitted
`c` only, as explicitly requested; historical zero-`c` artifacts remain intact.

The original joint-model fitted-`c` errors were 3.759 km for CH1–4, 2.557 km for
CH5–8, and 4.291 km for CH1–8. These are historical reference joins, not inputs to
the following experiments. The half-band runs inherited all-training ambiguity
initialization, so they are not fully independent band-only pipelines.

## Priorities and ownership

| Priority | Investigation | Owner | Diagnostic question and deliverable |
| --- | --- | --- | --- |
| 1 | Optimization versus objective | SOL sequential agent | Replay the original training objective and profile all-band nuisance parameters at each of the three training-selected positions. Does a feasible better objective exist that the all-band optimizer missed, or does the objective itself prefer its current position? Return objective/prior decompositions, convergence checks, and matched-budget profile receipts. |
| 2 | Cross-band calibration and timing | SOL shape agent | Verify actual sky-RF Doppler scaling and receive-time clock correction; compare physical calibration functions on common native observations. Quantify confounding of fitted `c`, band contrasts, satellite timing and position, without treating centered coefficients as comparable physical offsets. Return residual structure, local rank diagnostics, and source-likelihood closure. |
| 3 | Satellite and ambiguity assignments | SOL joint agent | With the original candidate bank held fixed, separate geometry/timing changes from calibration changes in the satellite/native-candidate/sampling-integer posterior. Return paired-band factorial comparisons, clutter and visibility accounting, and candidate inventory losses. Posterior occupancy is not confirmed satellite identity. |
| 4 | Observation weighting and correlation | Root integration slot | Identify bands, receivers and acquisition blocks that dominate the objective. Evaluate predetermined equal-band and equal-block weighting at frozen states using the same per-window likelihood port. Return support concentration and sensitivity; window counts are not an estimate of independent information. |

Three SOL workers run concurrently; root owns direction 4 and integration because
the workspace has four execution slots. Each worker implements component-owned
synthetic tests and debugs its diagnostic before the common DS21 run.

## Shared controls

`inputs-v1.json` binds the original recording, development membership, observation
partition, native bank, original six starts, receiver ambiguity initialization,
and all 18 historical fitted-`c` attempt receipts. The training-selected winner is
start 5 in each view. Inventory creation performs no inference or optimization.

The initial stage uses the original training observations and zero new optimizer
calls. Source snapshots and execution budgets are frozen before numerical replay.
Historical terminal bytes are hashed without using their position-error joins.
The current loader verifies the original prepared-evidence hashes; historical
source coverage is explicitly limited to the files archived by that experiment.
Saved-objective replay is therefore required before interpreting new diagnostics.

Direction 1's subsequent profile stage uses the original six all-band physical
starts at each training-selected position, changing position only. It retains
the same likelihood, bank, priors and fitted-`c` treatment. The bounded slice is
18 fits at 20 seconds / 600 iterations each, with no reference-derived seeds.
Boundary or nonstationary outcomes cannot establish a profiled optimum.

None of these diagnostics establishes improved localization merely by improving
frequency fit. Position errors are joined only after results are sealed.

## Path to full DS21 and the 0.5 km target

1. Complete the four diagnostics on DS21-039 and record the evidence for or
   against each suspected cause. Implement narrowly supported fixes, with
   component tests and paired original/fixed receipts.
2. Run fixes on the existing five development cases, then all 34 fast CH1–8
   development recordings. Keep observation partitions, causal catalogue access,
   candidate budgets and search budgets matched when comparing models. Include
   matched CH1–4 and CH5–8 results where evaluating the effect of combination.
3. Select and freeze one release using development evidence. Only then evaluate
   the 20 locked fast CH1–8 recordings. Do not tune per recording or use reference
   positions to choose seeds, satellite associations, calibration or winners.
4. Report all 54 fast recordings: per-recording error, median, upper quantiles,
   maximum, count below 0.5 km, and every failed/invalid fit. A failure is a miss.
   Report frequency-fit effects separately. The 54 adaptive CH1–4 recordings form
   a separate coverage/performance table; they cannot satisfy a CH1–8 target.

The immutable DS21 acquisition-hour split and the reviewed DS21-065 preparation
exception remain authoritative. Full DS21 has 108 recordings. Accuracy is measured
against the configured reference; it is not independently surveyed ground truth.
If any eligible CH1–8 recording misses 0.5 km, report that honestly and identify
the remaining failure mode. Evaluation reuse after a failed locked release must
be disclosed; it cannot be presented as a fresh untouched validation.

No new RF collection, production-default change, or multi-hour unattended campaign
is part of this investigation. Work proceeds in bounded, inspectable slices.

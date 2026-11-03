# Position pilot using availability-correct acquisition calibration

Freeze one original and, where available, one additional recording for each
passing family: choose the smallest plan index, without consulting errors.
Original (family,index): (2,0),(3,18),(4,21),(5,2),(6,1),(7,5).
Additional: (2,1),(3,2),(4,0),(6,5),(7,3). Family 5 has no additional record.
Families 0/1 remain unvalidated and outside this prerequisite pilot, not outside
the full DS11 objective. All previous results remain unchanged.

Use exact whole-source assignment with the verified accelerated DP, all original
candidate identities, separate per-track CFO, original causal orbit banks,
fixed zero height and original observation/visit masks. Rebuild public observation
joins and verify raw time, CFO, visit, receiver, RF and candidate-bank identities.
Use each family's newly qualified receiver calibration without tuning its weight.
RX0 is west and RX1 east, nominal outward tilt 10 degrees; no hard sky-sector gate.

Stage A has 22 cells: Doppler-only and signed geometry for each recording.
Seed from the original IID solution. Bounds are EN ±12 km and time ±5 s.
L-BFGS-B: maxiter100, ftol1e-15, gtol1e-5; the tighter ftol addresses earlier
premature stops, with unchanged qualification: success, bound margin ≥0.001,
raw gradient ≤0.01 and finite-difference discrepancy ≤0.02. Before optimization,
verify full exact versus collapsed Doppler partition and signed derivatives on
original 0. Each child ≤90 seconds, at most three single-thread workers; retain
every timeout and unqualified fit. No score-based pruning or selective retries.

Seal every terminal receipt before reading reference errors. Report original
IID, refitted Doppler and signed estimates, qualification, held likelihood and
runtime. Stage A passes only if all cells qualify and, separately in each
cohort, signed reduces median by ≥5%, wins strictly more than half of records,
and does not increase P90 relative to both original IID and refitted Doppler.
No missing/failed cell may be dropped. Passing is required before adding
receiver-only/swap/permutation positioning controls and the remaining eligible
records. A failed pilot ends this fixed model variant, not the overall goal.

This remains a conditional nonempty-state model with inferred satellite labels,
not a calibrated absence/clutter/activity model. The roof reference is not
surveyed, the original benchmark has been repeatedly examined, and additional
records share the site. No claimed deployment validation follows from this pilot.

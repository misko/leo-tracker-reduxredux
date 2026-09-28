# Frozen temporal-transfer comparison

Selection: the last chronological DS7 group, `group8-11`, plus its eight
single-recording fits (`single-081` through `single-088`). This selection uses
only the existing chronological partition, with no new group predictions or
reference scores. Preserve unavailable members; never shrink a group.

Run the unchanged `config/ds7/baseline-wave2-ready-v1.json`; the authoritative
comparison arm is the exact copied `arm.json` from
`reports/2026_09_27_ds7_wave2/solver/first8-panel-v1`. It binds the fast baseline
implementation and the original scientific configuration. Verify current code
against that run's recorded hashes before launch. The input index must retain
all 88 source identities and separately record readiness.

Budget: at most 900 adapter seconds in total and 300 seconds per unit, one CPU
and BLAS thread, nice 19. Exact unit selectors are mandatory. No optimizer,
prior, candidate, masking, RMS or starting-value changes. Input preparation
has a separate bounded lease in `LAUNCH.md`.

After independent predictions seal, apply the three unchanged wave-2 controls:
equal mean, inverse training-RMS-squared mean, and lowest-RMS 75% mean. Use all
eight members, qualified upstream estimates, and the same training-only RMS
definition. Each aggregation receives at most ten seconds. Seal predictions
before reference scoring. Report all selected units, unavailable/failed runs,
convergence/boundaries, and errors against the same unsurveyed operator
reference. Do not select or reweight a method using the group's reference
distance.

This comparison tests temporal transfer of the frozen model. It is not a full
88-recording estimate and cannot by itself satisfy the complete DS7 goal.

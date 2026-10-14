# C019 paired native clock and search coverage control

The original six 25 km search disks all exclude the configured, unconfirmed DS22 reference. This retrospective diagnostic motivates a reference-independent coverage control: retain every original 100 km coarse grid point, not a reference-selected subset. The sixteen centers have east/north coordinates in {-150, -50, 50, 150} km. Radius 100√2 km disks cover the original 250 km prior's bounding square. The original global prior remains enforced.

The fixed candidate bank contains the original 36 satellites plus every candidate from all sixteen coarse fits: 67 total. All candidates and all starting states are frozen before optimization. The experiment compares the original native model with a native receiver-common-clock extension. Both use fitted c, the same observations, candidate bank, original calibration frame, group priors and timing limits. No locked samples enter.

Each arm receives six original full-band endpoint controls in their original 25 km disks and sixteen coarse initializers in the expanded disks: 44 new fits. Each fit has the same 20 second/600 iteration budget and strict independently replayed KKT threshold 0.001. Each arm has two separate training-objective selectors: its original six controls and its full twenty-two starts. Objectives are never compared across the two model families. All 44 outcomes must seal before configured-reference reporting, including rejected outcomes.

For coarse initializers, source calibration is projected into the no-clock arm and exactly retained in the clock arm. Both use the same source-derived receiver ambiguity integers and orbital timings; added satellites receive the source common timing shift. Clock projection residuals are explicit. The original fitter's at-most 1.1 ns inward timing normalization is recorded rather than hidden. Six original native controls undergo exact physical transport, without projection or a second receiver lift; their clock extension starts at zero.

Qualification completed before localization:

- Sixteen coarse pairs: 96 objective evaluations, 16 bounded calibration projections, 64 explicit orbital predictions, zero localization fits. Maximum exact-clock physical correction discrepancy was 1.1642e-10 Hz.
- Six original control pairs: 24 objective evaluations, 12 explicit orbital predictions, zero projections or localization fits, 46.493 seconds. Zero-clock objective, likelihood, physical/group gradient and posterior closure errors were exactly zero. Preserved-candidate orbital discrepancies were at most 7.422e-10; calibration discrepancy was zero.

Pilot source: `11d198169`; reporting source: `cd39684e8`; shared original-control transport: `779f50cb3`. Pilot and transport tests passed (five tests), reporting pre-seal guard passed (one test), and Ruff passed. The frozen protocol contains the full source snapshots and parent bindings.

Scientific output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-coverage-pilot-v1`. Six single-thread workers process bounded paired units (120 second internal, 135 second TERM, 140 second KILL). Other services retain capacity. The fixed per-fit wall budget can affect convergence; CPU and wall durations are saved separately. No failed outcomes are silently retried.

This is a development experiment on a repeatedly examined case. DS22 reference coordinates remain unconfirmed; any eventual distance is a configured-reference distance, not verified localization accuracy. Original cohort histograms exclude this pilot.

# Noise-gated position search checkpoint

This goal turn made concrete progress: residual-aware evidence now governs
accepted parameter updates and geographic state ranking, with component tests,
four actual independent-position searches, four matched legacy controls, four
separate known-position diagnostics and frozen-state conditional nulls.

All bounded jobs completed; no RF collection or QNAP write occurred. No new
commit/push was performed. The larger satellite association / <0.5 km goal is
active and unachieved. Only DS22-001 and DSX01-S01 were searched this iteration.

## Authoritative outcomes

| Dataset | c arm | Legacy error km | New error km | New associated points | Merged tracks |
|---|---|---:|---:|---:|---:|
| DSX01-S01 | c0 | 11.967868 | 8.367140 | 2490 | 70 |
| DSX01-S01 | fitted_c | 11.967868 | 8.501465 | 2509 | 91 |
| DS22-001 | c0 | 12.923668 | 3.241090 | 1632 | 50 |
| DS22-001 | fitted_c | 12.923668 | 1.894662 | 1602 | 47 |

These are resumed blind local searches from previous sealed c0 estimates, not
cold/global convergence. Paired c arms share original measurements, causal banks,
all priors except c's existence, initial position and eight hardware values,
geographic/legacy-generated-seed caps. The new method performs extra feasible
updates. Common final candidate-after-gates association and pooled/member merger
checks are used for both methods. All original Graph IDs are accounted for.

Only individually measured-curved fragments rank or update hardware, phase or
position. Linear tracks can associate after curved support. Every accepted
tangent update improves the noise-gated score; exact nonlinear geometry selects
the final endpoint from three finalists. Original robust background retained.

Actual / randomized-intercept median curved points: S01 c0 1519 / 42,
S01 fc 1522 / 52.5, DS22 c0 1123 / 25, DS22 fc 1086 / 25. Sixteen frozen-state
nulls per arm preserve centered shape/times/RF and use identical random draws
between c arms. They are not reoptimized null searches or calibrated FDR.

The new c arms assign identical NORADs to every shared associated ID (S01 2334,
DS22 1567), despite different coverage and estimated positions. Compared with
legacy, S01 changes 61 shared point labels in each arm; DS22 changes zero.

## Important unresolved discrepancy

All four new wrong-position endpoints score better than both tested fixed-GPS
parameter initializations. Known GPS is only used after saving immutable blind
endpoints. Those diagnostics are in `known_position_diagnostic/`, never search
initializers. This is evidence that residual checks alone have not solved the
remaining model/criterion/parameter-proposal problem. It does not prove that
every possible GPS state is worse. Do not claim authenticated identities,
global convergence, full-corpus validation or sub-0.5 km success.

Next useful bounded diagnostic: keep each saved blind family/NORAD assignment
fixed, transfer to supplied GPS and refit only allowed shared hardware/phase
parameters using measured-curved members. Compare residual gates, phase bounds
and score against the same family's blind fit. This can distinguish an optimizer
proposal problem from incompatible families or missing frequency physics.
Keep this diagnostic separate from independent location results. Cross-scan
shared-satellite constraints may help after this discrepancy is understood.

## Artifacts and validation

README.md contains all tables, score-at-GPS comparisons and limitations.
comparison.png separates error, coverage and points per merged track.
track_associations.png displays all original Graph observations, colors by
candidate NORAD and grey unassociated points. merged_track_rms.json records
RMS/members/point count for every merged track; all 456 groups across eight
arms pass the saved residual check, maximum pooled RMS 240.57 Hz.

Thirty-five focused tests and changed-file Ruff checks pass. Sources are
snapshotted with a manifest; original bank, partition, seed, source-track and
known-position diagnostic inputs are bound in input_lineage.json. The missing
durable S01 selected TLE payload was archived from the verified causal cache;
its hash matches the already-frozen bank receipt. Earlier 260-file repair
report seal was verified unchanged. New report seal binds completed artifacts.

All process handles were polled terminal: new 88213/54296/39501/52587,
controls 68155/46740/44174/32901, GPS-only diagnostics
87012/56660/73574/78430, smoke 85966, render 37648/11423 and all tests.

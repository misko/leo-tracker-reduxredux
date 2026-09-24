# DS1 frozen inventory and comparison guardrails

DS1 is the whole-group frozen long-duration cohort in
`2026_09_23_long_inventory_complete/manifest.json` (SHA-256
`06818537a82a771e25bb71b8cc7c1819407978b05b72d387a0192240595295f6`). It
contains five eight-hour groups and uses the original nested 1/6/16/all views;
those views are correlated views of a group, not additional groups.

| Partition | UTC groups | Scans | Local verified cache availability |
|---|---|---:|---:|
| TRAIN | Sep 21 00Z (72), Sep 21 16Z (79) | 151 | 151/151 |
| Validation | Sep 21 08Z (80), Sep 22 08Z (44) | 124 | 124/124 |
| TEST | Sep 22 00Z (64) | 64 | 63/64 |

The first TRAIN cache root has 16 verified symlink reuses and 56 local
directories; all 72 manifest IDs resolve to a receipt and `state_cache.npz`.
The TEST failure is the frozen ID `scan-hop-6cd2560365a058bc` (position 48).
It lacks counter-continuity authority, so no 64-scan TEST comparison may drop,
replace, or reorder it. The predeclared 1/6/16 TEST prefixes remain available.

The historical selected model is **not** the current shared-clock method. The
frozen validation/TEST selected rule performs a blind tau-zero geographic search
from Sacramento 250 km and Reno 500 km, freezes its identities, then conditionally
fits a regularized global epoch (selected scale 0.2 s). In contrast, the current
shared-clock sensitivity evaluates the 165 TRAIN-sealed local-grid points,
reselects ordinary visible candidates at every shared receive-time shift in
[-5,+5] s, and has no cone arm or calibrated timing prior. Treating their
published scores as a direct model comparison would mix identity freezing,
regularization, geographic search domains, and data scopes.

A fair DS1 comparison must run tau-zero ordinary candidate re-selection and
shared-time candidate re-selection on identical frozen memberships, nested view
orders, priors, geographic point/search budget, causal cache/TLE bindings,
candidate policy, visibility rule, randomized masks, per-track TRAIN CFO,
occupied-second weights, and 800 Hz all-track cap. It may differ only by the
single global receive-time shift and its predeclared grid. Seal both inferences
before held/reference evaluation. Choose or alter neither method from validation
or TEST outcomes; use TRAIN for protocol/model decisions and validation for a
frozen comparison. The full TEST arm remains a recorded failure.

Runtime must be budgeted by group and view. The 165-point shared-clock TRAIN
grid took 998 s with an amended eight-worker execution; repeating it naively
for every group/view/prior is not a bounded single experiment. Benchmark the
exact frozen arms first, account for every cache/export failure, and avoid
expanding a local TRAIN grid into a new validation or TEST geographic search
without a separately frozen protocol.

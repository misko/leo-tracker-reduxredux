# Fitted-only three-model development expansion

The reusable composition runs the original A/B/C numerical models against one
sealed generic six-proposal parent. DS21-009 is the first real case frozen under
this protocol. It is a development comparison, not the frozen release for the
20 locked fast recordings. The full-DS21 target remains below 0.5 km per eligible
CH1–8 recording, with failures retained as misses.

| Model | Explicit run unit | Selection | Maximum new fits per case |
| --- | --- | --- | ---: |
| A: sequential calibration | Six separate low → locked-high → final-all paths | Lowest stationary final-all training objective | 18 |
| B: absolute-frequency shape-proposal model | One six-start unit per all/low/high view | Lowest stationary own-view training objective | 18 |
| C: native joint association | One six-start unit per all/low/high view | Lowest stationary own-view training objective | 18 |

Every call retains fitted c, the original objective, 20 seconds, 600 iterations
and the original proposal's 25 km disk. A failed or nonstationary prerequisite
stops its dependent path, preserving the failed stage and explicitly recording
skipped stages. B/C attempt their six starts independently. Skipped stages are
not counted as completed optimizer calls. No zero-c arm or held-data preparation
is invoked.

Initialization projects the six physical seed functions into each model/view's
original coordinates. C derives six receiver ambiguity lifts once from all-band
training and applies each once to its corresponding view seed. All half-band
views inherit shared discovery, candidate bank, geography and physical seed
information; their restricted likelihoods are not independent end-to-end
half-band pipelines. C additionally inherits all-training receiver lifts.

A supplies one final-all estimate plus dependent stage diagnostics. Its locked
high stage is not an independently estimated high-only location. B and C supply
all/low/high estimates. The resulting seven evaluation rows cannot be interpreted
as nine independent band/model estimates.

Initialization is capped at 90 seconds internally (TERM 105, KILL 110). Each A
path uses those same slice limits. Each B/C view is capped at 165 seconds
internally (TERM 175, KILL 180). Preparation shares the slice budget. Only an
explicit completed checkpoint can continue in another slice; orphan/failed work
is not silently retried. One heavy dataset process runs at a time with one BLAS
thread; there is no unattended case campaign.

All six A path outcomes and all three B and C view outcomes must be sealed before
reference access. A truly terminal failed unit can be explicitly finalized with
its complete attempt inventory and reason; a missing or changing outcome blocks
evaluation. Finalized failures remain misses. Selection uses training objectives,
never the closest known position. Accuracy is relative to the configured reference,
which is not independently surveyed, and is reported separately from frequency fit.

Implementation commit `2f311f953` adds `tools/ds21_fitted_models.py` and owned tests
without changing successfully frozen sources. Seventeen tests passed, followed
by a saved-stage continuation check. Five independent integration checks passed
in 26.01 seconds, covering actual small-model fits, physical seed/lift transport
and the finalized-failure/reference barrier. Independent source review found no
blocking numerical mismatch. The original fitter supplies KKT and physical-bound
certificates; the composition additionally checks finite layouts and local disks.

DS21-009's frozen protocol SHA-256 is
`cf286c67385c33642d22f77435d8848aad9acac36595ee68d5ac08ab00089fc6`.
It binds 410 reachable source files, the actual native binary/C++ source and the
[completed initialization](PROPOSALS_009_RESULTS.md). Its model fits have not yet
run at protocol publication. The original five-case A/B/C comparison and separate
DS21-007 Model C result remain historical results, not silently relabeled outputs
of this new orchestration. Complete development evaluation and a separate model
freeze must precede locked inference.

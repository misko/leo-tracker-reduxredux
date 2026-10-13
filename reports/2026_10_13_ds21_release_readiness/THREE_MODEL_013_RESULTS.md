# DS21-013 fitted-c three-model results

All three models have severe position misses on DS21-013. Their training-selected
CH1–8 errors are **266.839679 km for A, 268.879362 km for B and 267.759878 km
for C**. All seven reported views miss 0.5 km. Of 54 attempted location fits,
**52 are stationary**; two nonstationary C outcomes remain saved and excluded
from selection. All 12 outcomes were sealed before the seven reference rows
were joined. The full-DS21 target remains unmet.

| Model | View | Error km | Selected proposal | Fitted c Hz/GHz | Calls / stationary | Boundary flag |
| --- | --- | ---: | --- | ---: | ---: | --- |
| A | Final CH1–8 | 266.839679 | cold-0 | 82.727343 | 18 / 18 | No |
| B | CH1–8 | 268.879362 | cold-0 | -611.348813 | 6 / 6 | No |
| B | CH1–4 | 268.826502 | cold-0 | -677.461184 | 6 / 6 | No |
| B | CH5–8 | 190.851447 | cold-1 | -755.899318 | 6 / 6 | No |
| C | CH1–8 | 267.759878 | cold-0 | -488.694069 | 6 / 5 | No |
| C | CH1–4 | 271.452943 | cold-0 | -800.454154 | 6 / 5 | No |
| C | CH5–8 | 198.398059 | cold-2 | -806.623532 | 6 / 6 | No |

A runs six dependent low → locked-high → final-all paths, reporting one
final-all selection. B/C select separately among stationary fits in each view.
Selections minimize the unchanged own training objective, then original start
index; neither accuracy nor reference position chooses a model or proposal.
Combining B is slightly worse than low and substantially worse than high.
C combining is better than low and worse than high. Every result remains a
large miss, so those within-case comparisons do not establish useful accuracy.

All seven selected boundary flags are false. Their minimum physical slacks
range from 0.353816 to 2.302385. This flag covers satellite total-timing and
geographic constraints, excluding common timing and coefficient bounds.
Constrained stationarity and inactive reported boundaries do not establish
global optimality or correct localization.

| Retained nonstationary fit | Proposal | KKT | Elapsed s | Solver success | Boundary |
| --- | --- | ---: | ---: | --- | --- |
| C/all start 3 | shape-low | 235.230587 | 20.063334 | No | No |
| C/low start 2 | cold-2 | 0.001292600 | 7.620696 | Yes | Yes |

The fixed stationarity threshold is 0.001. Solver success does not override
that check: C/low start 2 fails even though the optimizer reports success.
The C/all attempt ran for 20.063 seconds without stationarity.
Neither attempt was retried, dropped or accepted by changing tolerances.

Frequency diagnostics are separate from position accuracy:

| Model, CH1–8 | Training objective | Likelihood NLL | Posterior frequency RMS Hz |
| --- | ---: | ---: | ---: |
| A | 35928.288758 | 35400.352879 | 158.266882 |
| B | 34372.428491 | 33680.321602 | 124.394134 |
| C | 35304.116545 | 34801.100423 | 150.451398 |

These scores have different association/calibration structures and are not
interchangeable validation metrics. Frequency RMS is not a position confidence
interval; the stationary fits here demonstrate how convergence can coexist
with severe position error.

The [completed initializer](PROPOSALS_013_RESULTS.md) supplied 49 shared
satellite candidates and six proposals in each view. Their original east/north
coordinates in the regional-prior frame are:

| Proposal | East km | North km |
| --- | ---: | ---: |
| cold-0 | 156.250000 | 6.250000 |
| cold-1 | 43.750000 | -231.250000 |
| cold-2 | 25.000000 | -225.000000 |
| shape-low | 34.641668 | -218.675926 |
| shape-high | 167.688118 | 6.791643 |
| shape-all | 154.590337 | -28.601487 |

All models inherit these widely separated proposals and their original 25 km
search disks; A's high stage locks its preceding low-stage position. A separate
post-seal geometry audit places the configured reference 118.889651 km from
the original regional-prior center, inside its 250 km radius, but outside all
six proposal disks. Its nearest proposal center is 182.457260 km away in
optimizer coordinates, exceeding the local radius by **157.457260 km**.
Thus these fixed local domains cannot recover the reference. This establishes
an upstream coverage failure; it does not establish why global discovery missed
or validate an alternative search policy. Source/input/recording bindings pass.
The next priority is a reference-blind discovery-coverage/multiview exploration
control before further initialization, preserving the original 100-point budget
and frozen namespaces. No reference-derived seed was used for these fits.

The saved discovery search stops at its 100-point budget with 76 deferred
cells. Its evaluated spacings of 100 / 50 / 25 / 12.5 km have 16 / 16 / 24 / 44
points respectively. The coordinator's post-seal coverage check finds the
nearest evaluated point to the configured reference is the coarse `[-50, -50]`
point, 48.291651 km away; no finer evaluated point is closer. The original
best-first hierarchy uses the all-view score before choosing one low/high/all
proposal. That coarse score is not a certified lower bound on finer-cell fits.
These observations locate a coverage gap; they do not validate a replacement
exploration rule or show which model would succeed with different proposals.

Training inventory is 2,666 / 1,433 / 1,233 all/low/high windows, with the
original randomized whole-20-second partition and seed 20261012. The unchanged
[v2 protocol](THREE_MODEL_EXPANSION_V2_PROTOCOL.md) uses fitted c only, 20 seconds
and 600 iterations per fit, and unchanged priors. Initialization and A paths
use 90/105/110-second internal/TERM/KILL limits; B/C views use 165/175/180.
Dataset processes run serially with one BLAS thread. The 411 numerical and
412 reader source bindings remain frozen; there were no numerical-source edits
or repeated fits. The narrow metadata reader retains the sequential high-stage
descriptive override and validates the unchanged numerical receipts.

Of 24 required A/B seed projections, 23 succeed with the original strict solver.
Only **B/all start 3, shape-low**, uses independently certified original physical
source coefficients after the specific projection nonconvergence error.
Its frame, clock basis, coefficient and timing checks pass; physical closure
RMS is 4.700e-13 Hz and maximum mismatch 7.276e-12 Hz. This is a seed transfer,
not an accepted failed solver result or a stationary location fit. Six carried
clock coefficients are -1999.9999999999995, only about 4.55e-13 Hz inside the
original -2000 Hz bound. The certificate's empty exact-equality `active_bounds`
list does not imply substantial distance from those bounds. C's 18 native
seeds and six once-only all-training receiver lifts are unchanged; the report
does not attribute C's failures or the shared position misses to B's fallback.

B/C half-view likelihoods use designated observations but share discovery,
proposal geography and physical initialization. C additionally shares its
all-training receiver lifts. These are not independent end-to-end half-band
pipelines. Held observations were not used for these fits or selection. The
reference entered only post-seal evaluation and the coverage audit and is configured, not an
independently surveyed position. The aggregate review terminal SHA-256 is
`40933c2e86be096a41ef3805d611db4276456768d77b81c958214cb08e3feae7`.
The independent [receipt audit](THREE_MODEL_013_AUDIT.json) passed the source,
parent, call, stationarity, selection, geometry and evaluation checks without
new fits or reference-error calculations.

The historical five-case table remains unchanged. The new fitted-only A/B/C
expansion now covers 009, 011 and 013; 007 remains C-only. Nine of 34 fast
development cases have complete proposal sets and 25 still require
initialization. DS21-025 has passed metadata readiness only: its case freeze
and initialization have not started. The 20 locked fast recordings remain
unopened for inference. The passing C/all result on DS21-011 does not establish
general performance in light of this severe DS21-013 miss.

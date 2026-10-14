# Original Model B: two bounded fitted-c diagnostics

DS21-039 and DS21-023 completed the original-receipt diagnostic with **zero
optimizer calls**. Their original selected positions and frequency fits are
unchanged. The local results support strong timing/position confounding in both
worst cases; they do not establish its physical cause, explain the best-versus-
worst ranking, or provide a localization improvement.

Both use `baseline-shared-six-proposals-v1` Model B: the original common-clock,
free-group absolute Gaussian/clutter likelihood. They are not native Model C.
Exact objective type checks and the independently reconstructed B likelihood,
physical gradient and posterior guard that distinction.

## Execution and source closure

| Recording | Training preparation seconds | Entire slice seconds | Diagnostic seconds |
| --- | ---: | ---: | ---: |
| DS21-039 | 16.518063 | 18.309953 | 1.093582 |
| DS21-023 | 12.392551 | 13.595673 | 0.643563 |

The 180-second internal whole-slice bound includes preparation. Each process
also had external TERM at 195 seconds and KILL five seconds later. Runs were
sequential with single-threaded BLAS and completed normally, without retries.
Preparation is computation and is included in the timings. No held observations
were prepared, no reference was read, and no RF was collected.

The pre-preparation freeze binds 385 source files and their archives plus 92
input files. Both cases retain the original 20261012 whole-20-second randomized
partition and all/low/high preparation digests. Integer probe counters and
canonical window IDs assign every scored observation to its original block.
Each view uses the original ordered bank and stationary fitted-c training
winner. No new seed, candidate, prior, model selection or c=0 arm enters.

All six saved objectives replay exactly. The independent Gaussian objective
oracle differs by at most 3.638e-12; NLL and satellite posterior differences
are exactly zero. The largest full physical-gradient discrepancy is 1.771e-12.
The six views used six objective evaluations, six orbit derivative calls and
six standalone likelihood oracle evaluations, with zero optimizer calls.
All selected fits have saved boundary=false and positive constraint slack,
from 0.628244 to 5.689365.

## Timing dominates the local loss of position curvature

The table gives the weakest horizontal eigenvalue of the **linearized observed
mixture** curvature, in NLL/km², after each declared nuisance profile. Original
prior curvature is retained. These local matrices include satellite/clutter
score covariance; they are not the full nonlinear orbit Hessian or calibrated
position confidence.

| Recording / view | Nuisance fixed | Calibration free | Timing free | Both free | Fixed / both |
| --- | ---: | ---: | ---: | ---: | ---: |
| 039 CH1–8 | 5377.024200 | 1361.938255 | 26.135850 | 13.611420 | 395.0 |
| 039 CH1–4 | 1780.543091 | 599.569852 | 6.220123 | 3.460160 | 514.6 |
| 039 CH5–8 | 1609.245935 | 296.161810 | 5.820001 | 0.661148 | 2434.0 |
| 023 CH1–8 | 7688.271035 | 481.281237 | 27.776083 | 7.432860 | 1034.4 |
| 023 CH1–4 | 1023.564569 | 193.821113 | 10.669299 | 5.799709 | 176.5 |
| 023 CH5–8 | 2970.366026 | 269.265337 | 5.651708 | 2.408578 | 1233.2 |

Timing alone reduces the weakest all-view curvature by about 206× on 039 and
277× on 023, versus about 3.95× and 15.97× for calibration alone. The joint
profile loses further information. Axes may rotate between profiles, so these
ratios compare their weakest eigenvalues rather than one matched displacement.
They support B-specific timing/position confounding without proving faulty UTC,
orbit error, an incorrect timing prior, or a transferable hardware correction.

The complete-data Gaussian approximation overstates the all-view joint weakest
curvature by 1.821× on 039 and 1.914× on 023. On 039/high it overstates it by
11.081×. Thus treating fitted satellite assignments as certain would obscure a
material part of this ambiguity.

## Whole-block and prior attribution

All views retain 12 original training blocks. The all views contain 2798 and
2384 windows for 039 and 023. Attribution holds each full-state compensated
direction fixed; blocks are not refitted or discarded.

| Recording / view | Likelihood curvature | Prior curvature | Negative likelihood blocks / 12 |
| --- | ---: | ---: | ---: |
| 039 CH1–8 | 12.014157 | 1.597262 | 1 |
| 039 CH1–4 | 2.969977 | 0.490183 | 5 |
| 039 CH5–8 | -0.301147 | 0.962295 | 3 |
| 023 CH1–8 | 5.876820 | 1.556040 | 0 |
| 023 CH1–4 | 4.795000 | 1.004709 | 5 |
| 023 CH5–8 | 1.672917 | 0.735660 | 2 |

Each row's likelihood and prior terms sum to the corresponding joint weakest
eigenvalue. For 039/high, the local compensated likelihood direction has negative
curvature and the original prior stabilizes the positive total. Block 9 supplies
-2.669205 likelihood curvature, while the largest positive block supplies only
0.741069. These signed quantities are local curvature contributions, not
probabilities, independent sample counts or evidence to remove those blocks.

## Limits and next test

This diagnostic omits orbit second derivatives, visibility changes, alias
crossings, competing modes and the optimizer's active-bound tangent cone.
Positive local profiles do not prove global identifiability or accuracy. The
best two B cases were not run, so this two-case test cannot establish whether
the measured confounding distinguishes failures from successful cases.

Both all-view joint curvatures exceed their half-view curvatures despite the
mixed historical position outcomes. Better local curvature therefore does not
establish that combining improves localization. No new frequency-fit or position
result is inferred from these matrices.

The next discriminating work is a bounded full-objective finite-displacement
check along the saved compensated directions, keeping bank, observations and
original priors fixed. This can check the tangent approximation before any
physical timing intervention is proposed. Blanket timing-prior tightening or
calibration transfer remains unsupported. This round remains fitted-c only.

## Receipts

The [saved-scalar/hash audit](MODEL_B_ORIGINAL_TANGENT_AUDIT.json) verifies all
preparation and numerical source/input bindings, output aggregate seals,
terminal joins and group/prior arithmetic without new scientific calls. It
retains every view and its signed group contributions. The audit SHA-256 is
`bb9cd0696a6e47497a1fbf842a5161a5d385d2ecf0166cc1ff65f6d8e7e74edc`.

The [pre-preparation freeze](model-b-original-freeze.json) SHA-256 is
`78bbd8c748d29221246f5fb6d63e29157dcc02dc3c59a1b706ba7aa1760392e6`.
Numerical terminal SHA-256 values are
`4714201371a79178f681c320a248184b0f558460924f592771169f7e55e2a219`
for 039 and
`90c9635a646323fed7761c413104301f8a22287fac04d639b1e890921452ff80`
for 023. Full receipts and source archives remain in their assigned local
`model-b-original-039` and `model-b-original-023` namespaces. The prototype's
20 synthetic component tests and Ruff passed before these runs.

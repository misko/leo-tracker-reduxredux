# C075 fold initialization recovers availability, but leaves a large optimization gap

The prespecified randomized-block experiment produced one strictly accepted full-training propensity estimate. Its configured-station distance is 21.331360 km. This is not evidence of a good model optimum: its objective is worse than a known feasible zero-propensity state, and several rejected endpoints have much lower objective. The conditional arm retains its original 77.586921 km estimate. No model or cohort result is promoted.

Distances below use the existing **configured, unconfirmed station**; they are not verified accuracy. Original held observations and locked cases were untouched.

| Arm | Fixed fold profiles accepted | Full continuations accepted | Training-selected origin | Selected objective | NLL | Configured distance km |
|---|---:|---:|---|---:|---:|---:|
| Conditional | 6/6 | 4/6 | Prior full-data incumbent | 39156.371971 | 38900.022418 | 77.586921 |
| Propensity | 5/6 | 1/5 | Fold 0, original low geography | 44370.470258 | 44282.529027 | 21.331360 |

Historical original raw C distances are full 77.586921, CH1–4 23.428397 and CH5–8 51.146438 km. Those halves share full-channel discovery/initialization and use the original raw likelihood. They are not matched halves of this new propensity model, and never entered its selector.

## What changed and what did not

All twelve fixed profiles completed before any release. The frozen seed 20261014 randomized whole-20-second blocks into 1520 and 1635 observation windows. Each accepted fold state transferred its complete physical and nuisance state into one same-arm full-training free fit, preserving the original geography-specific 25 km disk. No source endpoint required projection; no failed profile or release was retried. The experiment added 23 calls: twelve profiles and eleven releases, sixteen accepted overall.

Every fit retained the original nominal 20-second/600-iteration policy and independent KKT threshold 0.001. The iteration bound is not an objective-evaluation bound. Final bookkeeping/audits can extend elapsed time slightly past the nominal solver deadline. Four units ran concurrently; profile units took 64.2–74.4 seconds including preparation, release units 72.4–91.4 seconds. The original full-data experiment and original cohort remain unchanged.

Qualification passed 191 objective evaluations and zero fits in 34.661 seconds: 190 raw/conditional/zero-tail/gradient checks and one incumbent replay. Maximum propensity finite-difference errors were 6.27e-8 and 6.77e-8. All 21 driver/wrapper/randomized-helper tests and Ruff passed; the evaluator's two tests verify the seal barrier and recursive validation.

## Failure and optimization evidence

The propensity fold-1 high profile was rejected despite solver success: KKT 0.002508724 after 17.410 seconds and 647 evaluations. It received no release. No threshold was relaxed.

| Rejected full continuation | Objective | KKT | Elapsed s | Evaluations |
|---|---:|---:|---:|---:|
| Conditional fold 0 low | 41426.761369 | 0.0100371 | 20.072 | 256 |
| Conditional fold 0 high | 43517.685987 | 16.0460 | 20.093 | 225 |
| Propensity fold 0 all | 38355.694526 | 0.0278079 | 20.115 | 342 |
| Propensity fold 0 high | 41669.182713 | 46.3579 | 20.056 | 74 |
| Propensity fold 1 all | 38808.389091 | 0.00731696 | 20.073 | 235 |
| Propensity fold 1 low | 44053.517286 | 229.285 | 20.082 | 235 |

The accepted propensity endpoint has KKT 0.000225408. However, the original full-data state with a zero propensity tail is feasible with objective 39156.371971, lower than the accepted endpoint's 44370.470258. This within-model nesting comparison proves a remaining search shortfall. The much lower rejected all-origin endpoints strengthen the initialization/stopping concern; they remain ineligible. Cross-arm objective reduction is not used to establish superiority, and proximity to the configured station does not override stationarity.

The result supports using fold initialization to obtain additional calibration basins, but does not establish that it reliably solves the full propensity objective. No additional continuation is implicit in this report.

## C019 is a separate coverage problem

Independent post-seal geometry replay places the configured station at native XY (-87.0357958832, -80.9908603467), inside the 250 km regional prior. Every original 25 km proposal disk misses it: minimum planar clearance 79.784175 km at start 4; the current all/half anchor disks 0 and 5 clear it by 129.724816 and 203.272401 km. That diagnosis motivates a separate training-only coverage intervention, not reference-chosen seeds or more C019 propensity fits in the same inaccessible disks.

## Reproduction and seals

- Driver source: `002890b11`; evaluator source: `0d6c003a0`; immutable randomized helper: `413560688`.
- Scientific namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-fold-initialization-v1/DS22-075`.
- Protocol SHA256: `fa07466155672d44404c8ddd9cdcad6e2db8e64f53701cdb51e084c1e63d933e`.
- Qualification SHA256: `6ad66ec42f25ca923bcf290520b6a06664f0a21373d9e48f9e585696fdd1a8c2`.
- Terminal SHA256: `1e0f182c868bb87b517559f2714a2a7cc08b5338544a96d7cfa7a2bb6e814959`.
- Global seal SHA256: `63a1c64d9fc5ee8fcc8bf0ad6120011d812c6625512abc9bf2a29f90dc3ba5cc`.
- Comparison namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-fold-comparison-v1`; protocol SHA256 `129dace54f3054fa8e7b06587bd55adb532ce3a9d5a1bc11d5fd45c703b61a58`.

The evaluator replayed all unit seals and eligibility before reading the configured reference. No held prediction or accuracy-target claim is included.

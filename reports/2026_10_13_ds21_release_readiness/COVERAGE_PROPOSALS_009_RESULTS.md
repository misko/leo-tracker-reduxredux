# DS21-009 coverage-control proposal initialization

All five initialization stages completed under the unchanged qualified coverage policy in the separate `coverage-initialization-v1/DS21-009` namespace. Shape and hybrid each returned **9/9 stationary fits**; fresh and cold bootstrap each completed nine calls. Export sealed six physical proposals per all/low/high view, **18 seeds over 33 candidates**, with no failed call receipts. This establishes a usable parent for the fitted-c model comparison, not position accuracy.

The [receipt audit](COVERAGE_PROPOSALS_009_AUDIT.json) checks the recursive qualified predecessor chain, case/input/partition authority, exact terminal/artifact/call inventories and unchanged 405-source live/archive closure. It reads stored certificates and performs metadata/scalar arithmetic only: no optimizer, preparation, projection, objective, orbit, physical-function or reference calculations. The [original DS21-009 initialization](PROPOSALS_009_RESULTS.md) and [original A/B/C results](THREE_MODEL_009_RESULTS.md) remain unchanged.

## Stage outcomes

The [fixed discovery transfer](DISCOVERY_COVERAGE_009_RESULTS.md) supplies a 31-candidate union from DS21-009's original 983-candidate regional bank. Fresh bootstrap adds catalogue IDs 56805 and 69302, expanding the shared pool to 33. Cold bootstrap and export preserve that pool. Training uses the original randomized whole 20-second partition, seed 20261012 and held blocks 0/5/12; held observations and the reference were not used for these operations or selections.

| Stage | Terminal elapsed, s | Internal / TERM / KILL budget, s | Outcome |
| --- | ---: | --- | --- |
| Shape | 29.739532 | 240 / 255 / 260 | 9/9 stationary; three view call receipts |
| Fresh shape bootstrap | 38.633362 | 90 / 105 / 110 | Nine successful calls; pool 31 → 33 |
| Hybrid | 48.544662 | 240 / 255 / 260 | 9/9 stationary; maximum KKT 0.000820520 |
| Cold bootstrap | 41.727254 | 90 / 105 / 110 | Nine successful calls; fixed pool 33 |
| Six-proposal export | 45.848971 | 90 / 105 / 110 | 18 physical seeds; no optimizer calls |

Elapsed fields above come from terminals; the JSON binds slice launch/termination receipts separately. All shape winners use attempt index 2 under their own view training objective. Shape removes constant RF offsets; its fitted-arm label does not mean this stage identifies the RF-dependent coefficient c.

| Proposal index | ID | Original center in optimizer coordinates, km |
| ---: | --- | --- |
| 0 | cold-0 | [-87.5, -62.5] |
| 1 | cold-1 | [-87.5, -87.5] |
| 2 | cold-2 | [-75, -75] |
| 3 | shape-low | [-89.491636, -97.157550] |
| 4 | shape-high | [-86.179426, -94.727038] |
| 5 | shape-all | [-85.717338, -94.786602] |

All views retain those six IDs and centers, with parameter count 40 and satellite-number timing mapping over the 33-candidate pool. Bootstrap source indices identify bootstrap order, not the winning shape attempt. Cold construction preserves the original nearest-donor and missing-satellite timing fallback rules. Hybrid remains diagnostic; its optimized positions do not replace exported seeds.

## Target projection loss and source closure

| Stage / view | Maximum target RMS, Hz | RMS source | Maximum absolute target residual, Hz | Absolute-residual source |
| --- | ---: | --- | ---: | --- |
| Fresh / all | 1150.785824 | shape-high (1) | 7158.739298 | shape-high (1) |
| Fresh / low | 3.388710e-11 | shape-all (2) | 5.093170e-11 | shape-all (2) |
| Fresh / high | 5.162094e-11 | shape-low (0) | 1.164153e-10 | shape-all (2) |
| Cold / all | 1694.544208 | cold-1 (1) | 9222.040603 | cold-1 (1) |
| Cold / low | 4.572511e-11 | cold-0 (0) | 6.548362e-11 | cold-0 (0) |
| Cold / high | 3.884459e-11 | cold-1 (1) | 7.275958e-11 | cold-1 (1) |

Final export carries these target-projection diagnostics. Across all six exports, the all-view maxima remain 1694.544208 Hz RMS and 9222.040603 Hz absolute at cold-1 (export index 1). Low maxima remain 4.572511e-11/6.548362e-11 Hz at cold-0 (0). High RMS maximum is 5.162094e-11 Hz at shape-low (3), and absolute maximum is 1.164153e-10 Hz at shape-all (5).

The separately stored maximum closure to each seed's **own represented physical function** is 7.275958e-12 Hz for all and zero for low/high. Tiny own-source closure verifies the export representation; it does not erase the large all-view approximation loss against low/high bootstrap donor targets. These certificates are retained, not independently re-predicted by this audit. They establish neither physical calibration truth nor the cause of any future model error.

## Training diagnostics and zero-fit model initialization

Hybrid selections minimize their own stationary training objective. Every selected and unselected hybrid boundary flag is false.

| View | Selected start | Objective | Likelihood NLL | Posterior frequency RMS, Hz | KKT |
| --- | ---: | ---: | ---: | ---: | ---: |
| All | 2 | 32843.828601 | 32611.016267 | 87.459850 | 0.000499161 |
| Low | 1 | 17897.212011 | 17697.850281 | 89.211376 | 0.000498305 |
| High | 1 | 15447.756943 | 15199.400039 | 98.321112 | 0.000195153 |

These view-dependent objectives and frequency diagnostics are not position errors or a basis for cross-model accuracy ranking. Frequency RMS is not positional confidence.

The separately qualified model consumer completed zero-location-fit initialization, bound to 415 live/archive sources and receipt SHA-256 `3b6644e7e6d8deccc1e620c81c083483856d07b75621e005f07aaa90761f004f`. Of 24 required A-low/B seed projections, 21 use the original strict solver. B/all cold-0, cold-1 and shape-high use the existing exact-feasible-source transfer only after the literal strict nonconvergence error. All four frame, clock-basis, coefficient-bound and timing-bound proof flags are true; their RMS certificates are 2.062010e-13 / 4.987876e-13 / 2.074349e-13 Hz, with maximum residual 7.275958e-12 Hz each. This certifies the exported source function rather than the earlier bootstrap donor target. Across required projections, maximum RMS/absolute residual is 4.485215e-10/9.931682e-10 Hz. An empty exact active-bound list alone does not establish substantial distance from coefficient bounds.

Native C projection is another distinct quantity: all-view RMS spans 13.640077–434.557531 Hz, with maximum absolute residual 2810.856039 Hz. Native low/high absolute maxima are 1.818989e-11/4.365575e-11 Hz. Six receiver lifts are derived once from all training and shared across 18 C seeds; all six use [-1, +2]. Twelve unused A high/all placeholders retain the original dependent-path semantics. No location fit is counted by this initialization.

B/C half-view likelihoods use designated observations but share discovery, geography and physical initialization; C additionally shares all-training lifts. They are not independent end-to-end half-band pipelines. Final model outcomes must all be sealed before the reference join; this report makes no final-model accuracy claim and reads no model errors. The final proposal terminal SHA-256 is `255cb5ab98186e915471b6a85e72522c72c0338f4ce6f8ae5f03c5863e6bd758`. This second DS21-009 namespace does not add a development case: the original nine complete initialization sets and 25 remaining initializations remain the census. Locked inference remains unopened, and the full-DS21 0.5 km target remains unmet.

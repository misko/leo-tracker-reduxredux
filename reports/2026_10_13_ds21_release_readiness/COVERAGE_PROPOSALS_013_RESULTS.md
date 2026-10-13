# DS21-013 coverage-control proposal initialization

All five downstream initialization stages completed in the separate `coverage-initialization-v1/DS21-013` namespace. Shape and hybrid each returned nine stationary fits; both bootstraps returned nine successful call receipts; the final export sealed six physical proposals for each of all, low and high views. This establishes a usable proposal parent for the unchanged fitted-c model comparison. It does not establish localization accuracy.

The [receipt audit](COVERAGE_PROPOSALS_013_AUDIT.json) validates the qualified predecessor chain, case/input bindings, exact artifact inventories, source archives and saved diagnostics without new optimizer, projection, objective, orbit or reference calculations. All five stages bind the same 405-source closure. Root independently checked the completed chain and physical exports. The original DS21-013 initialization and [failed three-model comparison](THREE_MODEL_013_RESULTS.md) remain unchanged.

## Stage receipts

The parent is the sealed [dense-grid discovery control](DISCOVERY_COVERAGE_013_RESULTS.md), using the original 1,052-candidate regional bank. Its selected point-local union contains 37 candidates. Fresh bootstrap expands that union to 40 by adding catalogue IDs 53261, 56029 and 68000; cold bootstrap and export preserve the 40-candidate pool. The case retains its original training partition and designated view observations. Held observations and the reference were not used for these initialization operations or training selections.

| Stage | Terminal elapsed, s | Internal / TERM / KILL budget, s | Stored outcome |
| --- | ---: | --- | --- |
| Shape | 31.685034 | 240 / 255 / 260 | 9/9 stationary fits, three view call receipts |
| Fresh shape bootstrap | 38.701900 | 90 / 105 / 110 | 9 successful calls; candidate union 37 → 40 |
| Hybrid | 52.350134 | 240 / 255 / 260 | 9/9 stationary fits; maximum KKT 0.000798400 |
| Cold bootstrap | 44.196603 | 90 / 105 / 110 | 9 successful calls; fixed 40-candidate pool |
| Six-proposal export | 49.485733 | 90 / 105 / 110 | 18 physical seeds; no optimizer calls |

There are no failed call receipts. Elapsed times above come from stage terminals; slice launch/termination receipts are bound separately in the JSON audit. Stationarity certificates are retained and checked through the existing reader, rather than independently recomputed.

Shape winners are selected by their own view training objective. The all/low/high winning attempt indices are 1/2/2. Shape removes constant RF offsets; its fitted-arm label does not mean this stage identifies the RF-dependent coefficient c. The final proposal order and original optimizer-coordinate centers are:

| Proposal index | ID | Center, km |
| ---: | --- | --- |
| 0 | cold-0 | [-93.75, -81.25] |
| 1 | cold-1 | [-87.5, -62.5] |
| 2 | cold-2 | [-81.25, -93.75] |
| 3 | shape-low | [-92.243254, -83.011205] |
| 4 | shape-high | [-87.324808, -80.498839] |
| 5 | shape-all | [-89.795044, -81.671596] |

Each view exports the same six IDs and centers. Bootstrap source indices identify bootstrap order, not the winning shape fit attempt. Cold construction retains the original nearest-donor rule and missing-satellite timing fallback. Hybrid is a diagnostic stage; its optimized locations do not replace these exported physical seeds.

## Projection loss and physical export closure

The all-view bootstrap projections retain substantial donor-target approximation loss. The half-view target projections are near numerical precision. These are separate from the final source-function closure certificate.

| Stage / view | Maximum target RMS, Hz | Source of RMS maximum | Maximum absolute target residual, Hz | Source of absolute maximum |
| --- | ---: | --- | ---: | --- |
| Fresh / all | 1569.914986 | shape-low (0) | 5356.305611 | shape-low (0) |
| Fresh / low | 1.052502e-11 | shape-low (0) | 2.182787e-11 | shape-low (0) |
| Fresh / high | 6.298404e-11 | shape-high (1) | 9.458745e-11 | shape-high (1) |
| Cold / all | 1272.950045 | cold-2 (2) | 4229.535798 | cold-1 (1) |
| Cold / low | 1.127138e-11 | cold-2 (2) | 2.546585e-11 | cold-2 (2) |
| Cold / high | 5.945310e-11 | cold-2 (2) | 9.458745e-11 | cold-2 (2) |

The six-proposal export carries these prior target diagnostics. Across its six seeds, the all-view maximum RMS/absolute residual is 1569.914986/5356.305611 Hz at shape-low (export index 3). Low maxima are 1.127138e-11/2.546585e-11 Hz at cold-2 (2). High maximum RMS is 6.298404e-11 Hz at shape-high (4); maximum absolute residual is 9.458745e-11 Hz, attained by cold-2 (2) and shape-high (4).

The separately stored maximum closure between each encoded seed and its **own source physical function** is 7.275958e-12 Hz for all and zero for low/high. This small closure verifies the export representation; it does not make the large all-view donor-target projection losses small. Those losses may warrant calibration-representability or alias diagnosis if downstream results miss, but these receipts establish neither their cause nor their effect on accuracy.

## Training-fit diagnostics and model initialization

Hybrid winners use their own stationary training objective. All selected boundary flags are false.

| View | Winning start | Objective | Likelihood NLL | Posterior frequency RMS, Hz | KKT |
| --- | ---: | ---: | ---: | ---: | ---: |
| All | 2 | 34320.185946 | 33898.045493 | 114.854118 | 0.000449407 |
| Low | 0 | 16964.270861 | 16604.162933 | 82.522138 | 0.000264727 |
| High | 1 | 15214.849005 | 14850.731583 | 86.029887 | 0.000522553 |

Objectives include prior contributions and differ across view observations; they are not position errors or comparable evidence for choosing a model by accuracy. Frequency RMS is not positional confidence.

The separately qualified model consumer completed its zero-location-fit initialization after these five seals. Its initialization receipt SHA-256 is `3ab06f8921dcabf5366689fb2dfc15b48d85c12805a7d139c2017972984008d2`, bound to 415 sources and the 40-candidate proposal parent. Of 24 required A-low/B calibration seed projections, 22 used the original strict solver. B/all cold-1 and shape-low used the existing exceptional exact-feasible-source transfer after the literal strict nonconvergence error; all four recorded frame, clock-basis, coefficient-bound and timing-bound proof flags are true. Their RMS certificates are 3.307044e-13 and 4.825384e-13 Hz; both maximum residuals are 7.275958e-12 Hz. Across all required projections, maximum RMS/absolute residual is 1.394515e-10/2.837623e-10 Hz. These model-input transfers certify the exported source function, rather than the earlier bootstrap donor target.

The exact-transfer certificates report `active_bounds: []`, but the original source coefficients are close to their clock bounds: cold-1 coefficient 18 is near +2000 Hz, and shape-low coefficients 15, 18 and 20 are near −2000 Hz, each only about 4.547e-13 Hz inward. An empty active-bound list therefore does not establish a substantial bound margin.

Model C derives six all-training receiver lifts once and shares them across its 18 seeds: receiver lifts are [-1, +2] except cold-1, which uses [-1, +1]. Its native all-view target projection is a third distinct quantity: RMS spans 57.558474 Hz (shape-high) to 426.442881 Hz (shape-low), with maximum absolute residual 4375.412875 Hz at shape-low. Native half-view maximum absolute residuals are 1.818989e-11 Hz for low and 2.910383e-11 Hz for high. These native projection losses neither replace the earlier bootstrap target losses nor contradict the tiny own-source export closure.

Twelve unused A high/all placeholders retain the original sequential semantics. No location fit is counted by this initialization. Half-view likelihoods use designated observations but inherit shared discovery and physical initialization; C additionally inherits the all-training lift information. Model selection and reference joining remain gated on all required model outcomes being sealed. The independently checked initialization certificates are separate from the continuing final model fits; no final accuracy result is asserted here.

The final proposal terminal SHA-256 is `90681086b6ed4b784bdd56fbb1452025f8602a18d9b8257e16cce5a2cd88fd3e`. This control adds a second namespace for DS21-013, not another completed development case: nine original initialization sets and 25 remaining development initializations remain the census. DS21-025 has metadata readiness only, and locked evaluation remains unopened. The full-DS21 0.5 km target is still unmet.

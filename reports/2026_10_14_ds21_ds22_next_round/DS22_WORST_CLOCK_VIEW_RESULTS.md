# DS22-019/053: matched original-view receiver clocks

All twelve prescribed fits passed unchanged strict stationarity. Adding the existing B common receiver-clock model to C improved each view's training objective, but did not repair either case's localization. The original results remain unchanged in the cohort.

| Case | View | Original configured distance km | Clock configured distance km | Original objective | Clock objective |
| --- | --- | ---: | ---: | ---: | ---: |
| 019 | All | 142.113760 | 143.557087 | 41673.350596 | 41242.747837 |
| 019 | Low | 203.397332 | 204.024688 | 24420.002052 | 24017.540260 |
| 019 | High | 214.750950 | 215.163403 | 16841.493853 | 16796.875619 |
| 053 | All | 75.781770 | 68.124853 | 45613.177281 | 44276.416253 |
| 053 | Low | 27.083146 | 27.383467 | 23440.183036 | 22931.162467 |
| 053 | High | 30.491824 | 30.658771 | 21798.539349 | 21657.513650 |

019 remains broadly poor across all views. 053's full estimate improves modestly but remains worse than both matched clock halves. Training-fit improvements therefore do not establish improved position accuracy. These are configured-station distances with DS22 station continuity unconfirmed, not verified ground truth.

Each view retained its genuine original observation frame, candidate bank, receiver lifts, group calibration, selected starting state and winning 25 km disk. The added clock uses the original B training nodes and prior scale 4. Its zero-extension objective, physical and original nuisance gradients, satellite responsibilities and clutter probabilities exactly matched the original model. Both arms passed the original fitter-start qualification without projection exceeding 1e-12. These are shared-discovery half comparisons, not independent half-only discovery controls.

Each unit paired an original-model repeat with a clock-model fit from the same original view's complete training-selected state. The accepted source incumbent remained eligible in the original arm; only newly accepted clock fits were eligible in the clock arm. The unchanged fitter used 20 seconds and 600 iterations per call, followed by independent KKT auditing. No optional gradient finisher, new candidate search, reference-derived start or held observation was used. All six units were sealed before the configured reference was joined.

The 12 additional fits are a diagnostic budget, not replacements for original cohort calls. This result does not rule out different basins or search-domain restrictions; it shows that adding common-clock flexibility locally at these selected states is insufficient. Subsequent cohort evaluation now identifies 059 as the most severe development failure, so 019/053 are no longer the only failure priorities.

Control source `d8339c33b`, evaluator `7253590f5`; ten control/nesting tests and three evaluator tests passed, with Ruff clean. Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-worst-clock-views-v1` and `ds22-worst-clock-comparison-v1`. No model promotion or accuracy-target claim is made.

# Matched point-density control: negative broadening gate

With fitted c, both matched endpoints are strict. The new point density improves primary held NLL by only1.91, improves3/7 blocks and changes original-classifier coverage810→806/1909 while requested coverage rises72→73/80. This fails the frozen gate; no all-five expansion follows.

| c arm | Same evaluation PDF | Legacy held NLL | New-point held NLL | Held legacy→new /1909 | Requested legacy→new /80 | New/lost held |
|---|---|---:|---:|---:|---:|---:|
| fitted-c | original_shared | 23077.251 | 23075.341 | 810→806 | 72→73 | 2/6 |
| fitted-c | new_singleton | 23152.865 | 23146.608 | 811→809 | 73→73 | 2/4 |
| zero-c | original_shared | 23924.531 | 23965.107 | 684→670 | 54→53 | 69/83 |
| zero-c | new_singleton | 24015.678 | 24056.237 | 688→673 | 54→53 | 69/84 |

fitted-c, original_shared: 804 held points retained, 2 model-ID changes. On that same intersection RMS changes 167.409→167.891Hz; changing-set RMS is 168.820→168.307Hz.


fitted-c, new_singleton: 807 held points retained, 3 model-ID changes. On that same intersection RMS changes 168.200→168.452Hz; changing-set RMS is 169.282→168.878Hz.


zero-c, original_shared: 601 held points retained, 32 model-ID changes. On that same intersection RMS changes 195.059→195.834Hz; changing-set RMS is 200.953→202.113Hz.


zero-c, new_singleton: 604 held points retained, 32 model-ID changes. On that same intersection RMS changes 195.005→196.597Hz; changing-set RMS is 202.013→203.259Hz.

The table and paired residuals use the same score/classifier within each row. The primary score is the original shared normalized PDF; the new proper singleton PDF is secondary. Neither is an emitter-identity truth test. Both PDFs are normalized: this experiment changes odds/signal/clutter weighting as a density family, not a broken normalizer.

The reused new-point endpoints are immutable iteration8 results. Exactly two legacy-density controls were added, with the same public TRAIN terminal complete seed,45 ordered candidates, 2073 TRAIN rows, free bands, priors, broad regional domain and1000-call/120s allowance. Newpoint c0 remains nonstrict; it was not repaired or retried. Both legacy controls are strict. c0 is conditional after fitted-c upstream discovery and is not a selection arm.

This is a posthoc control motivated by already inspected S03 outcomes, not unseen validation. The gate and metrics were frozen in PROTOCOL before outcomes. Evaluator source freeze occurred after the short control fits completed but before any new held scores were read; only their convergence and costs were known. All raw states and all predictions sealed before held scoring. No state, hyperparameter, window or source winner was selected from held measurements.

| State | KKT | Strict | Calls + audit | Configured distance km | Inside old25km disk |
|---|---:|---|---:|---:|---|
| legacy_fitted-c | 0.000780776 | True | 371 +1 | 6.866676 | False |
| new_point_fitted-c | 0.000282416 | True | 353 +1 | 6.847125 | False |
| legacy_zero-c | 0.00027987 | True | 489 +1 | 6.715833 | False |
| new_point_zero-c | 0.00108131 | False | 482 +1 | 8.515805 | False |

Configured station coordinates enter only these post-seal descriptive diagnostics; survey uncertainty is unknown. The common broad regional domain does not impose the original extra25km local production constraint. Correction functions use the same recorded times/RFs in state_diagnostics.json; coefficients alone are not hardware evidence. Plot RX1/RX2 are native0/1.

TRAIN2073, HELD1909 and boundary6 remain separate. Requested HELD80 spans windows007/008/009 with26/28/26 denominators. The other four sources and555 requested observations are untested. All rows, losses, model-ID changes, per-window metrics, seven blocks and changing versus retained-pair RMS remain in evaluation.json/NPZ. No held grouping, new RF, position seed, all-five fit, promotion or reference-based selection occurred.

![Paired held forecasts](paired_predictive_comparison.png)

![Complete state diagnostics](state_parameter_comparison.png)

| c arm | Requested held window | Legacy original-classifier /N | New point /N |
|---|---|---:|---:|
| fitted-c | DSX01-007 | 23/26 | 23/26 |
| fitted-c | DSX01-008 | 24/28 | 25/28 |
| fitted-c | DSX01-009 | 25/26 | 25/26 |
| zero-c | DSX01-007 | 4/26 | 3/26 |
| zero-c | DSX01-008 | 25/28 | 24/28 |
| zero-c | DSX01-009 | 25/26 | 26/26 |

The frozen test docstring's phrase 'Pre-outcome gate direction' describes the already prespecified gate logic; evaluator implementation and its tests were completed after control fits and before held scoring. This chronology is retained in evaluation_source_freeze.json, not retroactively relabelled as pre-outcome implementation.

The original cold fitted-c endpoint's795/1909 held and66/80 requested assignments is a descriptive anchor. The matched legacy free-band continuation reaches810 and72; the new point-density continuation reaches806 and73. Thus gains over the original pipeline are largely also achievable with free-band continuation of the legacy density. This does not isolate normalization, establish geographic improvement or justify choosing either state by position.

# DS21-013: what the saved calibration projections discard

This source/receipt audit identifies two different calibration approximation losses. Neither establishes why the remaining localization errors exceed 0.5 km. No new projection, objective, orbit, optimization or reference calculation was performed for this report; the slope differences below are arithmetic on saved training bootstrap coefficients.

Authority is the qualified coverage initialization and model chain, documented in [COVERAGE_PROPOSALS_013_AUDIT.json](COVERAGE_PROPOSALS_013_AUDIT.json) and [COVERAGE_THREE_MODEL_013_AUDIT.json](COVERAGE_THREE_MODEL_013_AUDIT.json). The latter binds 415 live/archive sources, initialization `sha256:3ab06f8921dcabf5366689fb2dfc15b48d85c12805a7d139c2017972984008d2`, and terminal `sha256:ac51aa9b16ef26c9388ce81564bfe018c8ea9f49e7f45b89f61e47ed6a04574d`. Original sources and the separate DS21-009 discovery transfer remain unchanged.

## Bootstrap targets contain a band-dependent time slope

`src/leo/analysis/channel_group_seeds.py:26–34` evaluates each bootstrap receiver correction in its donor training frame:

`a_rx + b_rx × (t − donor_time_center) + c × (RF − donor_RF_center)/1e9`.

`shared_bootstrap_seed` selects the high donor on channels ≥5 and the low donor otherwise (lines 82–85). The all-view donor is a frequency-target fallback only when a half donor is absent. All six actual low/high pairs exist. Both fresh and cold assembly call this port without `carried_corrections`; nearest donors supply missing satellite timing only (`tools/ds21_shape_fresh_seeds.py:89–94`, `tools/ds21_fitted_initialization.py:797–823`). The six physical exports retain these projected cold/fresh seeds, rather than the later hybrid fitted corrections (lines 825–836).

The original bootstrap estimates only receiver intercepts and slopes, leaving its RF coefficient at the initialized zero (`src/leo/analysis/regional_position_bootstrap.py:145–185`). This is the original proposal algorithm, not a new zero-c localization comparison. All downstream shape/hybrid/A/B/C optimization retains fitted c.

The shared projection columns are receiver intercepts, receiver time slopes, one common RF coefficient, 18 shared-clock coefficients and two constant receiver/group contrasts. The group contrast is `1[rx=r] × (high − training_high_fraction_r)`. Group drift and group clock are optional ports, disabled in this chain (`src/leo/analysis/channel_group_calibration.py:70–105,109–151`; `src/leo/application/channel_group_refinement.py`; `tools/ds21_fitted_models.py:184–203`). A constant low/high offset is therefore representable. Independent low/high slopes also require a contrast-times-time term, which is absent. A shared receiver clock can approximate some such structure under the recorded retune schedule; it cannot generally express two distinct slopes at the same receiver/time.

| Proposal | High−low slope RX0, Hz/s | High−low slope RX1, Hz/s | Bootstrap target projection RMS, Hz | Native C projection RMS, Hz |
| --- | ---: | ---: | ---: | ---: |
| cold-0 | 0.750 | −9.906 | 235.58 | 86.51 |
| cold-1 | 6.489 | 39.760 | 969.05 | 339.89 |
| cold-2 | 31.663 | 23.713 | 1272.95 | 283.23 |
| shape-low | 27.527 | −51.477 | 1569.91 | 426.44 |
| shape-high | 8.639 | 2.355 | 316.50 | 57.56 |
| shape-all | 36.915 | 4.129 | 1334.45 | 233.85 |

The saved constant band gaps at the all-training time center range from approximately −24.01 to −18.85 kHz for RX0 and +29.70 to +38.36 kHz for RX1, inside the original group-offset bounds ±ALIAS/2 (approximately ±113.64 kHz). Both half donors have c=0, so these particular targets contain no independent low/high RF slope difference. Their differing time slopes are an observed seed-function property, not evidence of a hardware switch or true satellite identity.

Original projection bounds are drift ±60 Hz/s, common c ±5000 Hz/GHz, clock coefficients ±2000 Hz, and group offsets ±ALIAS/2. The saved all-view projections mark clock coefficients active for cold-1 (index 18) and shape-low (15,18,20); the other four mark none active. Their near-bound coefficients are only 4.55e−13 Hz inside ±2000. Basis coefficients bound the clock representation; individual interpolated clock knots can exceed 2000 Hz. Existing receipts alone do not quantify how much bootstrap loss arises from bounds versus the missing band/time basis.

## Native C discards a different, already represented function

The physical export serializes the projected correction as receiver affine terms, common RF c, group offsets and clock knots. Its ≤7.28e−12 Hz source closure checks that represented function, not the original low/high bootstrap target (`src/leo/analysis/research/doppler_shape_shared_proposals.py:17–72`; `src/leo/analysis/frozen_group_calibration.py:68–100`). A tiny closure therefore does not erase the preceding 236–1570 Hz target loss.

`src/leo/analysis/joint_association_projection.py:8–112` evaluates that physical function at exact native candidate times/RFs. Every original window has unit total weight over its available candidates. It analytically removes/restores receiver means, then projects onto two receiver slopes, common RF c and constant group offsets. Model C has no shared-clock coefficients. Integer receiver alias lifts are applied after this continuous projection and do not explain its residual shape.

All six native all-view projections have `active_bounds=[]`; their weighted receiver residual means are ≤4.52e−12 Hz in magnitude. Their 57.56–426.44 Hz RMS residuals, with maxima 218.27–4375.41 Hz, consequently are not simply discarded receiver constants or active native coefficient clipping. Affine/RF/group components have already been refitted during projection. The saved nonlinear shared-clock functions generally exceed the lean native model's representational capacity. The final C fit can change its existing calibration, geography, satellite timing and marginalized assignments, but cannot restore an arbitrary clock curve through absent clock columns.

These observations identify structural approximation, not truthful clock correction. Calibration functions themselves arose from candidate-dependent bootstrap fits. In the completed location run, shape-low—the largest target-loss and native-loss proposal—still won C-all's training objective; A-all selected shape-high and B-all selected cold-0. Projection RMS is neither a localization ranking nor an accuracy proxy. Injecting a full kilohertz donor residual into a reoptimized winner would not falsify the missing-dimension hypothesis: final calibration/timing/assignments have already changed.

## Prespecified next diagnostic: saved-function decomposition

The smallest informative next step is algebraic classification of all six saved functions, before another location fit. Evaluate each original low/high target and exported function at the original training timestamps, and each exported function at the exact native timestamps. Reproduce the original bounded projection; compare its fitted correction with an unbounded projection onto the identical scaled columns. Then append only the two derived receiver/group-times-time columns for the bootstrap target, and the original receiver shared-clock basis for native transport. Report bounded/unbounded RMS and maxima, correction differences, original-bound violations in the unbounded solution, weighted receiver means, rank/singular-value diagnostics, and absolute/relative closure for the expanded spaces. Errors are evaluated against prescribed saved functions, not measured Doppler or a reference coordinate. Expanded columns are a capacity diagnostic, not an approved new nuisance model or prior.

Proposed API: `diagnose_seed_functions(case, all_view_exports, bootstrap_receipts, native_seeds)` returns six ordered decompositions and their source/frame/row/weight bindings. A separate qualified runner binds the successful initialization/model terminals and live/archive sources, consumes training only, and seals the results. Ceiling: 12 original bounded calibration projections and 24 unbounded/expanded linear solves; zero orbit predictions, likelihood evaluations, gradients or location optimizations. Internal cap 90 seconds including preparation; external TERM105/KILL110. Preserve original column scales and receiver-mean gauges. Use the original exact least-squares rank convention, record its explicit tolerance and retained singular values, and refuse nonfinite data or failed bounded replay rather than regularizing or silently changing rank.

If the expanded spaces close the saved targets and the unchanged spaces do not, that establishes which function dimensions were discarded and whether bounds contributed. It does not establish that those functions should be fitted to data, or that adding them improves position accuracy. Any later normalized perturbation at a frozen fitted state would be a separate frequency-sensitivity experiment, with no interpretation as a calibrated accuracy result.

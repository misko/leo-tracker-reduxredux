# DS23-0268: association recovery, uncertain identity, and receiver geometry

The retained causal prototype associates **2,316 of 3,165 original winning GLRT observations (73.175%)**, across 64 graph tracks and 17 satellite labels. Both `c = 0` and fitted-`c` pass the original curved and predictive residual gates. All 2,254 observations in the earlier 71.216% result are retained. No extra GLRT peak is counted in the numerator. These are model-compatible associations, not independently confirmed transmitter identities.

**The evidence does not establish that every 53923 assignment was wrong.** Assigning the disputed RX1 family to 67953 improves the joint RF objective, but assigning the whole disputed family on both receivers to 67953 also passes. Those alternatives have close RF bounds. Their different position errors cannot be used to choose a transmitter identity.

This is single-scan development. It has not been promoted to ALGO02/ALGO03 or validated as a general correction. No new RF collection, post-scan TLE, or evaluation coordinate enters these fits. Position error is calculated only by the reporter. The regional cold start remains the centre of the original 25 × 25 km box.

## Recovery and what had failed

| Retained stage | Original GLRT associated | Association | Tracks | Position error, c0 / fitted-c |
|---|---:|---:|---:|---:|
| Receiver-step / family-reentry starting point | 2,111 | 66.70% | — | 5.359 / 5.485 km |
| Finer receiver basis, intact CH7 curve → 64333 | 2,171 | 68.59% | — | 5.216 / 5.273 km |
| Recover 66797 jointly with original gates | 2,254 | 71.22% | 63 | 3.867 / 3.636 km |
| RX1 disputed family → 67953; RX2 retained as 53923 | 2,254 | 71.22% | 63 | 1.240 / 0.943 km |
| Same split, add intact 62-point RX1 CH2 curve → 67953 | **2,316** | **73.18%** | **64** | **1.577 / 1.343 km** |

Three specific mechanisms explain these recoveries:

1. **Receiver covariance was too coarse for the CH7 curve near 150 s.** Replacing the 30-second-spaced receiver basis by a 10-second-spaced, 15-second-width basis recovers the intact 60-point curve as causal 64333. Average pointwise prior variance is preserved on the fixed 0–300 s grid; the marginal likelihood still penalizes flexibility. An affine correction did not solve this case. Independent-family transfer has a limitation: leaving out 64908 loses the local all-gate pass, so a purely instrumental explanation is not uniquely proved.
2. **The objective optimizer could settle outside the residual gates.** Recovering the 66797 curves originally made an existing CH5 slope statistic reach 3.021 against its limit of 3. Constrained refinement uses the same objective, priors and original gates, with a stricter 0.01 normalized interior margin. It retains 67 curved observations and 16 frozen-extension observations. Gate thresholds are not loosened.
3. **Satellite identity and receiver calibration were coupled.** Changing only the disputed curved tracks left related RX1 predictive fragments assigned to the old family. Updating both curved and predictive nominations, followed by phase-refreshed constrained fitting, yields jointly compatible alternatives. Predictive linear tracks still do not update the radio calibration coefficients.

All ten earlier 53923 graph tracks are single polynomial pieces. A multi-piece graph join is not demonstrated as this failure's cause. A single polynomial can still contain mixed or erroneous GLRT observations; piece count alone cannot certify an emitter.

![Original winning GLRT: retained identity, reassigned, added and unassociated](../2026_10_20_ds23_0268_visibility_reentry/accepted_split_73percent_GLRT.png)

There are **849 remaining observations: 470 in graph tracks and 379 outside every graph track**. The largest remaining graph component is RX2 CH5 T001: 53 points from 222.668 to 261.342 s. The next is RX2 CH4 T001: 46 points from 150.233 to 193.531 s. They are not declared clutter by this investigation.

## How uncertain is 53923?

The following three comparisons use the same earlier 71.216% observation set, powers, aliases, physical priors and search budgets. Each passes both c arms. The RF bound is a negative-twice variational bound; lower is better, but its differences are not calibrated identity probabilities.

| Identity hypothesis | Satellites | RF bound c0 / fitted-c | Position error c0 / fitted-c |
|---|---:|---:|---:|
| Keep earlier 53923 assignments on both RXs | 16 | 19560.662 / 19571.100 | 3.867 / 3.636 km |
| RX1 → 67953, RX2 → 53923 | 17 | **19519.402 / 19530.978** | 1.240 / 0.943 km |
| Whole disputed family → 67953 | 16 | 19523.522 / 19535.687 | 1.542 / 1.450 km |

The split improves the RF bound by 41.260 / 40.122 compared with keeping 53923 throughout. Its advantage over the whole-family 67953 alternative is only **4.120 / 4.709**. The latter also preserves a common identity across receivers. We should retain that competing explanation, especially given the raw waveform evidence below.

With the extra CH2 curve, both alternatives reach 73.175%. The split has 17 labels and 1.577 / 1.343 km error; the whole-family variant has 16 labels and 1.811 / 1.724 km error. Their RF-bound difference is 5.186 / 6.398. Bounds from these enlarged masks must not be compared directly with the 71.216% masks.

![Coverage, position and matched RF-bound comparisons](identity_comparison.png)

A family-excluded whole-catalogue search tests all 1,402 causal candidates. The RX1 pair prefers 67953 while the RX2 quartet prefers 53923. However, that diagnostic fit fails other retained gates and does not integrate calibration uncertainty in its proposal score. It motivates hypotheses rather than proving identities. The earlier screen using calibration learned with 53923 already included favored 53923 more strongly: this is a concrete example of calibration/identity feedback.

![Same disputed points under three compatible models](disputed_track_residuals.png)

The six residual panels illustrate why a visually good Doppler fit is insufficient: much of the residual behavior is nearly identical under the different identities after each model jointly adjusts its shared nuisance coefficients.

## Independent recorded-waveform control

At 242.3543972 s, simultaneous CH1 data have a shared residual component after deterministic pilot removal, inter-frame trend removal and a matched alias/frequency search. The residual coherence is 0.001180 versus a strongest shuffled-frame control of 0.000374. Whole-probe carrier coherence is 0.001385. The relative carrier is **−11,921.848 Hz modulo the 227,272.727 Hz pilot alias**, with a 5 Hz leave-one-frame-out span. Shared nonlinear pilot-frame phase and amplitude behavior also occur in this window.

This supports a shared received component, not a unique NORAD identity or proof that both winning GLRT peaks are the same emitter. Common pilot structure, an additional weaker common emitter and receiver effects remain possible. Other examined windows have much less stable carrier estimates (90–395 Hz leave-frame-out spans).

As an exploratory control, condition the **existing** Gaussian radio offset/drift prior on that differential measurement, preserving its full correlated covariance. Add no drift coordinate, no satellite-specific measurement term and no extra associated GLRT point. Use 100 Hz and 300 Hz engineering sensitivity scales; the 5 Hz jackknife range is not treated as calibrated uncertainty. Linear tracks never set this measurement. Its errors are not proven independent of the GLRT errors because both use existing IQ.

All six matched constrained trials pass, and each preserves the 2,254-point, 63-track association result. For fitted-c:

| Measurement scale | Identity | RF bound | Measured minus fitted RX2−RX1 | Position error |
|---|---|---:|---:|---:|
| 100 Hz | earlier 53923 | 19583.705 | −36.2 Hz | 3.956 km |
| 100 Hz | receiver split | **19544.836** | +21.4 Hz | 1.049 km |
| 100 Hz | whole-family 67953 | 19548.331 | −9.8 Hz | 1.450 km |
| 300 Hz | earlier 53923 | 19584.647 | −121.5 Hz | 3.746 km |
| 300 Hz | receiver split | **19545.045** | +85.4 Hz | 0.989 km |
| 300 Hz | whole-family 67953 | 19549.285 | −32.4 Hz | 1.450 km |

Compare RF bounds only within a measurement-scale group. The single anchor **does not resolve** the competing identities or improve localization relative to the corresponding unanchored split. It remains a diagnostic, not a production calibration or a generalized result.

![Single-window calibration sensitivity](calibration_sensitivity.png)

An initial implementation mistakenly passed the pilot search's unwrapped +3-period carrier into an absolute Gaussian contrast. That run was stopped and marked [invalid](../2026_10_20_ds23_0268_radio_calibration/invalid_run.json). The corrected experiment has a separate directory, an alias-invariance regression test and a zero-centred radio-gauge convention. The absolute alias branch is not independently identified. No invalid-run number enters the tables above.

## Sky geometry: every associated observation checked

The new audit independently propagates **nominal causal TLEs at original observation timestamps**, with no fitted phase/orbit correction, for all five retained identity/coverage variants and both c arms. The catalogue's TLE epochs and collection timestamps all precede the scan cutoff. The recording radio matches the station authority and its validity interval. Every associated original observation is covered exactly once.

For the 73.175% split:

- All 2,316 points across all 17 labels are above the horizon: minimum nominal elevation **34.060°** in c0 and **34.062°** in fitted-c.
- None is behind its nominal feed axis; maximum off-axis angle is **48.062° / 48.048°**.
- Eight c0 points and seven fitted-c points exceed 45° off-axis. That angle is a sensitivity reference, not a measured beam threshold.
- The whole-family 67953 alternative also passes the nominal horizon/front-axis audit. Sky visibility does not discriminate the two identities here.

![All 17 associated satellite directions by receiver](../2026_10_20_ds23_0268_visibility_reentry/sky_split_73percent_c0_nominal.png)

The station authority gives RX1 west and RX2 east, with provisional connector mapping. The mount's nominal outward tilt implies 70° axis elevation for a level base, hence only **40° between the two feed axes**. A satellite near zenith can therefore appear on both receivers. Treating them as disjoint east/west sky hemispheres would be incorrect.

Installed boresights, base pose, beam pattern, phase-centre baseline and obstructions are unmeasured. Observer altitude is assumed to be zero metres. Thus **nominal horizon and forward-axis consistency are verified; actual antenna visibility cannot yet be certified**. No invented antenna-width veto enters association.

## Recommended interpretation and next discriminator

Retain the 73.175% model-compatible coverage result as a prototype. Keep the receiver-split and whole-family alternatives explicit rather than publishing a uniquely confirmed 53923 correction. The useful algorithmic changes are a prior-normalized receiver covariance, coherent family-wide nomination updates, and gate-aware refinement. Their generalization needs a frozen multi-scan evaluation.

The next useful identity discriminator is repeated, RF-only-qualified differential receiver measurements on multiple curved tracks and times, with alias branches and uncertainty treated explicitly. One common component at one epoch cannot establish which family generated every dominant peak. If an independent measured antenna response becomes available, it could supply a further likelihood, rather than a guessed hard visibility gate.

## Reproduction and receipts

Run `.venv/bin/python` with `PYTHONPATH=/tmp/algo03-feasible-deps:src:tools`, `OPENBLAS_NUM_THREADS=1`, and `OMP_NUM_THREADS=1`.

1. `tools/probe_ds23_0268_radio_calibration.py --stage verify`: all six disabled-calibration endpoints reproduce their earlier RF bounds exactly.
2. The same driver `--stage run`, then `--stage constrained`: six matched c pairs per stage; all constrained jobs terminal without errors.
3. `tools/report_ds23_0268_identity_resolution.py --stage figures`, then `--stage calibration`: report-side geographic evaluation, original membership checks and direct nominal sky audit.
4. `tools/verify_ds23_0268_selected_result.py --proposal selected_split_all_RX1_with_CH2_constrained`: fresh independent 73.175% replay of curved gates, predictive gates, extension membership and nominal sky geometry.

Focused mathematical, waveform, event, identity and geometry tests: **23 passed**, including five calibration-factor tests. Frozen original ALGO02 source verification passes.

[Matched identity table](identity_comparison.csv) · [All-model sky audit](nominal_sky_audit.json) · [Per-observation sky directions](nominal_sky_points.csv) · [Calibration sensitivity and replay](calibration_evaluation.json) · [Calibration protocol](../2026_10_20_ds23_0268_radio_calibration_principal/protocol.json) · [Completed constrained trials](../2026_10_20_ds23_0268_radio_calibration_principal/constrained_execution.json) · [Raw waveform diagnostics](../2026_10_20_ds23_0268_shared_waveform/curved_pair_waveform_analysis.json) · [Earlier recovery details](../2026_10_20_ds23_0268_visibility_reentry/verification_followup.md)

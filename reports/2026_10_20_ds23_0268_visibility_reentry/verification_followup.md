# DS23-0268: 73.18% association and receiver-dependent satellite identity repair

Audit time: 2026-10-20T06:35:22.704603+00:00. This follow-up replays saved scientific fits, adds a direct nominal-SGP4 sky check, and tests family-excluded calibration and identity proposals. It does not replace the default algorithm or demonstrate generalization to other scans.

**The new accepted RX1/RX2 split reaches 2,316/3,165 original GLRT points (73.175%), 64 tracks and 17 satellite labels in both c arms.** It retains all 2,254 previously accepted observations, relabels 100 RX1 points from 53923 to 67953, adds the 62-point CH2 curve to 67953, and leaves 849 points unassociated. No original graph track is rebuilt or split. The unchanged residual, alias, horizon, support and predictive gates all pass after constrained optimization.

![Latest GLRT association and identity changes](accepted_split_73percent_GLRT.png)

The earlier retained candidate has **2,254/3,165 original winning GLRT points (71.216%)**, 63 tracks and 16 satellite labels in each matched c arm. All 2,111 earlier associated points are retained: 143 added, zero lost, zero additional peaks counted in the numerator. Fresh replay reproduces the full RF objective, retained curved gates, predictive gates and extension membership. The 911 remaining points remain unassociated.

| Earlier accepted candidate | c = 0 | fitted c |
|---|---:|---:|
| Position error, km | 3.867 | 3.636 |

Higher coverage is not accurate localization. GPS is used only by this reporter, never for fitting, candidate nomination or acceptance. No future TLE or new RF collection is used.

## Recovery mechanism

The receiver-step/family-reentry baseline reaches 66.70%. A finer receiver basis with matched average pointwise prior variance recovers the intact 60-point CH7 curve as 64333, reaching 68.59%. Restoring both 66797 curves adds 67 curved points; a frozen-calibration extension adds 16 more. The unconstrained c0 solution narrowly fails a retained slope gate (3.021 versus 3). The retained candidate minimizes the same RF objective subject to the original gates, with a stricter 0.01 normalized interior slack. This changes optimization, not the acceptance thresholds. Original observations and graph pieces are retained.

## 53923 identity: what is and is not established

The original whole-catalogue screen favors 53923 for all six curved tracks, but its receiver calibration was jointly learned with those tracks. As a control, remove every 53923 curved and predictive factor and refit position and calibration from the same regional cold start and unchanged remaining priors. The disputed measurements are used only after this fit to screen all 1,402 causal candidates across shared phases from -15 to +15 seconds, spaced by 0.25 seconds. Nominal candidate orbits are compared; no candidate-specific orbit modes or phase prior enter these proposal scores.

| c arm | Disputed group | 53923 score | 67953 score |
|---|---|---:|---:|
| c0 | RX1 | 140.3 | 90.6 |
| c0 | RX2 | 277.9 | 774.7 |
| c0 | all_six | 877.7 | 865.3 |
| fitted_c | RX1 | 138.4 | 89.9 |
| fitted_c | RX2 | 259.1 | 822.2 |
| fitted_c | all_six | 845.4 | 912.1 |

The RX1 pair favors 67953 in both c arms; RX2 favors 53923. The all-six winner changes between c arms. This exposes calibration/identity coupling and supports keeping the split as a hypothesis. It does not prove either identity: the family-excluded fit itself fails retained 63901 gates, and these conditional proposal scores omit calibration uncertainty. Neither all-six nominal candidate passes every local gate. All ten currently accepted 53923 graph tracks have a single polynomial piece, so a multi-piece graph join is not demonstrated as the explanation.

![Family-excluded candidate comparison](identity_family_excluded_comparison.png)

## Joint test of the receiver split

Next, starting from the accepted 71.216% observation mask, change the two RX1 curved nominations to 67953 while retaining the RX2 quartet as 53923. Test both with and without the additional 62-point CH2 curve proposed for 67953. Keep all earlier calibration and predictive observations, priors, gates, c-arm matching and cold 5-by-48 search budget. The all_RX1 variants also change the retained RX1 CH4 and CH6 predictive fragments to 67953: four earlier tracks containing 100 points change identity. The constrained variants refine each cold proposal for five phase rounds with at most 40 position steps per round, requiring a 0.01 interior margin on the unchanged gates. Geographic errors below are diagnostics, not trial selectors.

| Proposal | Paired gates | Failed curved c0 / fitted c | Failed predictive c0 / fitted c | Position error c0 / fitted c, km |
|---|---|---:|---:|---:|
| selected_split_RX1 | FAIL | 2 / 2 | 1 / 1 | 2.167 / 2.080 |
| selected_split_RX1_with_CH2 | FAIL | 2 / 2 | 1 / 1 | 2.247 / 2.171 |
| selected_split_all_RX1 | FAIL | 2 / 2 | 0 / 0 | 2.177 / 2.143 |
| selected_split_all_RX1_with_CH2 | FAIL | 2 / 2 | 0 / 0 | 2.257 / 2.218 |
| selected_split_RX1_constrained | FAIL | 2 / 2 | 1 / 1 | 6.161 / 5.279 |
| selected_split_RX1_with_CH2_constrained | FAIL | 3 / 3 | 0 / 1 | 6.081 / 5.135 |
| selected_split_all_RX1_constrained | PASS | 0 / 0 | 0 / 0 | 1.240 / 0.943 |
| selected_split_all_RX1_with_CH2_constrained | PASS | 0 / 0 | 0 / 0 | 1.577 / 1.343 |

selected_split_RX1 c0 failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_RX1 fitted_c failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_RX1_with_CH2 c0 failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_RX1_with_CH2 fitted_c failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_all_RX1 c0 failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_all_RX1 fitted_c failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_all_RX1_with_CH2 c0 failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_all_RX1_with_CH2 fitted_c failed curves: DS23-0268-RX1-CH1-T002-RF10940312500.000000, DS23-0268-RX1-CH7-T001-RF12440312500.000000.

selected_split_RX1_constrained c0 failed curves: DS23-0268-RX1-CH4-T006-RF11690312500.000000, DS23-0268-RX1-CH5-T005-RF11940312500.000000.

selected_split_RX1_constrained fitted_c failed curves: DS23-0268-RX1-CH4-T006-RF11690312500.000000, DS23-0268-RX1-CH5-T005-RF11940312500.000000.

selected_split_RX1_with_CH2_constrained c0 failed curves: DS23-0268-RX1-CH2-T005-RF11190312500.000000, DS23-0268-RX1-CH4-T006-RF11690312500.000000, DS23-0268-RX1-CH5-T005-RF11940312500.000000.

selected_split_RX1_with_CH2_constrained fitted_c failed curves: DS23-0268-RX1-CH2-T005-RF11190312500.000000, DS23-0268-RX1-CH4-T006-RF11690312500.000000, DS23-0268-RX1-CH5-T005-RF11940312500.000000.

selected_split_all_RX1_constrained c0 failed curves: none.

selected_split_all_RX1_constrained fitted_c failed curves: none.

selected_split_all_RX1_with_CH2_constrained c0 failed curves: none.

selected_split_all_RX1_with_CH2_constrained fitted_c failed curves: none.

The whole-RX1 constrained alternatives pass both c arms. On the matched original observation mask, the split's negative-twice RF bound is 19519.402 / 19530.978, versus 19560.662 / 19571.100 before: gains of 41.260 / 40.122 with unchanged observations, powers and search constraints. Its position error is 1.240 / 0.943 km, versus 3.867 / 3.636 km. This supports the split independently of GPS scoring. It does not establish a unique physical transmitter identity.

Adding CH2 raises association to 73.175% with 1.577 / 1.343 km error. Its raw bound must not be compared to a different observation mask. Coverage favors this branch; the higher-coverage branch does not yield the smallest position error. The successful repair needed the RX1 predictive fragments to change family as well as the curved pair, followed by gate-constrained refinement; changing the curved pair alone leaves inconsistent predictive evidence. The receiver-specific identity split is a better-supported explanation than blaming a graph join or declaring all 53923 evidence incorrect. RX2 retains its 53923 assignment.

## Direct sky verification

Every associated observation is propagated directly from its nominal causal TLE at its original measurement time using SGP4, with **zero fitted phase/orbit correction**. Every catalogue element's epoch and collection timestamp precedes the scan cutoff. The station authority matches the recorded radio and is valid at the scan time. Its receiver-ID mapping supplies RX1 west / RX2 east; for a level mount, the nominal 20-degree outward tilt implies 70-degree elevation. Connector mapping remains provisional; installed elevation, beam width and obstructions are unmeasured. The sky calculation assumes zero-metre observer altitude; actual altitude is unavailable.

For the latest 73.175% model at the c0 RF estimate all 2,316 associated points are above the horizon; minimum elevation is 34.060 degrees, maximum nominal off-axis angle 48.062 degrees, and none is behind the nominal feed axis. The fitted-c audit gives the same conclusion. An evaluation-only check at the supplied coordinate gives 34.092 degrees minimum elevation and 47.995 degrees maximum off-axis angle. This coordinate never feeds back into inference.

Eight nominal-TLE points exceed 45 degrees off-axis in c0 (seven in fitted-c). The earlier adjusted-orbit audit's four-point count uses fitted phase/orbit corrections, so it is a different sensitivity calculation. Neither 45 degrees nor any other unmeasured beam width is used as a selection threshold.

| Satellite | Points RX1 / RX2 | Nominal minimum elevation | Nominal maximum off-axis |
|---|---:|---:|---:|
| 53923 | 0 / 268 | 59.99° | 35.46° |
| 54873 | 0 / 42 | 61.41° | 14.62° |
| 59328 | 0 / 42 | 59.49° | 14.35° |
| 60415 | 80 / 97 | 58.89° | 36.70° |
| 61977 | 125 / 0 | 48.89° | 35.49° |
| 63901 | 91 / 0 | 45.41° | 48.06° |
| 63913 | 85 / 0 | 50.84° | 46.80° |
| 64333 | 60 / 0 | 51.17° | 27.82° |
| 64908 | 213 / 54 | 39.16° | 42.22° |
| 64923 | 306 / 0 | 42.58° | 27.77° |
| 64925 | 206 / 0 | 43.09° | 26.92° |
| 66797 | 83 / 0 | 34.06° | 36.21° |
| 66812 | 31 / 0 | 40.98° | 29.03° |
| 67935 | 99 / 23 | 38.45° | 37.28° |
| 67953 | 162 / 0 | 62.11° | 41.86° |
| 68343 | 159 / 0 | 44.44° | 38.83° |
| 69445 | 36 / 54 | 40.27° | 45.44° |

![Direct nominal sky directions through time](selected_split_all_RX1_with_CH2_constrained_direct_nominal_sky_time_audit.png)

![All 17 nominal satellite directions by receiver](sky_split_73percent_c0_nominal.png)

Horizon visibility is verified. Reception within a measured antenna beam cannot be certified from the available pose and pattern records. The near-zenith overlap of the two axes makes seeing the same satellite on both receivers plausible.

## Evidence and reproduction

Run the repository venv with `PYTHONPATH=/tmp/algo03-feasible-deps:src:tools` and single-thread BLAS. Scripts: `tools/verify_ds23_0268_selected_result.py`, `tools/probe_ds23_0268_identity_holdout.py`, `tools/probe_ds23_0268_selected_identity_split.py`, and this reporter. Completed identity trials refuse to overwrite prior results. The first nominal screen attempt was interrupted after noticing it omitted the event-aware hardware wrapper; its fit was retained and the corrected screen rerun. No output of that interrupted screen was accepted. The event-aware subtraction has a regression test. Seventeen focused tests pass, including family exclusion, native polynomial plotting, membership and receiver geometry checks.

[Latest independent replay receipt](selected_split_all_RX1_with_CH2_constrained_independent_replay_audit.json) · [Latest per-point nominal angles](selected_split_all_RX1_with_CH2_constrained_direct_nominal_sky_points.csv) · [Family-excluded fit](identity_family_excluded_fit.json) · [Family-excluded catalogue ranks](identity_family_excluded_screen.json) · [Accepted 71% split](selected_split_all_RX1_constrained.json) · [Accepted 73% split](selected_split_all_RX1_with_CH2_constrained.json) · [Coverage and ownership](accepted_identity_split_coverage.json) · [Earlier recovery report](README.md)

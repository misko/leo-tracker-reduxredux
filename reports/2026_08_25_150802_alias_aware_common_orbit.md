# 150802 alias-aware common-orbit audit

The training-only common winner was **STARLINK-31640 / 59748** at
+2.50 s. Aggregate train/holdout RMS was
90.42/158.15 Hz; the training runner margin was
1.09 Hz. The numerical identity gate
**failed**.

- PASS — `rx1_unique_strict_alias`
- PASS — `rx0_unique_strict_alias`
- PASS — `lossless_single_counter_segment`
- PASS — `selected_candidate_train_visibility_eligible`
- PASS — `selected_candidate_holdout_visibility_eligible`
- PASS — `selected_candidate_full_visibility_eligible`
- FAIL — `epoch_interior`
- FAIL — `every_member_orbit_beats_best_polynomial`
- PASS — `aggregate_orbit_holdout_rms_at_most_500_hz`
- FAIL — `aggregate_radio_null_advantage_at_least_100_hz`
- FAIL — `aggregate_orbit_beats_shared_curvature_null`
- FAIL — `training_runner_margin_at_least_100_hz`
- FAIL — `train_selected_identity_beats_every_alternative_on_holdout`
- FAIL — `heldout_alternative_margin_at_least_100_hz`
- PASS — `catalog_identity_stable_at_0_25_200_hz_s_drifts`
- FAIL — `epoch_adjustment_stable_at_0_25_200_hz_s_drifts`
- PASS — `forty_matched_wrong_time_fields_complete`
- FAIL — `identity_calibration_eligible`
- FAIL — `matched_wrong_time_identity_empirical_p_at_most_0p05`

The raw diagnostic matched wrong-time p-value was 0.04878, but identity calibration was not applicable because hard pre-calibration gates failed. The raw diagnostic p-value cannot indicate identity specificity.

## Interpretation limit

RX0 and RX1 are channels of the same Pluto and share a sample clock. This is channel
replication, not independent-instrument confirmation. Both trajectories and the RX1 direct
rows were selected using their full spans before this retrospective split. Even a numerical
pass would remain candidate-only and cannot promote a named physical transmitter identity.

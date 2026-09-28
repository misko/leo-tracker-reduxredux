# Calibration association consistency audit

This is a read-only audit of the six topology-filtered calibration scans. It compares the original Gaussian top-3 associations used to construct the reception-model direction features with the final robust Student-t fixed-point associations. It uses no development or confirmation outcomes.

All 344 retained tracks join exactly after excluding the 10 tracks named by the calibration topology audit. The original artifact contains 354 calibration tracks; the robust artifact contains exactly the expected 344. Candidate IDs and probabilities are internally constant within every original track.

## Results

- MAP satellite identity agrees for 324/344 tracks (94.19%), or 94.47% when tracks are weighted by occupied seconds.
- The old MAP remains in the robust top three for 98.55% of tracks; the robust MAP remains in the old top three for 98.26%.
- Only 202/344 tracks (58.72%) have the same unordered top-three set, and 164/344 (47.67%) preserve the same order.
- Mean probability total-variation distance is 0.06997 per track and 0.06309 under occupied-second weighting. Its median is only `3.93e-11`, while the 20 MAP-changing tracks have mean TV 0.9740. The discrepancy is therefore concentrated rather than a small diffuse change.
- Session `scan-fw-c559f436d578c9bd` has the largest discrepancy: 46/52 retained MAPs agree and occupied-second-weighted mean TV is 0.1250. Session `scan-fw-aa9770c66396e928` has 55/55 MAP agreement.

These results show that the old reception calibration and robust frequency model use materially different satellite associations for a minority of tracks. They do not establish how much the fitted direction feature would move.

## Direction comparison limitation

A numerical old-versus-robust direction-feature comparison is not identifiable from the frozen artifacts. `model_rows.json` preserves only the old probability-marginalized `east` and `up` value for each reception row. `topology_frequency_fixedpoint.json` preserves robust candidate IDs and weights, but not each candidate's east/up vector at the corresponding observation time. Reconstructing those values would require new candidate propagation, outside this audit.

The minimum sufficient future extraction is candidate-specific east/up for every robust shortlist member at each reception `observation_id` (or aligned `observation_utc_ns`), plus the explicit weight-marginalization convention. Until then, MAP/weight inconsistency is measurable but its reception-model directional impact is not.

Exact artifact paths, SHA-256 digests, definitions, weighting, per-session values, and binding checks are in `calibration_consistency_report.json`.

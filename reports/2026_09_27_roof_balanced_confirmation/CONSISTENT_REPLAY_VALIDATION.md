# Paired replay validation

Before interpreting the new calibration's geographic output:

- Reverified all seven source bindings of `calibration_consistent_calibration.json`.
- Verified the independently reconstructed old reception model matches frozen metadata exactly and coefficients to within 1.12e-15. Runner tolerance is 1e-12 for coefficients and 1e-14 for ratio variance; this permits numerical roundoff, not a model change.
- Added an evaluator-level comparison against the original robust evaluator, including reordered candidate IDs, unequal occupied-second track weights, and repeated-point caching. The original and paired scores agree to 1e-12.
- Corrected the new reporter's handling of full selected rows versus lightweight grid rows. The original selected rows contain additional per-track diagnostics; all shared fields must still match.
- Exercised the corrected reporter on identity replays constructed from all eight existing branches (2,312 actual saved points). All branches passed without reading reference coordinates. This validates the actual source schema but does not stand in for the running new-calibration experiment.
- The report-directory test suite passed: 42 tests. These cover scorer parity, finite inputs, exact inventories, deterministic selection, reference-report gating, and calibration joins among other experiment checks.

The four actual paired replays were launched separately with one compute thread each. Their producer is frozen while they run. Per-point old-versus-saved parity and unchanged Doppler scores must pass before any finished replay is accepted. The whole-cohort reporter then verifies bindings and selections independently before calculating distances.

No location-improvement conclusion follows from these software checks. Final results require all four completed real replays and their validated distance report. No production estimator or original frozen model was changed.

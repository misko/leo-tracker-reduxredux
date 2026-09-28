# First-eight cached-input metadata audit

This is a read-only audit of the first eight chronological cached exports and
banks. No IQ, score, reference, pose, or new preparation was used.

## Result

No concrete timestamp, visit-index, bank-shape, or binding defect was found.

- All 488 exported tracks have equal time, visit, and mask vector lengths;
  visit indexes are strictly increasing within every track; all times fall
  inside the approximately 302-second capture interval.
- The public projection computes support UTC from the qualified first-sample
  estimate plus integer-counter-relative sample position, with each track time
  defined as support-center UTC minus that same session start. The exporter
  independently checks equality to the prepared numerical times to 1 ns.
- Every bank binds its session and source manifest to its observation export.
  For every eligible track, candidate-id, position, and velocity array shapes
  match the 41-point `-5` through `+5` second timing grid and the observation
  count. The causal baseline snapshot changes only between sessions four and
  five, consistently in export and bank metadata.
- All tracks carry a single receiver, channel, and RF lane. Across the first
  eight there are two receivers and 24 receiver/lane groups; no non-finite
  exported CFO value was found.

The checked public path preserves scanner `fractional_tracking_cfo_hz` as the
exported measurement and carries `actual_rf_hz` separately. The bank builder
uses the declared fixed 11.2 GHz prediction convention. Thus there is no hidden
per-track RF rescaling or mixed-unit conversion in these artifacts. Any later
cross-lane physical-frequency interpretation would need an explicit
normalization policy; it is not supplied by this frozen export/bank contract.

The eighth chronological capture was included only as an ordinary member of
the eight; no outcome artifact was read.

## Evidence checked

- `tools/ds7_export_baseline.py`
- installed public `leo.application.scanner_trajectory` and
  `leo.operations.adaptive_tle_position_inputs` source
- first-eight track exports, bank manifests, and compressed bank array shapes
- `reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json`

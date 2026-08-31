# Production dual 2.5/25 MS/s PSS replay artifacts

The interpretation and capture-integrity accounting are in
[`reports/2026_08_31_production_dual_2p5_25_pss_replay.md`](../../../2026_08_31_production_dual_2p5_25_pss_replay.md).

All outputs are candidate-only. They do not claim decoded synchronization, payload, satellite
identity, absolute carrier phase, or calibrated physical Doppler.

## Artifacts

- `pss-frame-timing-replay.json`: complete rate-generic replay for 25 MS/s RX0 and both 2.5 MS/s
  inputs, including no-result blocks and refined timing windows.
- `pss-detection-vs-time.png`: full-dwell qualification strength and block accounting.
- `pss-frame-phase-vs-time.png`: full-dwell block and refined-window frame phase.
- `pss-qualified-episode-fit.json`: per-target block medians plus exact linear/quadratic fit data
  for the coherent 2.5 MS/s RX1 episode.
- `pss-qualified-episode-fit.png`: coherent-episode fit and residuals in rate-independent time
  units.
- `source/summarize_pss_replay.py`: executed producer for the fit JSON and PNG.

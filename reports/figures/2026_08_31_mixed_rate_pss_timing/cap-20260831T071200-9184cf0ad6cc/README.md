# `071200` PSS timing and GLRT comparison artifacts

The comprehensive interpretation is in
[`reports/2026_08_31_071200_pss_timing_glrt_comparison.md`](../../../2026_08_31_071200_pss_timing_glrt_comparison.md).

The replay and every derived comparison are candidate-only. They do not claim decoded PSS/SSS,
payload, satellite identity, absolute carrier phase, or calibrated physical Doppler.

## Source replay

- `pss-frame-timing-replay.json`: complete rate-generic PSS replay.
- `pss-detection-vs-time.png`: full-dwell PSS qualification.
- `pss-frame-phase-vs-time.png`: replay frame-phase plot.

## Derived comparisons

- `pss-timing-linear-quadratic-residuals.png`: global PSS timing residuals.
- `pss-vs-classic-doppler-rate.png`: timing-derived rate versus classic GLRT segment rates.
- `pss-vs-glrt-global-fit-residuals.json` and `.png`: native timing/CFO residual comparison.
- `pss-vs-glrt-normalized-residual-overlay.png`: dimensionless residual-shape overlay.
- `pss-vs-glrt-independent-cfo.json` and `.png`: exploratory direct PSS CFO comparison.
- `pss-timing-rate-vs-glrt-cfo-residuals.json` and `.png`: derivative-based shared-Hz residual
  comparison.

The JSON files retain the exact cohorts, coefficients, residuals, accounting, method descriptions,
and limitations used to render the derived figures.

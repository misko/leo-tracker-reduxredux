# Position transfer by receiver modification

The 124 four-region queries come from 62 acquisitions. Each acquisition appears once
with its correct region offered and once with it omitted. The DS29 roof recordings
also appear in the roof comparison. StarLoc supplies 11 captures across eight nearby
site groups. The three Altrincham field windows have no usable tracks. The 40 synthetic
acquisitions are simulations. This is a retrospective replay of the original blind study.

Each dot is a returned coordinate. Each count uses all attempts in its group and offer
condition. A published coordinate is a false publication whenever the correct region was
omitted. The best-guess series show the diagnostic coordinates the receivers recorded.
Withholding can leave a best guess or no estimate. Projected fit saves its accepted
pooled point as the published coordinate. When withholding, it records a diagnostic
point if available. The four-offer controls are the original regional grid's published
and best-guess coordinates. The original v5 reference applies to the fixed roof tile.

Orbital reuse, horizon screening, track compression, projected fit, later-sample
validation and the regional grid use the same outputs in both calibration settings.
Shared Doppler has a matched zero-versus-fitted
calibration comparison. Each CSV has four rows per query and method, including attempts
without coordinates. Coordinates and truth are in degrees. Errors use the evaluation
scorer's horizontal distance in km.

## Fitted calibration

[Figure book](fitted_c/modifications.pdf) · [Query-level data](fitted_c/modifications.csv)

- [Reusing orbital states](fitted_c/orbit_interp.png)
- [Horizon screening for Doppler scoring](fitted_c/shape_score.png)
- [Compressing Doppler tracks](fitted_c/track_reduce.png)
- [Fitting position with per-track offsets removed](fitted_c/projected_fit.png)
- [Doppler fit with shared receiver and satellite corrections](fitted_c/shared_doppler.png)
- [Verify satellite assignments on later Doppler samples](fitted_c/arc_validation.png)

## Zero calibration

[Figure book](c0/modifications.pdf) · [Query-level data](c0/modifications.csv)

- [Reusing orbital states](c0/orbit_interp.png)
- [Horizon screening for Doppler scoring](c0/shape_score.png)
- [Compressing Doppler tracks](c0/track_reduce.png)
- [Fitting position with per-track offsets removed](c0/projected_fit.png)
- [Doppler fit with shared receiver and satellite corrections](c0/shared_doppler.png)
- [Verify satellite assignments on later Doppler samples](c0/arc_validation.png)

Rebuild from the saved predictions and frozen reference scores.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel transfer124 --out reports/2026_11_19_receiver_duty/transfer-figures
```

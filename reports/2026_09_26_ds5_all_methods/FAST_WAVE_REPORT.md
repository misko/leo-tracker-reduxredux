# DS5 fast point and objective-surface methods

Status: **complete**.
Inference used no surveyed coordinate. Horizontal error below was added only after the sealed inference artifact was written.

| Method | Single median / p90 (km) | Qualified singles | Group8 median / p90 (km) | Qualified group8 | Full42 error (km) | Full disposition |
|---|---:|---:|---:|---:|---:|---|
| selected-point-equal-spherical-mean | 6.525 / 18.475 | 42/42 | 7.064 / 12.402 | 5/5 | 2.229 | qualified_bounded_source_search |
| selected-point-inverse-rf-rms2-mean | 6.525 / 18.475 | 42/42 | 3.868 / 5.286 | 5/5 | 1.459 | qualified_bounded_source_search |
| selected-point-lowest-rf-rms-75pct | 6.525 / 18.475 | 42/42 | 1.990 / 8.451 | 5/5 | 2.497 | qualified_bounded_source_search |
| selected-point-spatial-trimmed-75pct | 6.525 / 18.475 | 42/42 | 2.962 / 5.255 | 5/5 | 2.362 | qualified_bounded_source_search |
| selected-point-geometric-median | 6.525 / 18.475 | 42/42 | 5.791 / 5.791 | 5/5 | 5.791 | qualified_bounded_source_search |
| selected-point-iterative-huber | 6.525 / 18.475 | 42/42 | 2.235 / 5.847 | 5/5 | 2.484 | qualified_bounded_source_search |
| surface-fusion-raw-capped-mse | 5.771 / 19.387 | 37/42 | 3.854 / 9.241 | 5/5 | 3.667 | qualified_quadratic |
| surface-fusion-delta-mse | 5.771 / 19.387 | 37/42 | 3.854 / 9.241 | 5/5 | 3.667 | qualified_quadratic |
| surface-fusion-iqr-scaled-delta-mse | 5.771 / 19.387 | 37/42 | 3.697 / 9.204 | 5/5 | 3.223 | qualified_quadratic |
| surface-fusion-fractional-rank | 5.639 / 19.296 | 38/42 | 4.715 / 8.917 | 5/5 | 4.017 | qualified_quadratic |

## Complete rate subsets

| Method | 2.5 MS/s | 5 MS/s | 7.5 MS/s | 10 MS/s |
|---|---:|---:|---:|---:|
| selected-point-equal-spherical-mean | 5.458 | 4.780 | 3.292 | 11.438 |
| selected-point-inverse-rf-rms2-mean | 4.520 | 3.425 | 4.181 | 3.195 |
| selected-point-lowest-rf-rms-75pct | 4.049 | 5.641 | 3.221 | 3.221 |
| selected-point-spatial-trimmed-75pct | 1.989 | 4.231 | 5.027 | 4.064 |
| selected-point-geometric-median | 5.791 | 5.791 | 5.791 | 6.525 |
| selected-point-iterative-huber | 4.040 | 4.384 | 5.791 | 2.753 |
| surface-fusion-raw-capped-mse | 6.346 | 4.894 | 3.372 | 4.761 |
| surface-fusion-delta-mse | 6.346 | 4.894 | 3.372 | 4.761 |
| surface-fusion-iqr-scaled-delta-mse | 6.364 | 5.563 | 3.074 | 3.077 |
| surface-fusion-fractional-rank | 4.376 | 6.729 | 4.134 | 5.652 |

## Active-time interpretation

Valid active time spans 264.96–266.64 s per scan; the range is only 1.68 s. Valid-duty fraction spans 0.8832–0.8888. The active-time strata therefore compare nearly equal exposures; the continuous correlation fields are sensitivity diagnostics, not evidence that added exposure caused an error change.

## Artifacts and interpretation

- `fast-wave-inference.json` is the sealed truth-blind result; `fast-wave-postseal.json` adds the surveyed-coordinate score.
- `fast-wave-evaluations.csv` preserves every method/unit estimate, support, qualification and runtime.
- `fast-wave-summary.csv` contains overall, sample-rate, active-time, and sample-rate × active-time summaries.
- `fast-wave-comparison.png` compares group8, rate-full, and full42 results.
- `fast-wave-error-vs-active-time.png` and `fast-wave-rate-active-matrix.png` show the requested active-time diagnostics.
- Source V2 searches are 400-point bounded searches. Their completion count, stop reasons, deferred cells and boundary state remain in every machine-readable result.

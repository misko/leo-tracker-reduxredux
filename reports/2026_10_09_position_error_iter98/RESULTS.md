# Retained-region continuation: matched c arms

Recorded status: **complete**. All position errors below are evaluation-only.
Restoring and qualifying the ordinary score-selected region reduces this scan's final error from **55.685 to 1.031 km fitted-c**, and **53.945 to 1.927 km zero-c**. The ordinary-only replay reproduces both archived endpoint vectors and objectives exactly. This establishes a single-scan rescue, not broad generalization or a production deployment.

![Position, support and frequency separately](comparison.png)

| Arm | Archived error km | Ordinary-only replay km | Candidate km | Candidate minus replay km |
|---|---:|---:|---:|---:|
| fitted-c | 55.685054 | 55.685054 | 1.030621 | -54.654433 |
| zero-c | 53.945451 | 53.945451 | 1.927094 | -52.018357 |

Baseline replay parity and operational selection:

- **fitted-c** parity: `{"vector_exact": true, "vector_max_abs_delta": 0.0, "objective_delta": 0.0, "error_delta_km": -7.105427357601002e-15}`; selection: `{"region_source": "recovered-ordinary-region", "basin": "point:-47.5:-62.5", "start": "B7", "accepted_stage": "B7", "calibration_penalty": 0.0}`.
- **zero-c** parity: `{"vector_exact": true, "vector_max_abs_delta": 0.0, "objective_delta": 0.0, "error_delta_km": -7.105427357601002e-15}`; selection: `{"region_source": "recovered-ordinary-region", "basin": "point:-47.5:-62.5", "start": "B7", "accepted_stage": "B7", "calibration_penalty": 0.0}`.

Recovered regional finals (before B7):

| Arm / start | Qualified | Error km | Objective | Failure |
|---|---|---:|---:|---|
| zero-c / association | True | 41.463862 | 40661.896695 | None |
| zero-c / zero-timing | True | 20.955908 | 46495.543692 | None |
| zero-c / own-continuation | True | 41.463862 | 40661.896695 | None |
| fitted-c / association | True | 40.607945 | 39960.280703 | None |
| fitted-c / zero-timing | True | 18.866713 | 44787.066545 | None |
| fitted-c / own-continuation | True | 40.607945 | 39960.280703 | None |

All 24 baseline/candidate B3–B7 arm-stage attempts qualify; neither replay reports a fallback reason. The candidate fitted-c B4W error is 0.826 km, but the unchanged pipeline finishes at B7 with 1.031 km. We do not select an earlier stage by reference error.

Candidate stage errors and frequency fit:

| Stage | Fitted-c error km | Zero-c error km | Fitted-c RMS Hz | Zero-c RMS Hz |
|---|---:|---:|---:|---:|
| B3 | 39.662738 | 38.654180 | 126.127 | 153.854 |
| B4 | 15.563849 | 14.754290 | 112.943 | 132.369 |
| B4W | 0.825783 | 2.039761 | 87.170 | 127.954 |
| B5 | 0.840546 | 1.890831 | 86.448 | 127.437 |
| C6 | 0.840546 | 1.890831 | 86.448 | 127.437 |
| B7 | 1.030621 | 1.927094 | 83.644 | 124.767 |

Full stage metrics, unqualified attempts, regional model-score winners and fallback reasons
are preserved in [summary.json](summary.json) and [result.json](result.json).
The model-selected result, never the smallest reference error, determines candidate outcome.
Compare objective scores only within the same physical model/bank and calibration baseline.
B3–B7 change nuisance models and satellite banks; their raw scores are not a common accuracy scale.
Frequency RMS/support effects are reported separately from geographic accuracy.

This consumed single-scan test retains ordinary candidates and uses matched c arms, priors and budgets.
Reference coordinates are read only by this report; no reference-guided seed or winner selection occurs.
No additional objective evaluation, RF collection or deployment was performed for reporting.

All 713 frozen hashes match. See [protocol](protocol.json)
and [artifact hashes](report-integrity.json).

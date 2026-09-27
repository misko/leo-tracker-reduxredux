# Reception likelihood can dominate frequency identity evidence

This audit uses the completed fixed-position diagnostic without changing any estimator, location, calibration, or track membership. Probabilities are conditional model probabilities over three shortlisted satellites, not verified physical identity confidence. All candidate log-odds decompositions were checked against the stored joint posterior; three focused tests pass.

At the mixture-selected positions, counts are identical for Sacramento and Reno:

| Recording | Reception model | Tracks changing frequency MAP to joint MAP | Of those, joint probability >99% |
|---|---|---:|---:|
| 53ce (62 tracks) | Original | 5 | 5 |
| 53ce | Matched mean | 6 | 5 |
| 53ce | Mixture | 8 | 8 |
| e76c (59 tracks) | Original | 4 | 0 |
| e76c | Matched mean | 4 | 0–1, depending on prior |
| e76c | Mixture | 5 | 4 |

At the independently fitted roof reference, the mixture also overrides seven of 62 and five of 59 tracks, respectively; all overrides have joint probability above 99%. Therefore this phenomenon is not unique to the wrong geographic estimates, and it is not by itself a correctness test.

## Examples at the Sacramento mixture-selected position

Log-evidence differences below compare the joint-preferred ID against the frequency-preferred ID. Positive favors the joint-preferred ID. Frequency includes the training prior plus reserved frequency likelihood.

| Recording / track prefix | Reserved / matched rows | Frequency ID → joint ID | Frequency log odds | Detection difference | Ratio difference | Resulting joint log odds |
|---|---:|---|---:|---:|---:|---:|
| 53ce / 4d3d82fb7ab8 | 16 / 6 | 65450 → 66900 | -47.233 | +49.484 | +15.513 | +17.764 |
| 53ce / fb3f2634abc1 | 18 / 18 | 60071 → 66900 | -7.138 | -4.345 | +47.649 | +36.166 |
| e76c / 479b1a278615 | 21 / 21 | 45212 → 67497 | -24.633 | +27.584 | +39.912 | +42.863 |
| e76c / e35267c64df2 | 21 / 19 | 45212 → 67497 | -13.113 | +1.427 | +37.525 | +25.839 |

These large likelihood ratios are mathematically consistent with multiplying per-observation Bernoulli/Gaussian likelihoods. They are not numerical evidence of a bug. However, repeated observations of one pass may share receiver gain, obstruction, transmitter-beam, matching, or other unmodeled effects. The independence assumption and fitted response variance therefore require direct calibration checks before interpreting such certainty.

This audit establishes strong reception leverage, not that the reception-selected identity is wrong or that tempering would improve locations. The next appropriate test is held-out calibration residual structure, with no use of the geographic errors to select a weight. If structured residuals are supported, a track-level latent response term or explicitly correlated likelihood is a candidate remedy to validate independently.

Artifacts: `reception-identity-overrides.json` (source hashes and every override at all fixed positions), `reception_identity_overrides.py`, and `test_reception_identity_overrides.py`.

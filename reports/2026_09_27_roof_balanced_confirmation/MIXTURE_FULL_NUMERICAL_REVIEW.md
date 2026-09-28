# Full-calibration numerical review

The separately preserved Newton-refined full fit passed all original numerical gates in 16.12 seconds. Every one of the nine saved solutions required one accepted Newton step and reached the 1e-8 target. The largest final absolute gradient was 9.08e-11. Across starts, total objective spreads were at most 6.26e-13 and prediction differences at most 9.19e-13. Original objective values reproduced exactly before refinement. No model parameters, source membership, starts, likelihood definitions, or acceptance thresholds were changed.

The preliminary raw optimization remains in `mixture-calibration-full.json`; accepted refinement is separate in `mixture-calibration-polished-full.json`. Both bind their code and inputs. All 344 calibration tracks have reception-row counts exactly equal to the frozen frequency reserve counts (6,378 observations total).

| Model | In-sample joint NLL per track | Fitted ratio variance |
|---|---:|---:|
| Direction-free M0 | 1.02662218 | 0.22282492 |
| Same-objective mean-direction M1 | 0.82163574 | 0.16219886 |
| Candidate-mixture M1 | 0.61442321 | 0.10556538 |

These are descriptive calibration-fit scores, not held-out performance or location errors. A separate direct SciPy calculation of the Bernoulli/Gaussian shared-candidate likelihood agreed with the implementation on every track for all three arms, with maximum difference 1.78e-15.

This numerical review authorizes only the already-declared conditional reception LOSO stage. It does not pass the predictive advancement gate and does not establish improved geographic resolution.

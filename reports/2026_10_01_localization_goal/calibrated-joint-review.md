# Calibrated candidate refits improve the tail, but do not replace the baseline

The frozen excluded-dataset frequency calibration improves both median and p90
error relative to the uncalibrated candidate refit. Compared with the original
all-data baseline, its p90 is better but its median is worse. Do not promote
this model or claim the localization goal achieved.

| Same 12 development scans | Median error (m) | p90 error (m) | Within 1 km | Within 3 km |
|---|---:|---:|---:|---:|
| Original all-data baseline | 1,892 | 3,998 | 1/12 | 10/12 |
| Uncalibrated candidate refit | 2,278 | 4,989 | 4/12 | 8/12 |
| Calibrated candidate refit | 2,117 | 3,534 | 3/12 | 9/12 |

All 12 calibrated fits pass, along with all 12 controls. Seven calibrated fits
improve over the uncalibrated refit, and six improve over the all-data baseline.
The three-scan pilot was followed by nine new scans using the unchanged method;
no pilot was rerun and no failures were removed or retried.

![Paired horizontal errors](calibrated-joint-panel-v1.png)

The calibrated model uses scale 43–50 Hz and signal probability .934–.939,
learned on the other two datasets. It keeps the original training likelihood,
Gaussian clock/drift/epoch priors, uniform250km Sacramento support, fixed100ftMSL
height, training-winner initialization and fixed satellite identities. It refits
position and shared nuisance terms jointly. Former checking observations now
enter fitting and must no longer be described as validation observations.

All final objectives reproduce, source/input bindings pass, and complete scalar
finite differences confirm gradients and stationarity in the fixed training
metric. Six component tests for candidate derivatives and joint search pass.
This establishes a local numerical solution, not a global optimum or calibrated
position covariance. The fitted candidate calibration remains a surrogate for
detector-selected observations, not a measured physical signal probability.

Median incremental warm runtime is 5.62 seconds, maximum 7.15 seconds; median
process CPU is 5.59 seconds. At most two fitting processes ran under the shared
lock, with 25-second internal and30-second external deadlines. Cold acquisition
and trajectory preprocessing are excluded, so these timings do not establish
the90-second end-to-end requirement. No new RF or held-out recording evaluation.

The original frozen64baseline is unchanged. Next, audit satellite-association
stability at these calibrated endpoints using the complete calibrated objective,
including candidate-set terms and shared epoch priors. Fixed identities may no
longer be preferred after this stronger frequency likelihood moves the state.
Only evidence of improving discrete alternatives justifies another bounded
refit; do not launch an unstructured scale sweep or full64campaign.

Artifacts: `calibrated-joint-v1/` (3scans×2arms),
`calibrated-joint-expansion-v1/` (9scans×2arms), the corresponding evaluation
JSONs, `calibrated-joint-panel-v1.json`, and SHA256 sidecars. Reference errors
use the inherited operator-provided unsurveyed coordinate. No independent
recording generalization or new uncertainty-calibration claim is made.

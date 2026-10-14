# C053 local-curvature qualification

The current second-cycle training winner shows positive local curvature at both tested finite-difference steps. This provides no evidence for a hidden local saddle that would justify another optimizer continuation. It does not establish a global optimum or validate the observation model.

The frozen endpoint has objective 22288.344961733, NLL 22064.556982476 and maximum scaled gradient 1.73599e-5. Its 86-dimensional state lies 35.909439 km from its original 50 km search-disk center. All prespecified positive and negative probes were strictly inside the original physical, timing, nuisance and geographic constraints. Fitter initializer adjustment was zero.

| Scaled finite-difference step | Smallest full Hessian eigenvalue | Position eigenvalues after locally profiling nuisance |
| --- | ---: | --- |
| 1e-4 | 0.249914868 | 7.065565516, 34.661076108 |
| 5e-5 | 0.249916662 | 7.049771035, 34.653331498 |

The full and nuisance Hessians had no negative or numerically zero eigenvalues at either step. Maximum relative full-matrix step difference was 1.40181e-6. The smaller position eigenvalue changed by approximately 0.224%; the larger by 0.022%. No eigenvalue regularization was applied. Position coordinates use km; nuisance coordinates use the original fitter scales. These are observed objective curvatures, not calibrated position uncertainties.

This check makes a routine local optimizer failure less plausible for this endpoint. Together with the earlier exact likelihood-mass audit, it directs the next investigation toward physical RF/calibration assumptions and observation-model adequacy, while leaving the possibility of other distant modes open.

The run completed 345 objective/gradient evaluations, zero fits, and no reference or held-data reads in 46.437 seconds. Three component tests passed: symmetric coordinate probes, refusal to evaluate active-bound states, and recovery of a known negative profiled direction in a coupled quadratic. Ruff passed. Source commit: `4b79be570`.

Frozen experiment: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-interior-curvature-053-v1`.

- Result SHA256: `9f292cc226d8da810f74fbb54244f34140e15b3ecb354afdde84bbaa2b7fb30d`
- Seal SHA256: `9df830d4a8104bc615926f7d7cca7d57aff84a1c08e7f185ec00094245ed6ec8`

Original cohort results remain unchanged; no new estimator is promoted.

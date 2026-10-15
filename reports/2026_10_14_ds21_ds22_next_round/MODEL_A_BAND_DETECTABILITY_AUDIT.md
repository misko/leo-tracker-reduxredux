# Zero-fit audit of shared satellite detectability across bands

The current A observation port uses one catalogue detectability vector for both frequency bands. A zero-fit diagnostic finds substantial score derivatives for a band-dependent extension at both current full incumbents. This identifies model capacity worth testing predictively; it does not establish that sharing detectability causes the position error, nor that more capacity improves localization.

The proposed local contrast is defined before evaluation as `theta_low = theta - f_high*delta` and `theta_high = theta + (1-f_high)*delta`, where `f_high` is the observed full-training high-band fraction. Each band's logistic intercept independently preserves the original full-bank detection budget. The original shared-theta prior is counted once; the diagnostic contrast has a standard-normal prior, whose derivative is zero at delta=0. Geography, clocks, calibration, timing and observations are held fixed. No model has been fitted with this extension.

| Case | High-band fraction | Cosine of low/high data gradients | Contrast-gradient L2 norm | Tested interior coordinate | Analytic derivative | Central FD error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A035 | 0.410389 | 0.013158 | 152.492563 | 19 | -66.350505 | 3.04e-8 |
| A053 | 0.318717 | 0.129963 | 81.706970 | 48 | -22.350499 | 1.08e-9 |

The full gradient vectors are approximately orthogonal, not strongly opposed. Bounds on shared detectability coordinates and the original prior also affect stationarity, so these norms should not be read as an unqualified conflict or a failed current optimum. For the finite-difference test, the largest-magnitude contrast derivative among coordinates with two-sided effective-parameter slack is used; both plus/minus 1e-4 probes preserve the existing effective coefficient bounds. This choice uses only training gradients and feasibility, never reference accuracy.

The experiment independently replays current full objectives and partitions full NLL and detectability gradients into low/high terms after removing duplicated shared priors. It performs 14 objective evaluations, zero fits, and completes in 6.058 seconds. Actual finite differences agree with the contrast chain rule at both selected coordinates. Full derivative arrays and probe scores are retained in the sealed evidence.

Prior-art review found that heterogeneous receiver/channel dispersion, temporal persistence diagnostics, recorded-branch compatibility bounds, native likelihood/alias transport, and globally shared catalogue propensities have already been tested with mixed or negative findings. This band-dependent contrast is distinct from those tests and from the ongoing smooth-visibility model. A next-stage test must preserve a shared-q control, fit only training-block observations, evaluate excluded blocks, separate predictive NLL from priors and position error, and report failed fits explicitly. It must not select a contrast width, prior, band weight or endpoint using reference error. No new fitting is authorized by this report alone.

Source `f79e4f1f8`; one test and Ruff pass. Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-band-detectability-audit-v1`. A035 uses its current polished full training selector; A053 uses the latest crossed-profile full selector. No references or held observations were accessed, and no accuracy row changed.

# Fresh roof confirmation: RX geometry and geographic error

Frozen before any reception or location scoring of this cohort. The selection manifest fixes the metadata cutoff and earliest four complete, pose-valid recordings after the development cohort; it records exclusions and forbids replacement based on results. The four selected IDs are b5604c3d838fa7ed, f147dd8a5bc99346, 609d7a8d9861f3db, and 40ebc07665464c7d. All are disjoint from the original six calibration and four development scans.

## Frozen models and independent searches

Use the Student-t shared-track-identity model and calibration export from `../2026_09_27_roof_location_geometry/fixedpoint_parameters.json`: scale132.45056967671437 Hz, df1.585959259734901. Verify the extraction and core/fitter hashes. Keep the original six-scan detection/ratio reception calibration and counterpart-matching bias unchanged. Do not refit frequency parameters, reception coefficients, orientation mapping, matching thresholds, or likelihood weights on these four recordings.

Compare robust Doppler-only D with D plus calibrated receiver detection and conditional log-margin-ratio likelihood. Same three-candidate training-only shortlist, zero timing offset, one shared satellite identity per track, occupied-second track weights, and unit reception coefficients in both prior branches. Neither ground truth nor reception selects the training shortlist. The joint likelihood can marginalize candidate identity using reserved evidence when scoring a location.

Sacramento prior: center38.5816,-121.4944, radius250km. Reno: center39.5296,-119.8138, radius500km. Each prior and each arm runs the measured-priority search with levels100/50/25/12.5/6.25/3.125/1.5625km and160 point evaluations. Boundary representatives stay within the prior disk. At every point use its own full causal eligible catalogue; never share fitted candidates or winning coordinates between priors or recordings. Full-catalogue immutable propagation may be reused within a recording. No reference position, development winner, or published production estimate is a search seed.

Reception endpoints are generated directly from the public tracking input and exact source-observation links without receiver coordinates, satellite IDs, or reference fits. Missing counterpart probes or ambiguous anchors are errors, not nondetections. Record every exclusion/failure and do not replace failed recordings after seeing outcomes.

## Reporting

Only after both independent branches finish, a separate reporter may read the pose coordinates and compute great-circle distance errors. Report all eight scan/prior cases, D versus joint error and signed change, coordinates, budget/termination status, and common-inventory D/detection/joint/reversed-direction diagnostic winners. Report means and medians separately for Sacramento and Reno; do not select whichever prior or metric happens to improve.

Success requires an improvement attributable to adding RX evidence against the matched robust baseline on fresh data. Better search alone, better frequency likelihood alone, lower training loss, finer nominal spacing, or a selected success case do not establish that claim. Mixed outcomes must be reported as mixed; retain the full goal as unproven if the evidence is not convincing. These four nearby stationary recordings support only a bounded cohort conclusion, not universal accuracy or an independent large-sample confidence claim.

The primary likelihood is per-anchor composite evidence. Reciprocal compatible-pair rows and temporal dependence remain; any apparent gain needs a deterministic pair-deduplication sensitivity before a general conclusion. Keep the full observation denominator when removing a duplicate reception contribution. A receiver-mapping reversal is a diagnostic control, not an alternative to choose based on reference error.

Coordinates are operator-supplied WGS84 roof metadata, not surveyed GPS truth. Altitude, antenna phase centers, and orientation/beam uncertainty are not independently measured. No sub-survey precision claim, new RF collection, source-store mutation, or production model deployment is authorized by this experiment.

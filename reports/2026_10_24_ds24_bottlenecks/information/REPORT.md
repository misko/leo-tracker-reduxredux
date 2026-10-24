# DS24 information bottleneck: matched observations and identities

All 24 common DS24 cases were replayed at the persisted all-channel cavity solution in both c = 0 and fitted-c arms. Every channel/RX subset retains the same all-data endpoint, candidate identities, aliases, point mask, geometry, noise Gamma precision, nuisance prior and causal TLE inputs. This is not a rerun of the independently fitted channel halves. GPS enters only evaluation_only.json and this report. No RF collection or post-scan TLE was used.

## Measured result

The primary calibration-only diagnostic uses exactly the curved observations that update the current algorithm's nuisance coefficients. For fitted c its median local major-axis SD is 0.534 km; freezing every nuisance gives 4.17 m. Only 0.00461% of raw position-information trace survives nuisance elimination. Freezing phase alone gives 0.110 km; freezing phase + orbit gives 0.056 km; freezing all receiver terms gives 0.386 km. This is local information conditional on the supplied model and Gamma variables, not a fundamental CRLB or calibrated uncertainty.

A separate curved-plus-predictive Gaussian surrogate has median major local SD 0.484 km and all-nuisance-known value 4.07 m. This surrogate includes predictive rows through a joint fixed-Gamma Gaussian marginal and is not permission to update calibration from those rows. The actual algorithm's linear rows remain predictive-only. Five cases have no predictive entries, so the two diagnostics coincide there.

| Same full-solution data slice | Curved major local SD (km) | Curved reduction from adding remaining data | + predictive Gaussian surrogate SD (km) |
|---|---:|---:|---:|
| low | 0.760 | 26.2% | 0.684 |
| high | 0.938 | 37.1% | 0.799 |
| rx1 | 0.801 | 27.5% | 0.740 |
| rx2 | 0.885 | 35.3% | 0.820 |
| all | 0.534 | — | 0.484 |

Every subset satisfied the positive-semidefinite information ordering: adding a band or receiver helps at fixed identities/masks. This need not improve each independently refitted endpoint: those runs can change associations, masks, robust weights and prior compromises.

| Unavailable-information oracle | Curved major local SD (km) | + predictive Gaussian surrogate SD (km) |
|---|---:|---:|
| Freeze phase | 0.110 | 0.102 |
| Freeze orbit | 0.329 | 0.288 |
| Freeze phase_and_orbit | 0.056 | 0.056 |
| Freeze receiver_offsets | 0.529 | 0.481 |
| Freeze receiver_drifts | 0.493 | 0.462 |
| Freeze receiver_smooth | 0.417 | 0.388 |
| Freeze receiver_all | 0.386 | 0.375 |
| Freeze rf_c | 0.533 | 0.484 |
| Freeze all_fragment_bias | 0.399 | 0.351 |

In the primary curved-only diagnostic, the median maximum absolute correlation of the weak position axis with an individual phase coefficient is 0.935; with an orbit coefficient 0.542; with c 0.037. Correlations and oracle controls indicate confounding, not that those nuisance values are known or may safely be fixed in inference.

## More precise frequency measurements at the same nuisance priors

| Hypothetical point-noise change | Curved major local SD (km) | Curved median reduction | + predictive Gaussian surrogate SD (km) |
|---|---:|---:|---:|
| σ / 2; precision × 4 | 0.397 | 24.5% | 0.360 |
| σ / 10; precision × 100 | 0.185 | 63.7% | 0.157 |

These are fixed-Gamma counterfactuals, with unchanged observations and nuisance priors. They do not establish that an estimator or waveform can attain those frequency errors. The observed bottleneck is compared directly with the much stronger oracle phase/orbit constraints above.

## c = 0 versus fitted c

The full major local SD median is 0.484 km for c = 0 and 0.484 km for fitted c. The median per-case fitted/c0 SD ratio is 1.0006. The mean curved RMS changes from 71.416 to 71.380 Hz; the separately evaluated mean position error changes from 1.202 to 1.220 km. Frequency fit improvement therefore did not improve mean location here.

## Geometry and physical interpretation

For curved calibration data the median weak-axis separation between independently nuisance-profiled low/high slices is 17.7°; between RX1/RX2 slices 21.9°. These are local information-ellipse axes, not antenna boresights. Median counts of shared candidate families are 11.0 across bands and 8.0 across receivers. Including predictive rows gives angle medians 13.4° / 20.9° and shared-family counts 15.0 / 12.0. Thus the additional measurements often constrain the same family phase/orbit variables.

The LT3D-004B station authority and operations note establish a nominal 40° included feed-axis angle, 20° outward tilt per holder, and 120 mm CAD neck-center separation. They explicitly leave installed RF boresights, base pose, phase centers, polarization roll and directed ENU phase-center baseline unmeasured; physical connector/software RX mapping is provisional. A level base would imply nominal axis elevation 70°. Antenna orientation weights which signals are visible; it is not a measured satellite bearing. The present frequency model uses one site location for both receivers and contains no antenna-bearing, measured gain-pattern, TDOA or interferometric phase observation. Two similarly located feeds therefore do not produce a two-station triangulation baseline merely because their nominal boresights differ.

Physical metadata sources: /home/mouse9911/gits/leo-tracker-reduxredux/docs/operations/radio20-lt3d-004b-20261001.md and /home/mouse9911/gits/leo-tracker-reduxredux/deploy/station/gauss-r20-lt3d-004b-20261001-v1.json. The metadata authority is prospective and is not, on its own, verification of a capture-bound companion for every DS24 recording. The /srv/bulk/leo/capture-pose/gauss-r20-lt3d-004b-20261001-v1 directory was not readable in this session (permission denied), so companion-level bindings were not independently verified.

## Numerical and evaluation checks

All 48 arm/endpoints passed persisted-objective replay (maximum absolute gap 2.7801445e-05; guarded absolute < 1e-3 and relative < 1e-8 tolerance). Position derivatives at 20/40 m agreed to maximum relative 2.08e-09. Stable ridge-projection information agreed with independent augmented QR at <1e-8 relative. Profiled negative-twice-ELBO Hessians, divided by two, were checked at 0.1/0.2 km with the persisted phase-linearization reference held fixed and nuisance coefficients/Gamma variables reoptimized. They are not fully phase-refreshed nonlinear curvature. Maximum relative step change is 0.000688; minimum eigenvalue across all arms is 0.899 per km².

The evaluation error vector uses the exact inverse of the engine map prototype_dsx01_continuous_position.latlon at CENTER: north scale 111.0 km/degree, east scale 111.32 × cos(CENTER latitude) km/degree. This keeps Mahalanobis errors in exactly the same position-coordinate units as the information matrices. Separately reported scalar geographic errors are retained from the existing evaluation table.

For fitted c, the descriptive apparent squared Mahalanobis error has median 6.90, range 0.22–30.31. 11/24 are below the χ²₂ 95% reference 5.99 and 15/24 below the 99% reference 9.21. These are descriptive comparisons, not coverage tests: the covariance is conditional, identities were selected, Gamma/prior scales are model assumptions, and cases may share systematic or orbital errors. A true site not coinciding with the likelihood maximum alone does not prove model error.

## Code and evidence

- diagnose_information.py: persisted-input replay, finite differences, nuisance projection, same-point band/RX subsets, counterfactual noise precision and actual objective Hessian.
- test_information.py: independent augmented-QR agreement, data/freezing monotonicity and exactly confounded precision-saturation identities.
- Per-case JSON plus all_cases.json: all 24 cases × both c arms; curved-only and curved-plus-predictive fixed-Gamma surrogate results, oracle controls, top correlations and numerical checks.
- summary.json, evaluation_only.json, position_information.png: aggregates, evaluation-only comparisons and scientific figure.
- Repository model pointers: tools/dsx01_joint_marginal.py (common-site Doppler and hardware/phase/orbit columns); tools/ds23_predictive_linear.py (predictive linear covariance and 300 Hz biases); tools/build_dsx01_orbit_modes.py (causal physical orbit scales); tools/ds23_position_information.py (independent QR projection).

The fixed-Gamma surrogate freezes covariance derivatives and does not fully reproduce the nonlinear robust likelihood. The separately computed objective Hessian includes nuisance-coefficient/Gamma reoptimization and covariance-volume effects while holding the persisted phase-linearization reference fixed; it is not fully phase-refreshed nonlinear curvature. Oracle freezing controls are diagnostics, not proposed changes to scientifically necessary nuisance uncertainty.

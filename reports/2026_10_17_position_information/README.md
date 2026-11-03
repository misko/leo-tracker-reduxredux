# Position information and a scan-local calibration pilot

The position goal remains unmet. The new diagnostics show substantial loss of
position information to component constants and satellite phase. Merely merging
the current blind families or combining two recordings does not remove the
observed bias. No RF metadata, measurements or satellite labels were changed.

## Conditional information audit

East/north Doppler derivatives are evaluated at the existing independent local
estimates. A weighted Gaussian design includes four receiver/band offsets, four
small drifts, optional RF-dependent c, one phase per satellite and one constant
per fixed component. All individually measured-curved points from the earlier
blind c0 associations are retained in both arms. These assignments did not come
from the supplied GPS. Linear fragments never enter the calibration population.

The component cap is 50 effective points, measurement noise is 150 Hz, component
constant sigma is 1,000 Hz, drift sigma is 0.5 Hz/s and the original phase sigmas
are preserved. Bias priors carry the same component weight as the fitting cost.
An augmented, column-scaled SVD projects out nuisance parameters without a
subtraction of large normal matrices. Synthetic tests compare with the dense
Gaussian Schur complement, nuisance-unit changes and unidentified directions.
Position finite differences at 50 m and 25 m agree to within the recorded
1e-3 Hz/km tolerance. Jacobians, weights and prior precisions are saved.

| Dataset / families | c arm | Curved points / constants | Major axis with nuisance fixed | Major axis after nuisance projection | Major axis without nuisance priors | Actual error |
|---|---|---:|---:|---:|---:|---:|
| S01 / separate | c=0 | 1,519 / 43 | 0.013 km | 0.618 km | 1.006 km | 6.356 km |
| S01 / separate | fitted-c | 1,519 / 43 | 0.013 km | 0.618 km | 1.006 km | 6.356 km |
| S01 / merged | c=0 | 1,519 / 36 | 0.014 km | 0.620 km | 1.003 km | 6.479 km |
| S01 / merged | fitted-c | 1,519 / 36 | 0.014 km | 0.621 km | 1.009 km | 6.479 km |
| DS22-001 / separate | c=0 | 1,123 / 29 | 0.015 km | 0.851 km | 1.003 km | 2.139 km |
| DS22-001 / separate | fitted-c | 1,123 / 29 | 0.015 km | 0.851 km | 1.003 km | 2.139 km |

![Information loss to nuisance parameters](nuisance_information.png)

These are local conditional one-sigma axes, **not calibrated accuracy bounds**.
Identities and alias branches are fixed; independent Gaussian noise and a
locally correct mean model are assumed. Active bounds and derivatives of the
conditional-volume score are not included. No phases or drifts are near their
bounds in these six endpoints. Wrong identities, correlated residuals, TLE
model discrepancy and external calibration uncertainty are not represented.
Therefore these are not full-score posterior covariances. In particular, the
S01 error greatly exceeds the local conditional scale; measurement noise alone
under this model does not account for its error.

Component constants cause the first large information loss. Allowing phases
causes the next. The modest c effect does not establish better localization.
Tightening priors to shrink an ellipse would not establish better accuracy.

## Independent merged DS22-001 replay

Two new matched searches use exactly the same blind c0 curved population,
candidate labels, priors, initializers and 73-location cap. They finish at
**2.139 km** error in both arms, with 1,016 / 1,123 fixed curved points passing
final member checks. The full-population post-fit extension associates 1,515
points into 47 merged tracks in each arm. Endpoint RMS is 81.12 / 81.08 Hz.

Filtering the original merged catalogue to curved calibration members leaves
29 components, the same count as the separate-family fit. Thus this particular
merging proposal does not reduce calibration constants or supply new geometric
constraints; identical positions are expected. It must not be described as a
demonstrated accuracy benefit from merging. This contrasts with S01, where
43 to 36 constants are actually reduced but position accuracy still does not
improve in the recorded local search.

## Common-position pilot

A further pair of blind searches assumes S01 and DS22-001 share one stationary
position. Each recording independently profiles its own receiver/band offsets,
drifts, component constants and satellite phases at each geographic proposal.
No offsets or phases are tied across scans. The starting position is the mean
of earlier blind estimates; GPS is used only after saving the final fit.
The same-site hypothesis is an explicit assumption, not independently verified
physical deployment evidence.

Both arms finish at **5.557 km** error after 49 evaluated locations. All 2,642
fixed curved points contribute; 2,491 pass final member checks, split 1,420 in
S01 and 1,071 in DS22-001. Per-scan RMS is 123.0 / 82.7 Hz for c=0 and
123.0 / 82.6 Hz for fitted-c. Neither arm is a fully qualified localization
result, and a local search does not prove the global optimum. The result does
not improve on DS22 alone and does not solve S01's bias. Pooling observations
alone is insufficient under the present fixed labels and model.

## Scope and next experiment

The best earlier DS22-001 result under the accepted RF model remains 1.895 km.
No result below 0.5 km, all-five-DSX01 blind validation, or whole-DS22 accuracy
claim is supported. Known-GPS phase-family association gains are reported
separately in `../2026_10_17_cohort_phase_repair/`.

Next, inspect per-satellite position-score conflicts using the same blind
labels and all-point accounting. Compare the full causal orbital discrepancy
between successive TLEs with the single along-track phase approximation, then
test any additional orbit uncertainty with explicit priors and matched c arms.
Before extending a shared-position fit across DSX01, obtain blind labels for
S02–S05; their GPS-conditioned labels must not seed a claimed blind result.
The wider DS22 recording cohort also remains part of the active goal.

Sixty-five focused tests pass across the information projection, scan-local
orchestration, association gates, fixed-family fitting and existing invariants.
Sources and input hashes accompany these results. The initial diagnostic run's
stdout serialization failure is preserved separately as
`../2026_10_17_position_information_print_failure/`; its first completed numeric
output was superseded by the successful full six-state rerun. No RF collection,
QNAP mutation or golden-fixture change occurred.

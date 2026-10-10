# Receiver-difference mean-model audit: no new extension justified yet

This is a source/report review only. No recording, model, IQ or reference-error
query was performed; no parameter, protocol or numerical experiment is frozen.
The review does not identify a sufficiently supported new receiver mean-model
extension to prioritize over the full phase-versus-timestamp comparison.

## What the present model already covers

[DynamicRFObjective](../../src/leo/analysis/hard60_dynamic_rf.py) combines the
ordinary receiver affine terms and shared static RF coefficient with independent
receiver smooth-clock bases and receiver-specific RF-by-time coefficients. The
smooth basis removes constant and linear node modes, so its coefficients do not
simply duplicate the existing affine coordinates. Priors remain essential: data
rank alone cannot separate clock changes from orbital Doppler curvature.

[SatelliteCorrection](../../src/leo/analysis/hard60_satellite_correction.py)
also supports candidate-common frequency offsets and slopes; production
[SlopePrior](../../src/leo/analysis/hard60_slope_prior.py) supplies the B7 slope
prior. These satellite corrections are shared across receivers. Adding another
arbitrary per-satellite trend would duplicate this mechanism or weaken the
geometric information it competes with.

The most obvious missing-looking static term is already a negative experiment:
[iteration 2](../2026_10_08_position_error_iter02/README.md) tested
`c_RX0 = c - d/2`, `c_RX1 = c + d/2` with three fixed Gaussian widths. On its
seven selected development diagnostics, the best mean improvement was only
1.9 metres and worst error worsened. That older, narrow test is not a universal
rejection under B7, but it does not justify presenting differential stretch as
an untested solution. Its proper c=0 ablation locked both c and d.

[Iteration 23](../2026_10_08_position_error_iter23/README.md) showed why unmatched
receiver means are misleading: some large apparent contrasts had no coincident
pairs. [Iteration 90](../2026_10_09_position_error_iter90/DECISION.md) then audited
all 148 historical members. Median fitted-c receiver/satellite contrast fell
from 23.944 Hz raw to 5.583 Hz after common time/channel projection and 1.874 Hz
after including the existing smooth-clock span. The residual contrast is not
identified as an LNB error. Unpenalized span projection also does not prove the
regularized production model has physically absorbed every such contribution.

## Why differencing is not a new position-information source

For genuinely simultaneous observations of the same signal at the same RF,
under the existing co-located receiver geometry, write

```
y0 = D(position, satellite, time, RF) + b0 + c*RF + error0
y1 = D(position, satellite, time, RF) + b1 + c*RF + error1
difference = b1 - b0 + error1 - error0
```

The shared geometry and static c cancel. A pair difference can constrain
relative receiver calibration without fitting receiver position, but it cannot
identify common clock error, common RF stretch or a common geometric bias.
Different satellite signals, actual RF centres, or observation times invalidate
that exact cancellation. Near-simultaneous pairing needs its actual timing
error accounted for; rounding timestamps is not a new physical simultaneity
measurement.

For balanced Gaussian pairs with known assignments, transformation to average
and difference is an invertible change of coordinates. A free antisymmetric
correction changes the differential residual alone; the common spatial gradient
is unchanged. [Iteration 91's geometry and linear-solver preparation](../2026_10_09_position_error_iter91/README.md)
already covers this limitation. Position benefit would require unequal support,
association changes or calibration coupling, and must be demonstrated rather
than inferred from smaller pair residuals.

Within-RF temporal differences likewise suppress constant nuisances but retain
receiver drift and satellite timing/slope confounding. Dropping the average
component discards position information. Keeping all averages and the correct
transformed covariance yields the same Gaussian likelihood, not a new model.
Reweighting differences without that covariance would instead be a changed noise
model, revisiting the unresolved covariance branch rather than identifying a
physical mean correction.

## Concrete low-cost option already available, not a new hypothesis

If embedded execution cost becomes the immediate constraint, the
[iteration 91 bounded linear nuisance solve](../2026_10_09_position_error_iter91/LINEAR_NUISANCE.md)
is the appropriate existing prototype: fixed geometry, responsibilities and
windings reduce the current receiver-clock block to a small constrained weighted
least-squares problem with the actual coefficient prior. It adds no flexibility,
preserves c=0 locks, and must accept only through the refreshed exact objective
and unchanged qualification gate. This is a solver implementation option, not
evidence of additional position information or a new untested mean model.

A future differential-calibration claim would first need new reference-free
evidence of a component outside the existing clock/RF span on genuinely shared
support, stable under conditional-label overlap checks. The recent saved-moment
RCA shows why arbitrarily small positive responsibility mass cannot establish
that overlap. No extra offset, slope, per-channel calibration or per-scan prior
is proposed from the current evidence. Keep common/differential identifiability
explicit and report matched c arms and frequency fit separately if any later
model experiment is justified. The standalone 0.4 km target remains unmet.

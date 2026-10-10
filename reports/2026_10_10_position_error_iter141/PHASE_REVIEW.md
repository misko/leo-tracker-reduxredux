# Independent review of the frozen relative-phase objective

**No sign, units or smooth-cell derivative defect was identified.** The phase
model makes a different physical interpretation of satellite-relative timing;
source inspection does not establish that this interpretation is correct for
all recorded errors. This review reads code and existing tests/reports only.
It performs no recording or objective evaluation and changes no frozen source.

## Frame and velocity semantics

The ordinary [predict_orbits](../../src/leo/analysis/hard60_score.py) queries the
ECEF bank at `q = observation_time + common + relative_k`. The native
[orbit kernel](../../src/leo/analysis/_regional_orbits.cpp) linearly interpolates
position and velocity independently. Consequently the ordinary relative shift
advances both satellite phase and Earth's rotation.

[PhaseObjective.predict](../2026_10_10_position_error_iter130/objective.py)
queries the same q, then applies `Rz(+omega*relative_k)` to both interpolated
position and rotating-frame velocity. The positive sign is consistent with
[teme_to_ecef](../../src/leo/sky/frames.py), which uses `Rz(-GMST)` and subtracts
`omega cross position` from the rotated inertial velocity. In the constant-rate
approximation, the extra rotation cancels only the relative shift's Earth
rotation; the common shift remains a timestamp correction.

No extra `omega cross position` term should be added to the transformed velocity
itself. For constant delta, the physical derivative with respect to observation
time is `Rz(omega*delta)*v_ECEF(q)`. Equivalently, converting the advanced inertial
state into the earlier Earth frame gives the same result because rotation about
the same axis commutes with the cross-product correction. The cross term belongs
in the derivative **with respect to delta**, not the velocity value.

The [transformed helper](../2026_10_09_position_error_iter126/phase.py) correctly
returns, for each independently interpolated state a and its secant a':

```
value              = R(delta) a(q)
common derivative  = R(delta) a'(q)
relative derivative= R(delta) [a'(q) + omega cross a(q)]
```

It applies this formula separately to position and velocity. Substituting the
stored velocity for the position interpolant's secant would differentiate a
different numerical model; the implementation does not make that substitution.

## Doppler and gradient checks

With direction u from receiver to satellite and radial speed `u dot v`, the
prediction is `-RF/c_light * (u dot v)`. Receding motion therefore lowers received
frequency, matching ordinary B7. Positions are kilometres, velocities km/s,
`c_light=299792.458` km/s, RF is Hz and timing shifts are seconds. The rotation
angle is dimensionless radians.

The spatial derivative uses
`+(RF/c_light) * (v - radial*u)/range dot site_jacobian`; the sign follows the
negative derivative of satellite-minus-site displacement. Timing derivatives
use `-(RF/c_light) * [tangent dot dp + u dot dv]`. Common timing sums its separate
derivative over candidates, while relative timing projects the individual
derivative through the unchanged zero-sum satellite basis. The common and
relative Gaussian penalties, clock precision, satellite slope/offset terms and
RF design are retained. This does not add a receiver-frequency nuisance term or
change the shared-c interpretation.

[Existing iteration 130 tests](../2026_10_10_position_error_iter130/test_objective.py)
already check finite differences for spatial, common/relative timing, clock and
satellite coordinates, and conversion preserving the slope prior and layout.
At zero relative shifts they check ordinary score, common/spatial gradients and
clock gradients agree. Relative derivatives are expected to differ even there:
the two models have the same value at delta=0 but different nearby families.
[Iteration 126 scope](../2026_10_09_position_error_iter126/SCOPE.md) also records
the frame-sign algebra and off-equator synthetic checks. Repeating those tests
would not provide independent new physical validation.

## Assumptions and limits

- The rotation is a constant-rate z-axis approximation applied to an existing
  ECEF bank, not exact direct phase-shifted SGP4 propagation. The source frame
  conversion uses a GMST polynomial, approximates UT1 by UTC and omits polar
  motion. The shortcut does not independently resolve those approximations.
- A fitted relative shift could represent orbit-phase error, measurement timing,
  association error or several effects. Treating all relative timing as phase
  while treating the common component as timestamp is a physical assumption.
  Zero-sum relative timing fixes the chosen separation; it does not prove a
  physical cause for the fitted common mean.
- Visibility is a hard horizon mask. Derivatives are valid inside a fixed
  visibility/interpolation cell, not a smooth derivative across horizon events
  or interpolation knots. The phase objective retains this limitation rather
  than repairing it. A local gradient gate is not global optimality proof.
- Observer coordinates come from the hypothesis and regional prior, not a known
  receiver reference. The formulas apply at arbitrary supported latitudes and
  longitudes; the positive z-axis rotation is not Sacramento-specific. They
  retain ordinary B7's stationary ground observer, fixed-altitude regional
  geometry and local coordinate mapping assumptions.
- `convert` is a shallow state transfer. Its mathematical preservation is
  intentional; callers must not mutate shared arrays across arms. The reviewed
  clean comparison constructs independent measurement-model copies before phase
  conversion. This is an integration constraint, not an identified numerical
  defect in the phase formula.

The scientifically relevant question remains the complete matched position
comparison, including c=0, convergence/fallbacks and failures. Smaller frequency
NLL or a plausible frame argument cannot establish better localization. No
additional variant is proposed solely because another timing convention is
possible; the frozen full-cohort phase test should determine the next decision.

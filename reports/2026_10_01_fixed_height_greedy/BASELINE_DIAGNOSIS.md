# Baseline diagnosis for fixed-height greedy replay

This diagnosis reads the seal-verified `runs-v3` receipts from the frozen
64-scan Sacramento experiment. It does not run new fits or propagation. The
proposed replay fixes receiver height at the separately defined 100 ft MSL
surface; this document does not choose the MSL-to-ellipsoid conversion.

## Baseline outcomes

The greedy arm completed 12 of 64 scans. Thirty-six stopped on a support gate
and 16 raised `prediction time lacks four-knot orbit support`. Of the completed
fits, only 2/64 planned scans were below 1 km. Accepted errors were:

- DS9: 0.379, 2.126, 2.737, 3.017, 8.010, and 39.275 km.
- DS10: 2.195, 200.531, and 216.971 km.
- DS11: 0.906, 11.473, and 113.080 km.

Completion therefore did not imply acquisition of the correct spatial mode.
Three accepted fits were more than 100 km wrong, and two exceeded 200 km.

## What the receipts show

### The first one-shot update is usually a very large move

Across all 64 scans, the median horizontal displacement after the first greedy
track was 150.2 km. Forty-eight first updates exceeded 100 km and nine exceeded
200 km. Median first displacement was 97.6 km for completed fits, 148.0 km for
later interpolation errors, and 172.8 km for gate failures. DS11-F048 crossed
the disk boundary after its first update at 304.8 km.

This is the expected failure mode of applying one local EKF linearization to a
broad, curved Doppler likelihood. The update treats a tangent approximation at
the prior component as valid across a continental-scale covariance, then
commits to the single highest-scoring satellite branch. A valid covariance and
a completed update do not make that extrapolation locally accurate.

### Early association evidence is ambiguous but greedy commits permanently

The median largest first-track satellite probability was only 0.233 for scans
that eventually completed, 0.256 for interpolation errors, and 0.174 for gate
failures. Several first tracks split comparable probability among three or more
satellites. For example, DS10-F001 began with 0.199, 0.197, and 0.187 on its top
three branches; DS9-F020 began with 0.257, 0.232, and 0.215.

The greedy arm retains only the winning branch after each track. It cannot
recover when an early, weakly separated identity points the state toward a
wrong location basin. The accepted DS10-F168 and DS10-F177 solutions illustrate
the consequence: they completed every gate while ending 200.5 and 217.0 km from
the evaluation reference.

### Free height absorbs model error until the support gate fires

Twenty-three scans stopped on `height_support_boundary`. Their final height
offsets commonly reached roughly 0.5 to 1.1 km in magnitude. Height can trade
against horizontal position, clock, drift, orbit error, and a wrong satellite
identity in the local Doppler Jacobian. Fixing height removes this escape
direction and should eliminate this particular gate, but it does not by itself
repair wrong identities, large horizontal extrapolations, or the likelihood
model.

Thirteen other scans stopped on `uniform_region_center_boundary`. Several were
already near or beyond 225 km after the first track. Fixing height may change
these trajectories, but their immediate horizontal jumps show an independent
nonlinearity problem.

### Clock motion exhausts the finite interpolation stencil

All 16 exceptions were four-knot orbit-support failures. The last recorded
clock offsets ranged from -5.30 to +18.79 seconds; failure can occur at smaller
offsets when a retained track lies near an orbit-grid edge. The frozen orbit
banks span -10 to 310 seconds, while cubic velocity interpolation needs an
interior four-knot stencil.

The bound metadata uses causal Space-Track TLE snapshots for every scan. TLE age
at capture start ranges from 896 to 7,797 seconds (median 3,497 seconds), and the
saved metadata binds the exact TLE path and digest. It is therefore possible to
repropagate a wider time interval from the same causal TLE without introducing
future information. That engineering change should be source-bound and tested
for numerical agreement on the existing interior interval. Wider support
prevents an exception; it does not validate a large inferred clock offset.

### The null branch is effectively unavailable

First-track background probabilities had a median near 7e-261, a maximum near
2e-81, and underflowed to exactly zero in seven scans. The background slope
prior is narrow relative to some observed tracks. Greedy association therefore
has almost no way to classify an absent-catalogue satellite, outlier, or poorly
modelled track as background. A sharp satellite probability under this model is
not calibrated identity evidence.

## Recommended mechanism changes

1. **Fix height before linearization.** Remove height from the inferred state
   and compute the receiver ECEF position from the declared 100 ft MSL surface
   using the frozen geoid conversion. Do not emulate fixed height with a tiny
   covariance in the old six-dimensional update.

2. **Use an iterated, damped nonlinear update.** For each proposed association,
   recompute prediction and Jacobian at the updated state until the innovation
   and state step converge. Apply a trust region or line search in horizontal
   position and clock. Reject a branch when no supported step improves its
   proper likelihood. This directly targets the 100–300 km first-step behavior.

3. **Keep a small association beam.** Retain the top few joint
   location/identity hypotheses through the ambiguous early tracks, including a
   background branch, and prune only on cumulative normalized evidence. A beam
   of fixed bounded width is cheaper than the full Gaussian sum while allowing
   recovery from an early wrong identity.

4. **Refit the track history.** After accepting a new branch, solve or iterate
   over all retained track residuals for that hypothesis rather than applying a
   single irreversible sequential tangent update. If the cumulative refit
   changes the basin or makes an earlier association implausible, reconsider it
   within the beam. Freeze convergence, damping, and maximum-iteration gates
   before reference scoring.

5. **Separate clock support from clock plausibility.** Repropagate the exact
   causal TLE over a wider bounded interval so supported hypotheses do not fail
   at the stencil edge. Independently constrain or penalize implausible clock
   movement and report boundary contact. Extended propagation must not become
   permission for an unconstrained clock to absorb wrong associations.

6. **Revalidate the background model independently.** Use held-out development
   tracks, including absent-catalogue and outlier cases, to freeze a background
   likelihood with realistic slope/curvature support. Do not tune it against the
   roof reference or the selected 64-scan outcomes.

## Gates for the next replay

The fixed-height replay should report first-step displacement, nonlinear
iteration convergence, trust-region contact, beam mass retained, background
probability, cumulative refit residual, clock support margin, and association
changes. A run that merely avoids the old height gate is not a successful
localization. Accepted status should require bounded nonlinear convergence and
support, while location error remains evaluator-only after receipts are sealed.

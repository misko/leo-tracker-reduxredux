# Prespecified observed timing-curvature diagnostic

The question is whether satellite timing adjustments absorb much of the local
position information after the model can also change satellite assignments.
Evaluate exactly two saved fitted-c states: the original all-band winner and
the earlier seven-call refined all-band winner. Do not optimize, change priors,
change candidate evidence, compare alpha settings or access reference positions.

Satellite timing parameters shift the ECEF ephemeris query in seconds. Receiver
calibration remains evaluated at recorded native times. These parameters are not
corrections to acquisition UTC. Large fitted values therefore require analysis
of model identifiability before being interpreted as physical timing errors.

Use central finite differences of the original complete marginalized gradient,
with latent assignment responsibilities recomputed at every point. The two
fixed steps are 1e-4 and 5e-5 in scaled coordinates. Physical scales are 1 km
for position, 200 Hz for receiver offsets, 2 Hz/s for drifts, 200 Hz/GHz for c,
1 second for common/relative satellite timing and 5,000 Hz for group contrasts.
Each 52-parameter state requires one baseline plus 208 gradient evaluations:
418 total, zero optimizer calls. Baseline objective, NLL and prior ledger must
replay their saved values within 1e-7.

Report both raw and symmetrized Hessians and the exact original quadratic prior
Hessian. Compare the 2×2 position Schur complement with calibration profiled
alone versus calibration and satellite timing profiled together. Retain physical
compensation coefficients per kilometre of displacement and interpolation/bound
applicability. These are local model diagnostics, not calibrated position errors
or confidence intervals.

Before interpretation, require full-Hessian relative symmetry error at most
1e-3 and two-step full/Schur stability error at most 1e-2. In the declared scaled
coordinates, use eigenmode threshold 1e-10 times the larger of one and spectral
magnitude. Report negative modes separately from singular/weak modes. Either
invalidates nuisance profiling; do not add a ridge or pseudoinverse to obtain a
confidence claim. Unavailable or unstable results remain outcomes, with no
step-size sweep or retry selected from the result.

All perturbations must pass the original physical bounds and bank support
checks before the first gradient call. The whole numerical slice, including
training preparation, has a 120-second internal limit, TERM at 135 seconds and
KILL at 140 seconds. Immutable input, source/archive, original endpoint and
seven-call parent bindings precede the run. Preserve failed endpoint receipts;
the complete terminal must bind both endpoint results and their seals. No held
observations or new RF collection are used.

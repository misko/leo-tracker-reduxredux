# B7 observability adapter expectations

This is a source/math review, not a recording evaluation or uncertainty result.
Treat known coordinates and errors as evaluation-only; diagnostic construction,
grouping, eigenmode thresholds and operational decisions must not read them.

For frequency prediction Jacobian J_ik and frozen mixture responsibilities w_ik,
the complete-data Gaussian curvature proxy is
`H_complete = sum_ik w_ik J_ikᵀ J_ik / sigma²`.
Clutter has no frequency Jacobian. This is positive semidefinite and measures
local conditional frequency sensitivity when labels are effectively known. It is
not the observed Hessian of the marginal mixture objective. Freezing labels
omits their response to parameter changes and can substantially overstate
information when several satellite hypotheses compete.

For locally affine predictions and fixed visibility, define each component score
`a_ik = residual_ik J_ik / sigma²`, with a_i,clutter=0. The observed negative
log-likelihood curvature is
`H_observed = H_complete - sum_i Cov_w(a_ik)`.
Thus missing categorical information subtracts a positive-semidefinite term.
Nonlinear orbit predictions add the responsibility-weighted residual-times-second
derivative term (with sign determined by residual=measured−prediction). Circular
wrap and visibility changes are nonsmooth; neither proxy captures those jumps.
Observed curvature can be indefinite away from a local minimum. Do not silently
clip its negative eigenvalues and rename the result Fisher information.

Construct physical and nuisance columns from the actual B7 endpoint layout:
position, common/relative timing, physical receiver frequency/drift/static c,
smooth receiver clocks, satellite offset/slope contrasts and final RF-time terms.
Include the same prediction chain and scaling as the fitter. Preserve c=0 locks,
zero-sum bases and any fixed RF drift. A convenience matrix with only position
and affine receiver clocks does not measure deployed B7's conditional geometry.

## Nuisance elimination and bounds

Separate three explicitly labeled quantities: data-only complete-data proxy,
data-only observed local curvature when computed, and prior-regularized local
curvature. Add the exact timing and clock precision blocks for the last quantity;
position itself must not receive an invented calibration prior. Whiten/scalings
must be specified, especially since a raw eigenvalue compares km, seconds, Hz
and clock coefficients with different physical units.

For a PSD block matrix partitioned into position x and nuisance z, the Schur
complement `H_xx − H_xz H_zz† H_zx` measures remaining quadratic sensitivity
after nuisance relaxation, with a declared SVD rank tolerance and range check.
If H_zz is singular and cross terms are outside its numerical range, report the
condition instead of forcing a plausible matrix. For an indefinite observed
Hessian, ordinary PSD/Fisher profiling arguments no longer automatically apply.
Report eigenvalue signs and qualification rather than blindly applying the same
interpretation. Prior precision can stabilize nuisance directions that are weak
in the data, so weak data sensitivity alone is not proof that the full regularized
fit is unidentifiable.

Active bounds alter feasible directions. At a fixed active face, use the scaled
tangent nullspace of actual active normals and locked coordinates; coupled timing
constraints are not coordinate-wise clipping. This is face-conditional sensitivity,
not the entire feasible cone: an active inequality can allow inward perturbations.
Show interior/unconstrained and active-face diagnostics separately, with active
rank and tolerances, rather than declaring constrained directions physically
observed. An operational bound may stabilize a fit without supplying RF evidence.

## Tests and permitted decisions

Synthetic checks should compare analytic prediction columns to finite differences
for every parameter block; compare the complete-data proxy to an explicit known
Jacobian; verify the missing-information subtraction on a small affine mixture
against objective finite differences; exercise ambiguous/clutter and separated
labels, rank-deficient nuisance, prior stabilization, receiver exchange,
satellite permutation, c=0 locks and coupled active constraints.

Use these diagnostics to explain where position sensitivity is absorbed by
nuisance, identify redundant parameterizations and formulate globally frozen
model/search experiments. Do not infer calibrated kilometre error bars, select
scan-specific priors, choose winners by reference error or discard weak scans.
Complete membership and failures remain visible. A cheap proxy can be useful on
embedded hardware if labeled honestly and benchmarked; it cannot certify accuracy
or replace independent convergence and out-of-sample localization checks.

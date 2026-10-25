# Amendment 02: nonlinear target phase integration

Date: 2026-10-25. Status: approved for bounded preparation only. No new position
fits are authorized until the independent numerical and input audits pass and
the coordinator writes a go receipt. This amendment supersedes the target-phase
Gaussian approximation in COORDINATOR_PLAN.md; all other ownership, comparison,
budget, reporting and stopping rules remain in force. Preparation01 is retained
as an explicitly rejected approximation, with zero new position fits.

## Why the first approximation was stopped

The independent direct-propagation check found 115–129 Hz of nonlinear phase
error for DS24-0095 at one original prior standard deviation, after removing a
constant and local phase derivative. The deleted shape prior projects to about
34 Hz under the same projection. DS24-0087 has about 1.42 Hz versus 0.86 Hz.
These errors can confound the proposed covariance comparison. They do not show
that the original baseline, which refreshes its local phase references, has the
same error. No new position result was produced using the rejected approximation.

## Prior and phase domain

Integrate the new target's original causal Student distribution, with its
original location, scale and degrees of freedom (nu = 3), CONDITIONED on the
existing operational phase interval [-15, +15] seconds. This is an explicit
domain-conditioning choice, not an unchanged marginal mean or variance. Derive
Student scale from the original marginal standard deviation as
sd * sqrt((nu - 2) / nu). Divide the density by its exact interval probability.
Do not recenter, rescale, clip quadrature samples, or tune the prior from position
error. Report both original parameters and conditional moments:

| Case | Original location (s) | Original marginal SD (s) | Removed prior mass | Conditional mean (s) | Conditional SD (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS24-0095 | -2.296774 | 6.282140 | 2.846380% | -2.132187 | 4.567776 |
| DS24-0087 | -0.359190 | 0.732391 | 0.004943% | -0.359137 | 0.709302 |

These are engineering-prior quantities. Domain conditioning affects both new
branches equally. Comparisons to saved Gaussian/graph controls change more than
shape covariance and must be described accordingly. No full-prior claim is made.

## Common nonlinear predictive likelihood

At every phase node, propagate target Doppler directly and evaluate its physical
shape-mode columns at that phase. The branches share phase nodes, normalized
prior weights, parent state, target noise, source-constant prior, observations,
candidate identity and aliases. Their sole difference is zero shape covariance
versus the unchanged three-mode physical shape covariance at scale one.

Let C denote parent curved observations, E original predictive observations, T
the new source, and phi its phase. Evaluate

    p(E,T | C,x) = p(E | C,x) * integral p(T | E,C,x,phi) p(phi | domain) dphi.

Retain shared parent-calibration covariance between E and T. A Schur conditional
or independently verified equivalent factorization is acceptable. At each node,
integrate Gaussian parent/shared, source-constant and (in the prior branch) shape
uncertainty, including quadratic, determinant and density normalization. Use
log-sum-exp for the phase integral; a best phase or average phase score is not
the integral. Do not append a second phase Gaussian or reuse a dormant family
slot. Parent calibration, Gamma precision and phase references remain independent
of target CFO at fixed x. Updating the conditional prediction algebraically from
E is not permission for target calibration feedback.

The existing parent variational/Gaussian approximation remains; this amendment
only removes the new target's first-order phase approximation. Preserve parent
cached objects, and independently test repeated evaluations and target redaction.

Audit target visibility over the phase integration domain. If a phase node has
invalid propagation, do not silently drop or clip it. Document visibility rules
and keep any target qualification separate from likelihood membership. If the
entire domain is visible at all tested positions, record that directly. A new
position-dependent visibility truncation requires a further explicit amendment.

## Numerical freeze and bounded execution

Before fits, choose a fixed common quadrature rule using RF-only convergence
tests at saved baseline/support positions, a common midpoint, and the regional
start for both c arms. Audit both covariance branches. Check actual normalized
target scores and position finite differences, not just prior moments. Compare
against a denser rule and an independent integration construction capable of
detecting narrow or separated likelihood modes. Record the finite-difference
step, absolute/relative errors, node count, run time and propagation support.
Numerical tolerances and hard node cap must be written before scientific launch.
Use the same frozen rule throughout each optimizer; no position-dependent rule
selection based on position accuracy. If quadrature fails, close preparation or
retain only explicitly qualified fixed-position diagnostics.

### Predeclared numerical rule, before any fits

The independent math auditor ratified absolute errors of at most 1e-3 in
negative-twice log target density and 1e-3 objective units/km in each position
finite difference, using a 0.01 km step. Candidate common phase-space
Gauss–Legendre orders are 81, 161, 321, 641, 1281 and 2561. One globally fixed
order must pass all declared case/arm/branch/position checks before fitting,
including comparison with a denser rule and independent adaptive integration
with explicit narrow-mode checks. The hard production node cap is 2561;
an unresolved result at that cap is no-go, not a license to extend it. The exact
Student CDF supplies domain normalization; quadrature prior-mass error must be
at most 1e-8. Preparation has a 600 second numerical cap. These thresholds and
the tested alternatives were specified before any new position endpoint.

The original maximum of eight new fits, two numerical workers, one BLAS thread,
180 seconds per arm and 20 minutes total scientific propagation remains. Time
the preparation separately and keep it bounded. If adequate quadrature makes
the fit budget infeasible, publish the fixed-position mechanism test and its
limits instead of extending into a campaign. Do not retry statistical failures.
All geographic readouts follow the RF seal. There is no new ALGO promotion or
cohort expansion authorized by this two-case diagnostic alone.

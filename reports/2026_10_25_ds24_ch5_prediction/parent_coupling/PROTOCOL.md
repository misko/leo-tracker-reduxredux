# One-family active-parent B(phi) control

This is a normalized **frozen-Gamma conditional Gaussian** diagnostic, not the
original full Student/VI evidence or a production replacement. Current parent
geometry evaluates nominal Doppler and physical modes at the saved phase
reference, uses an affine phase column and refreshes references between fits.
The specific omitted dependence is changing those existing three physical-mode
columns with the integrated phase. No missing modes or covariance are appended.
The prior blanket covariance experiment and already dynamic target/identity
kernels answer different questions.

Select DS24-0010/0011 chronologically. From each old c0 RF information diagnostic,
use its joint curved/predictive information if present, otherwise curved, and
choose the largest absolute phase/weak-axis correlation among families already
having all three physical modes (NORAD tie break). This selects 63069/63936.
No fallback family is chosen if its actual source layout disagrees. Freeze the
old c0 weak axis/precision and same saved c0 RF center for both c arms. Use offsets
−0.05, −0.025, 0, +0.025, +0.05 km: 20 fixed case/arm/probe contexts, no optimizer.

At each arm's common center obtain original curved VI noise and coefficient
prior precisions once. Freeze those for every probe. Other phase means/priors,
receiver/smooth terms, native noise, likelihood powers, aliases, curved fragment
constants and predictive-only constants retain their original Gaussian roles.
Predictive noise retains the unseen Gamma inverse-moment factor two. Fractional
powers are represented by their equivalent frozen Gaussian variances; differing
original generalized/VI constants are common to the branches, not relabeled as
a full unchanged evidence model.

Remove the tested family's existing phase column and **all three** mode columns
from the joint curved-plus-predictive design. Integrate every other Gaussian
coordinate jointly, conditioning the tested-family rows on all other data.
Its phase law is Normal(original causal mean,
phase_sigma/sqrt(original conditional prior precision)), explicitly conditioned
on [−15,+15] s without recentering. Export both original quantities and lost
mass. This conditional Normal is not the original marginal Student prior.
The original three mode coefficients retain their original Gaussian precision;
dynamic and frozen columns are scaled identically by its inverse square root.
No learned same-family posterior is reused as a second independent prior.

Both branches use the **same exact nonlinear nominal f(phi)**. Branch F uses
B(saved reference); branch D uses B(phi). All level/phase overlap of the full
three columns remains. The selected-family affine intercept is removed when
exact f replaces the phase column. Require original affine-f/frozen-B full
Gaussian = other-data Gaussian + selected conditional Gaussian closure within
1e-5 objective units; require reference f/B replay within 1e-7 Hz. Require full
nominal visibility on the operational phase domain using the existing support
certificate. Otherwise stop with concrete matrix/source evidence; no new
support convention or replacement case is introduced.

Integrate using Gauss-Legendre 81/161/321 in the analytic affine posterior's
truncated-Normal CDF coordinate, preserving prior/proposal domain normalizers.
Use a separate direct-phase adaptive reference partitioned by a fixed 31-point
global grid and affine posterior mean ±{0,.5,1,2,4,8} SD. Export proposal center,
SD, sampled phase ranges, prior/proposal masses, edge/max weights and reference
errors. Require rank3/dense node agreement within 1e-5. This is a resolved-mode
stability check: a narrow proposal plus finite grid cannot certify the absence
of every remote nonlinear mode. Do not claim global absolute precision.

Resolved numerical qualification requires score differences 321-vs161 and
321-vs-independent-reference ≤1e-3, adaptive relative error ≤1e-6, and gradient
disagreement ≤1e-3 units/km. Weak-direction gradient uses symmetric 0.05/0.025 km
differences. Require their agreement within max(0.01 units/km,5% gradient).
For delta J=J_dynamic−J_frozen and old weak precision lambda, the local movement
proxy is −delta-gradient/(2 lambda). This is not a new estimated position.
Materiality is ≥25 m (5% of the 500 m accuracy aspiration) **and** >5 times its
numerical displacement-error proxy. Continue only if both c arms are resolved;
record sign differences and do not choose an arm from geographic improvement.
Stable smaller effects close this tested conditional neighborhood; unresolved
effects close without an optimizer and do not prove all parent coupling absent.

Cap all tests/preparation/scientific processing at 300 cumulative seconds, one
worker, BLAS/OMP/MKL one thread. Freeze source/input protocol and tests, then
require B's exact matching independent preflight before corpus preparation or
RF integration. Preserve every partial output on failure/deadline. No retries,
new draw campaign, position fits, GPS, IQ, RF collection or production changes.

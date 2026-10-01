# Localization approaches: methods and pilot evidence

Status: methods frozen; official 64-scan A1/B1 comparison in progress. This
document describes the estimators and the evidence used to admit them. It does
not contain or anticipate official benchmark results.

## Common observation model

Every recording starts independently from the same uniform horizontal prior on
the 250 km Sacramento map disk. Receiver height is fixed at 30.48 m above mean
sea level and converted to ellipsoid height with the pinned GEOID18 surface.
The retained tracks, selected samples, causal satellite catalogue, extended
orbit bank, and exclusions are common to all approaches.

For track $j$, candidate satellite $s$, and joint state $x$, let

\[
  \ell_{js}(x)=\log a_{js}(x)
    +\log t_4\!\left(y_j;\mu_{js}(x),S_j\right).
\]

Here $y_j$ is the observed, frequency-offset-projected Doppler shape;
$a_{js}$ is the normalized association opportunity prior; and $t_4$ is a
normalized multivariate Student-t density with four degrees of freedom. The old
Gaussian covariance $S_j$ is used as the Student-t scale, so the distribution's
covariance is $2S_j$. Each track also has a normalized background branch
$\ell_{j0}(x)$, which preserves probability for clutter, missing catalogue
objects, or tracks not explained by a visible candidate.

The shared state contains horizontal position, receiver time-tag offset, two
receiver drift coordinates, and one epoch offset per catalogue satellite. The
timing and drift coordinates retain zero-mean Gaussian regularization: clock
σ=1 s, satellite epoch σ=0.5 s, and receiver drift σ=0.5 Hz/s. These
terms stabilize nuisance directions; they do not make the resulting location
uncertainty calibrated.

All methods begin from the same three seeds produced by the deterministic broad
acquisition. That acquisition searches the location disk and is charged to each
arm's runtime. The seeds initialize local searches and do not add observations
or replace the original prior.

## A1: faster hard-association robust MAP

A1 minimizes

\[
  J_{\mathrm{hard}}(x)
   =\tfrac12(x-m)^T P(x-m)
    -\sum_j \max_{s\in\{0,\ldots,M\}}\ell_{js}(x).
\]

At an outer iteration it scores every satellite and background branch, chooses
one branch per track, constructs a Student-t IRLS step from only the selected
satellite branches, and accepts a damped step only when the fixed-assignment
physical objective decreases. It then recomputes all assignments. The three
seed results remain separate; the lowest-objective attempted seed wins even if
that winner is numerically unresolved.

A1 changes evaluation cost rather than the intended inference. Full-catalogue
means are used for reassignment, while line searches evaluate only the selected
normalized branch and state updates request derivatives only for selected
satellites. The implementation retains the old priors, Student-t likelihood,
background normalization, support, 24-iteration cap, damping, convergence
rules, and seed policy. Full and selected scores are cross-checked at each
assignment.

This method addresses repeated unused Jacobian and catalogue-prediction work.
It does not soften an early identity decision within an iteration, prove that a
selected satellite is physically correct, find a guaranteed global optimum, or
produce a calibrated posterior distribution.

On the three F001 pilot scans, A1 converged on all three and reproduced the
existing solver's horizontal errors within $2.8\times10^{-5}$ m. Under the
final 50 s common acquisition budget, its end-to-end runtimes were 55.6, 54.5,
and 47.9 s, compared with 85.7, 85.6, and 75.1 s for the contemporaneous oracle.
These three development scans establish numerical agreement and a measured
pilot speed benefit; they do not establish the 64-scan speed distribution.

## B1: full soft-association robust objective

B1 replaces the per-track maximum with an exact finite mixture:

\[
  J_{\mathrm{soft}}(x)
   =\tfrac12(x-m)^T P(x-m)
    -\sum_j \log\!\left[
      \sum_{s=0}^{M}\exp\{\ell_{js}(x)\}\right].
\]

The responsibility of candidate $s$ for track $j$ is the normalized branch
contribution inside that log-sum-exp. B1 includes the background branch and all
numerically positive satellite responsibilities in both the objective and the
derivative; the admitted configuration has no top-k truncation or subset
renormalization. Position-dependent visibility and background normalization
therefore remain part of the model.

For a local proposal, B1 combines each responsibility with the Student-t IRLS
weight

\[
  \lambda_{js}=\frac{4+d_j}{4+q_{js}},
\]

where $d_j$ is the track contrast dimension and $q_{js}$ is its squared
Mahalanobis residual. It freezes those weights while forming a joint damped
least-squares proposal, including the same Gaussian nuisance regularization as
A1. Every proposal is accepted against the actual full soft objective rather
than the quadratic surrogate. Compact Jacobians and block assembly reduce the
linear-algebra cost without changing which mixture branches contribute.

B1 addresses premature hard association: several plausible identities can
guide a state update simultaneously. It remains a local optimizer from three
acquisition seeds. Its responsibilities are conditional model weights, not
independently verified satellite identities. Its objective values are not
posterior mode probabilities, and the method does not justify averaging
geographically distinct solutions or reporting calibrated credible regions.

The pilot exposed the expected computational cost. The first DS9-F001 attempt
was unresolved at 85.2 s. On the three-scan stress panel with the allowed second
stage, B1 converged on DS9-F080 and DS10-F131 with horizontal errors 2,375 m and
4,694 m and cumulative runtimes 85.1 s and 166.4 s. DS11-F087 remained unresolved
after 170.2 s; its 2,174 m reference error is diagnostic only and is excluded
from accepted-error summaries. This was sufficient to admit B1 as an accuracy
and completion challenger, not evidence that it improves either.

## C1: timing-gauge profiling control

The Doppler likelihood depends on receiver clock offset \(\tau\) and satellite
epoch offset \(\delta_s\) only through

\[
  d_s=\tau+\delta_s.
\]

C1 removes that exact likelihood gauge and optimizes the effective shifts
$d_s$. It reconstructs the unique clock/epoch split that minimizes the original
Gaussian MAP penalty. Equivalently, the profiled shift precision is the inverse
of

\[
  \Sigma_d=\sigma_\delta^2 I+\sigma_\tau^2\mathbf1\mathbf1^T.
\]

This is profiling of the original MAP objective. It is not marginal likelihood:
no determinant reward is introduced for eliminating a coordinate. C1 also
solves the two shared receiver-drift coordinates in a weighted quadratic IRLS
proposal, then accepts the reconstructed state only against the original
Student-t hard-association objective. Thus the drift solve is a proposal, not an
exact analytic marginalization or exact Student-t profile.

C1 addresses a redundant timing direction and tests whether better numerical
conditioning reduces work. It leaves hard association and the physical model
unchanged. It cannot identify receiver clock and satellite epoch separately
from these observations, remove orbit/model bias, or supply Bayesian evidence.

On the three F001 pilot scans, C1 converged to effectively the same locations as
A1: its horizontal errors differed by 0.0010, 0.0037, and 0.0011 m. Its runtimes
were 29.2, 30.8, and 18.7 s, versus 10.1, 10.4, and 6.0 s for A1 in that
seed-conditioned pilot. Because it added cost without an observed accuracy or
completion benefit, C1 was stopped after development and was not admitted to
the official 64-scan comparison.

## Scope of the comparison

Only A1 and B1 are frozen for the official benchmark. Each is evaluated on the
same 64 DS9/DS10/DS11 recordings with fresh acquisition, a 90 s primary limit,
and at most one status-triggered continuation for 180 s cumulative time.
Reference coordinates are read only by the evaluator after prediction and
receipt sealing. Results will report unresolved and failed scans in the common
denominator. Numerical convergence will remain separate from location error,
satellite correctness, and uncertainty calibration.

Final error percentiles are conditional on accepted numerical outcomes and are
reported beside accepted counts and failure-inclusive 64-scan ECDFs. Paired
error differences use only scans accepted by both methods, with the paired
denominator shown explicitly. Primary results are compared with the bound
historical primary control; results after an allowed continuation are compared
with the bound historical two-stage control. Runtime summaries include every
attempted scan, including unresolved and failed outcomes. The historical control
used a 40 s acquisition sub-budget while the prospective arms use the frozen
50 s common sub-budget, so end-to-end timing comparisons retain that scheduling
difference.

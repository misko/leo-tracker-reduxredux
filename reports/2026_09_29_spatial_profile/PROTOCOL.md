# Frozen local spatial and finite-displacement timing profiles

Evaluate the original q020 model at its training-selected coordinates/timings
on all eighteen consecutive panels. Preserve banks, masks, likelihood scales
and every track. This extends the earlier DS7 slope identifiability diagnostic
to the current model and all three datasets; it is not another slope fit.

Compute the observed negative Hessian by central differences of the complete
training gradient, with position steps .002 km and timing steps min(.0001 s,
half the distance to the nearest .25-second interpolation node). Repeat at
half steps. Require every timing half-step >=1e-5 s and no node crossing.
Symmetrize each matrix; require relative raw asymmetry <=1% at both scales,
positive timing and profiled spatial blocks, and relative Schur-complement
change <=1%. Preserve failed curvature results; do not change steps to rescue them.
Check the original training score and gradient against the published artifact
within 1e-7. Candidate visibility must remain unchanged across Hessian stencils.

Profile local timing with the Schur complement of the timing block. Report its
two eigenvalues, eigenvectors, and sqrt(2/eigenvalue) km as the local distance
for a one-nat quadratic score loss. This is a likelihood-shape diagnostic, never
a calibrated error radius or confidence interval.

For qualified curvature, test both signs of both spatial eigenvectors at
.25 km and 1 km from the training-selected point: eight fixed positions. At
each, optimize timing only within ±5 s from two starts: original timing and the
linearized profile prediction clipped to the bounds. Use L-BFGS-B, maxiter=80,
maxfun=120, ftol=1e-14, gtol=1e-8, maxls=30. Qualify success, no bound within
.001 s, and max absolute timing gradient <=.01. Select by training score only.
Retain all failures. Offsets outside E/N ±12 km are reported unavailable.

At every selected timing profile, check derivatives using .0000625 and
.00003125 s steps: discrepancy and step disagreement must be <.002, with no
node crossing. Compare finite training-score losses with the local quadratic
prediction, and report held-score changes separately. Flag horizon-visible-set
changes from the center; do not mistake them for smooth local geometry. No
reference coordinate enters direction construction or timing selection.

One sequential child per panel, BLAS1/nice19, timeout90s, AS4GiB, available RAM
>=5GiB. Five synthetic tests cover known nuisance response, exact profile,
unidentifiability, invalid timing information, independent minimization and
step stability. Sources/inputs frozen before execution; no retries. Any timed-out
panel remains incomplete. No new RF, raw IQ, propagation or provider reads.

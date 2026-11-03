# Position-information audit of orthogonalized curvature

Use exactly the 1,732 supported tracks from curvature_transfer, at the inherited
fitted geography/timing and physical candidate assignment. Compare free slope
and orthogonalized quadratic nuisance terms on this same population. Remove
each track's constant, retain its linear position sensitivity, and profile
the eight recording-time directions jointly with each nuisance model.

For curvature z, regress centered time squared (seconds squared) against
[1, centered time] using training samples and retain the residual. Use physical
seconds squared, not independently scaled track coordinates, so a shared
coefficient represents common Hz/s². Share coefficients within recording,
candidate, exact RF; also report independent per-track coefficients as a
more flexible bound. No curvature prior, held samples or geographic reference
enters this conditional local design audit.

Reuse the earlier candidate_information contrast-design weight and Schur
complement calculation. This is a conditional local information proxy, not
the full mixture Hessian or calibrated uncertainty. Check residual replay
<1e-7, timestamp/mask equality, candidate visibility and finite differences
at full/half steps. Require retention changes <=0.001, timing knots farther
than the largest timing step, and eigenvalue retentions in [0,1] to tolerance.
Report every panel; no post-hoc information threshold defines model success.
Bound execution to 120 seconds. No new RF or geographic fitting.

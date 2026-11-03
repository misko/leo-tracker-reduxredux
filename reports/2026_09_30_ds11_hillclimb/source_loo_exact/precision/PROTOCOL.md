# Saved-endpoint precision diagnostic

This is a bounded numerical diagnostic of the already saved, unqualified
index-4 `robust_t8_scale100` source-deletion endpoint for physical NORAD 65855.
It performs no minimization, candidate selection, geographic-error evaluation,
or additional source holdout fit.

Reconstruct the retained model from the immutable exact-screen plan, original
input artifacts, frozen original-IID source assignments, and the saved failed
fold. Require exact assignment, source-weight, omitted-track, endpoint, session,
result-source, and receipt bindings before evaluation. The independent restart
result and receipt must show the same point, score, held score, and unsuccessful
optimizer status.

At the saved point, use the original coordinate steps `(1e-4, 1e-4, 1e-5)` and
half steps to estimate the observed negative Hessian from central differences
of analytic score gradients. Report raw and symmetrized matrices, relative
asymmetry, eigenvalues, condition number, and relative step-halving change.
Compute the stationary Newton displacement `H^-1 g` from the symmetrized
original-step matrix when it is finite and nonsingular, and report the
corresponding east/north and time displacement.

Evaluate score and analytic gradient at saved-point plus the Newton displacement
scaled by `0, 0.5, 1, 2`, provided each point remains within the existing
bounds. Separately audit every analytic gradient coordinate using central score
differences at double, original, and half steps. Persist all finite values,
source hashes, and elapsed time. The diagnostic has no advancement rule and
does not alter the exact-screen failure; it only characterizes whether the
saved point is at a stable numerical floor.

Run once with one BLAS thread and a 90-second process cap. Preserve any timeout
or nonfinite result without retry.

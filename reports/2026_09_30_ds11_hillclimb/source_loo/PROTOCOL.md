# Source-level leave-one-NORAD-out influence diagnostic

Status: prospective phase-one protocol. This phase computes local influence
diagnostics only; it does not run deletion refits, score held observations, or
inspect reference coordinates or geographic errors.

Run only original DS11 indices 0 and 16. Compare exactly four existing,
qualified endpoints: original IID Student-t4/100, `source_receiver_equal`,
robust Student-t8/100, and robust Student-t4/200. Every endpoint and model
source is digest-bound in the result.

Freeze membership once per scan from the original same-scan IID endpoint and
the existing candidate-ID-to-NORAD sidecar. A track is assigned only when its
training-only conditional candidate probability is at least 0.90. The fold key
is physical NORAD across all receivers and RFs. NORADs with at least two tracks
are eligible. Ambiguous tracks stay in every retained objective. Candidate
mixtures are not shortened.

For family `f`, source `g`, and its already-fitted endpoint `theta_f`, compute
the exact source score gradient `u_fg`. Compute observed negative Hessians by
central differences of analytic gradients at fixed steps `(1e-4 km, 1e-4 km,
1e-5 s)` and again at half those steps. Because every objective is additive by
track, obtain the retained Hessian as the full-objective Hessian minus the
source-only Hessian. This is algebraically the exact finite-difference retained
Hessian and avoids repeatedly evaluating all retained tracks. For
`source_receiver_equal`, derive weights once on the full scan and carry each
surviving track's weight unchanged; never renormalize after deletion.

The frozen influence estimate is

```text
theta_IF = theta_f - inverse(H_f,-g) u_fg.
```

Record the endpoint's full gradient and the separate optimizer-residual
correction `inverse(H_f,-g) gradient_full`; the frozen influence estimate does
not apply that correction. Also record the endpoint timing coordinate's
distance to the nearest 0.25-second orbit interpolation knot.

A fold is available only if both retained Hessians are finite, their relative
antisymmetric norm is at most 0.005, the symmetrized primary Hessian is positive
definite, its condition number is at most `1e10`, primary-versus-half-step
relative Frobenius disagreement is at most 0.005, and the influence estimate
is inside the unchanged `[-12,12] km` E/N and `[-5,5] s` bounds. Do not ridge,
clip, retry, or change derivative steps.

Within each family, rank folds by predicted E/N displacement, using the smaller
NORAD for a tied largest displacement and ascending NORAD within the complete
ordering. Persist the largest and the lower median (`(n-1)//2`) source before
any exact refit only when every eligible fold is available. If any fold fails,
mark formal selection unavailable; an explicitly exploratory available-fold
rank may be recorded but cannot substitute for the failed fold or qualify the
scan. Report both eligible and available denominators. No exact deletion refit
is authorized in this phase.

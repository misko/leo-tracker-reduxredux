# Stationary offset solver and diagnostic position refits

The new scalar solver passes convergence checks on all 566 candidate fits in
44 numerically selected tracks spanning all 43 scans, including the candidate
that failed the preceding 2000-iteration IRLS audit. Maximum absolute
penalized-likelihood derivative is 1.16e-14 per Hz; all selected roots have
positive loss curvature. This resolves the tested numerical failure without
claiming global scalar optimality or improved DS6-wide location accuracy.

Each scan contributes its largest absolute training-score change from the
prior iteration audit, plus every track with an unconverged visible candidate.
Selection reads no geographic error. On those tracks, total training score
changes by +133.46 and held score by +77.56 versus the original 12-step solver;
one MAP candidate changes. These selected-track totals are not comparable as
population totals to the preceding all-track audit.

The solver uses nine training-residual quantiles plus the median, centered
IRLS initialization, derivative sign brackets and Brent root solving. It
retains only positive-curvature stationary roots and selects by training
penalized loss. The weak offset penalty is now part of optimization as well
as scoring. Narrow undiscovered modes remain possible under the finite
bracket scheme, so it is not presented as a proof of global optimality.
`max_roots` counts bracket solutions before deduplication, not distinct modes.

## Matched geographic isolation

Three scans were selected by numerical evidence: the two largest stationary
audit training gains, the earlier covariance-sensitive scan and the prior
unconverged scan (the first two criteria overlap). Only their audited tracks
use the new solver; every other track retains the old profiler. This isolates
the numerical effect and is not a complete estimator replacement. Each fit
uses two matched starts, fixed causal-element mixtures, unchanged random
whole-visit masks and training-only selection.

| Scan suffix | Original error | Selected-track correction | Held log-score gain |
|---|---:|---:|---:|
| a077447f07d9f81f | 2.179 km | 3.178 km | +68.68 |
| a38d2f57a8974b96 | 2.355 km | 2.316 km | +40.92 |
| 53ce822d78d476ba | 2.045 km | 2.036 km | -1.79 |

All three winners converge inside bounds. Exact propagation agrees with the
interpolated winning training scores to within one log-score unit. The
reference is read only by the post-fit summarizer and never selects tracks,
offset modes, starts or parameter values. No tested result reaches 1 km.

Five tests pass: multimodal synthetic loss comparison against a dense grid,
held-data isolation, all selected real candidate convergence and provenance,
agreement of the selected-track correction with direct likelihood scoring,
and frozen real-refit selection and exact-propagation score checks. The old
failed iteration audit remains unchanged; its failure is not hidden.

No estimator is deployed or accepted as a sub-kilometre individual-scan fix.
The historical corrected baseline still has 6/43 sub-kilometre scans and the
historical joint estimate is 761.85 m; those figures use the old offset model
and have not been revalidated under a full stationary-offset replacement.
The remaining work includes efficient all-track stationary profiling with
candidate/mode completeness checks, followed by matched geographic refits.
This diagnostic must not be used to keep an unconverged solver merely because
its output happens to be closer to the reference.

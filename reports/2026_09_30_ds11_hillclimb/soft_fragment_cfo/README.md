# Soft CFO coupling for disjoint same-source fragments

Status: implementation and fixed-endpoint diagnostics are ready; no position fit
has been launched.

This family implements the frozen [`SOFT_CFO_DESIGN.md`](../same_source_cfo_audit/SOFT_CFO_DESIGN.md).
Both variants use the exact same 76 training-frozen, disjoint, same-receiver,
same-exact-RF track pairs.  All other tracks retain the original IID Student-t4
profile likelihood and candidate mixture.

- `identity_only` uses one latent common physical NORAD per pair, mixes over the
  full retained candidate intersection, and profiles the two weakly regularized
  CFOs independently.
- `gamma1000` uses the same candidate support and adds one fixed 1,000 Hz native
  wrapped-Cauchy CFO-difference factor.  The period is exactly `1/4.4 us`, so no
  candidate-dependent alias branch is selected.

The offset calculation remains a profile likelihood; its conditional retained-bank
weights are not calibrated physical-identity probabilities.  The treatment uses
the highest qualified stationary profile found by a finite multimode search.  It
does not claim a certified global two-dimensional maximum.  Every selected
profile records scalar mode counts, joint starts and roots, terminal gradient,
and the largest Hessian eigenvalue.  A predeclared score rule removes starts when
their separable scalar-mode score plus the maximum coupling factor is below an
already evaluated feasible point.  Because the subsequent root solve is
unconstrained and can cross scalar basins, this is a start-selection heuristic,
not a global pruning certificate.

## Preparation checks

Ten component tests cover original-IID no-pair parity, the common-candidate
mixture and one-catalogue denominator, infinite-width parity, wrapped-factor
alias invariance and exact Gaussian-prior normalization, pair symmetry,
multimode root selection, envelope gradients, a native training-frozen held
scorer, held-data isolation, track accounting, and frozen public-builder
membership.

[`fixed-endpoint-diagnostic-v4.json`](fixed-endpoint-diagnostic-v4.json) evaluates both
variants at the eight frozen original IID screen endpoints and performs central
finite differences for the treatment.  It performs no position optimization.
The earlier diagnostics through v3 are preserved as preliminary pre-freeze runs
and are superseded by v4, which binds the final source and protocol wording.

- Maximum finite-difference discrepancy: `2.98e-6`.
- Maximum selected CFO stationarity residual: `8.36e-10`.
- Worst selected maximum Hessian eigenvalue: `-3.48e-5`; all are negative.
- No joint-profile start failed qualification.
- Maximum projected standard four-start runtime: `56.50 s`, using 109 gradient
  calls (the observed maximum in prior four-start screens) plus 24 score-only
  audit calls.  This passes the fixed 90-second gate.
- The CFO term changes the endpoint gradient on every screen index; maximum
  absolute treatment-minus-identity component is `1.94`.  It is not negligible.

The bounded mode pruning reduced 1,080 located scalar-mode combinations to 149;
deduplication left 298 joint starts and 217 qualified roots across 98 paired
candidate profiles in the eight endpoints' recorded gradient evaluations (the
JSON preserves per-candidate details).  These counts describe
the fixed endpoints and do not guarantee equal complexity elsewhere in the
position bounds.  The 90-second process cap remains mandatory if a screen is
authorized.

The largest scientific limitation remains empirical-Bayes reuse: membership,
confidence, disjoint support, and the fixed width were obtained from original32
training data.  A geographic win on that panel would remain exploratory and
would require the frozen additional panel or another untouched validation.

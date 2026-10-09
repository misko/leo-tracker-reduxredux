# Explicit old-coarse compatibility proposal

This proposal can avoid recomputing up to46×400=18,400 historical fixed-point
coarse fits, if their source payloads are available and every condition passes.
That is a potential upper bound, not a measured runtime saving. No fit was run.
It does **not** claim the historical completed baseline had today's recovery policy.

## Source-equivalence evidence

The exact two historical hashes in [SOURCE_REVIEW.md](SOURCE_REVIEW.md) match
commit967566245. Inspection of their full diff to7d296d36d shows:

- Fitter objective construction, scaling, seed normalization, constraints,
  optimizer arguments, best-feasible tracking and returned physical vector/value
  are unchanged. The original same KKT arithmetic is moved into an audit helper;
  the0.001 acceptance threshold is unchanged. Optional terminal diagnostics add
  an evaluation after optimization and expose optimizer/returned-state differences.
  Stop-reason text changes for solver-success/nonstationarity, not qualification.
- Runner fixed-point bootstrap/objective/fit arguments are unchanged except for
  the diagnostics output dictionary. The configuration gains the recovery_policy
  field, changing policy keys; current recovery executes after ordinary regions.
- Current `hard60_recovery` seeds from original bootstrap or fit vector and uses
  independent `fit.converged`. Historical optimizer diagnostics are retained for
  reporting but do not select or seed recovery. Their absence must be labeled
  unavailable, never fabricated.

These narrowly justify testing reuse of original **bootstrap/coarse fixed-point
receipts**, not historical calibration, association, final or completed region
outputs. Objective/gradient implementation changes in any other dependency would
invalidate this equivalence argument.

## Testable admission contract

`old_coarse_policy.py` is a pure proposed metadata gate. It requires the exact
known historical pair, every other frozen required numerical dependency equal,
no unreviewed dependency, and old configuration identical to current after
removing only the new default recovery_policy. Only the already reviewed pure
renderer mismatch is excluded. It explicitly returns `reuse_authorized=False`:
metadata eligibility alone never enables a cache hit.

The eventual numerical adapter must then verify public checkpoint input/analysis
binding and payload digest, causal snapshot/evidence/prior/score/bank ordering,
bootstrap subset/vector, exact sampled point, finite feasible physical state and
saved objective agreement under the reconstructed current model. Recompute the
independent KKT if any qualification flag is used. Reject incompatible states;
missing coarse receipts stay explicit or are recomputed within the frozen budget.

Map only the historical baseline-config `point:east:north` key to current
`b7-shared:point:east:north` after those checks. Include provenance/alias reason
and old payload digest in receipts. Never strip arbitrary policy prefixes or
alias calibration/association/final/recovery/region keys. Continue current runner
all three separation passes, current original coarse recovery and all missing
calibration/final stages, then ordinary B7. Generic new recovery remains a separate
candidate comparison retaining the complete current ordinary baseline.

Eight synthetic metadata tests pass: exact pair, renderer-only difference and
rejections of unknown old hashes, changed/missing physical source, extra unknown
dependency, changed bounds and unexpected current policy. No optimizer tests or
recording loads were run. Runtime binding/objective checks and source-closure
completeness need actual-adapter tests before freezing any numerical extension.

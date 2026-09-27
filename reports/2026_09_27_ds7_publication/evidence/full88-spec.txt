# Full-DS7 execution and scoring specification

This specification is written before full88 predictions or scores. The target
remains all 88 minted DS7 recordings; partial groups and partial pooled results
cannot substitute for it. The site and some group scores have already been
exposed during development, so this is an exposed-corpus evaluation.

Use the existing immutable budgets plan's exact `full88` unit and the minted
dataset digest `47007b1c18e8182f6a005dfd05c237cb3edb9bf85ae6376c99ccf29d54434109`.
Do not construct a different unit or silently discard missing recordings.

## Frozen estimators

Evaluate all three existing independent-position controls: equal spherical
mean, inverse training-RMS-squared mean, and lowest-training-RMS 75% mean.
The equal mean supplies the direct unweighted pooled readout; report all three
without selecting members or weights from geographic errors. Require all 88
source-bound independent estimates to be present and qualified before running
a control. The 75% rule then retains 66 according to its original training-RMS
policy. Otherwise retain abstention or missing-input status explicitly.

Also attempt the unchanged joint scientific model through the optional
`config/ds7/baseline-wave4-batched-ready-v1.json` adapter if the resource and
input gates below pass. The wave-4 full-fit validation response was byte
identical to the frozen first-eight response. No starts, optimizer limits,
priors, masks, candidate banks, timing bounds or scientific configuration may
change for this attempt. Never use scored coordinates to initialize it.

## Input and execution gates

- All 88 observation/bank inputs must be frozen and validated, with exact
  dataset membership, source manifests, artifact hashes and eligible-track
  coverage. Existing prepared inputs remain unchanged.
- Every control estimate must match its qualified sealed source response and
  training-only RMS exactly. Verify run inventories and source linkage.
- Check host memory immediately before joint launch. Require at least 16 GiB
  available, serialize it against other DS7 preparation/fitting, and enforce an
  8 GiB address-space ceiling inherited by the adapter. If unavailable, defer
  this fit while completing the inexpensive controls.
- Joint adapter budget: one exact `full88` unit, at most 1,800 seconds, one
  CPU/BLAS thread and nice 19. Allow at most 120 further seconds around the
  runner for validation and sealing. Do not widen a running deadline or
  replace a timed-out attempt; retain its failure receipt.
- Each control receives at most ten adapter seconds. No raw IQ or RF
  collection is authorized by this specification.

The measured 24-document objective used 1.648 GiB peak RSS and 5.056 seconds
for one objective/gradient call. Linear full88 estimates are roughly 6 GiB
RSS and 18.54 seconds per call. An 8 GiB envelope appears plausible, but
heterogeneous captures and a 90-parameter optimization remain uncertain.
Approximately 63 calls could fit the time limit; 95 calls leave insufficient
overhead margin. These are planning estimates, not a convergence guarantee.
Evidence: [24-document measurement](../2026_09_27_ds7_wave5/resource-readiness/REPORT.md).

## Reporting and completion

Seal each prediction before reference scoring. Use the existing evaluator and
great-circle metric against the unchanged unsurveyed operator reference.
Report all four methods, convergence, boundaries, failures, resource usage,
all per-group and individual outcomes, and availability denominators. Preserve
the first chronological group's failure even if a pooled method succeeds.

Include the fixed inherited donor-coordinate diagnostic as context. Its
coordinator-only check, performed before full88 predictions, measured 809.03 m
without using any DS7 observations. A sub-kilometre fitted result therefore
does not by itself demonstrate useful information beyond the inherited site
knowledge. Report whether each observation-based estimate improves on this
fixed-coordinate distance. This diagnostic must not change the frozen models,
weights, membership, starts, or input preparation, and cannot substitute for
the full88 observation-based evaluation.

The active goal requires verified sub-kilometre performance for the complete
DS7 pooled estimate under this benchmark. A sub-kilometre group or selected
single does not satisfy it. No result on this exposed single-site corpus
establishes surveyed absolute accuracy or independent-site generalization.

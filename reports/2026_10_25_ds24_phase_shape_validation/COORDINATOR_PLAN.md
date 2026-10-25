# Fast-scan phase/shape separation and later-recording validation

Started 2026-10-25 at 18:39 UTC. Previous goal turn is **progress**: it completed
32 generating-component fits, 112 causal identity comparisons and publication
at main 5217788f231f9edce40ddca515a636a26bb97659. The persistent fast-scan
improvement objective remains active; no operational improvement was promoted.

## Parallel tasks

- SOL xhigh A (`plan_validation`): complete the two missing phase×shape
  generating cells on the same eight artificial realizations. Thirty-two
  paired c-arm fits, unchanged inference and all other latent/noise draws.
  Freeze protocol; B reviews before scientific launch. Two workers, one BLAS
  thread, 180 seconds per fit and 600 seconds cumulative numerical budget.
- SOL xhigh B (`plan_evidence`): independent preflight and terminal audit of A;
  a short design for later identity falsification, without a new search.
- SOL xhigh C (`next_validation`): validate the first eight chronologically
  selected complete later fast jobs using current full public contracts and
  exact identity/exposure bindings. Freeze membership before any error lookup.
  No IQ, inference, geographic evaluation or dataset mutation in readiness.
- Root: inspect and prepare a bounded new-recording comparison of the unchanged
  current reference and frozen shared RX1 RF-scaled 50 Hz model. Scientific
  fitting depends on verified inputs and a frozen reviewed execution protocol.

## Invariants

Preserve root tracked diff SHA256
add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b.
Use research outputs only, apply_patch for handwritten sources, no production
changes. No QNAP writes, new RF, postscan TLE inference, geographic selection,
stationary receiver pooling or reference-repository runtime dependency.

All localization comparisons retain matched c=0/fitted-c observations,
candidate sets, other priors and search budgets. Report fit/score, membership,
failures, runtime and geographic outcomes separately. The reference region
remains 25×25 km centered at 37.906,-122.545. Evaluation truth remains
37.849061591561885,-122.48574968092912, used only after decisions freeze.

Do not claim later recording inference completion means geographic exposure,
or absence from the old 24 means untouched validation. Reconcile exact recording
and content identities. Treat unavailable selected inputs as outcomes, without
replacement. DS24-0103's differing raw-authority hashes are a separate lead.

Publish the completed iteration with findings, figures, all declared failures,
new code, hashes and explicit replay limits to remote main. Do not create a new
ALGO version without a verified improvement supported by appropriate validation.

# Postseal geometry-preference evaluation

Preparation only: no reference reads. Publish a separate evaluation manifest
before evaluation. Authenticate all 12 members, 96 fixed-position fit receipts
and their claims before opening iteration 107's evaluation ports. Retain every
failed or unqualified fit and unavailable held score; no historical fallback.

For each final c arm separately, each geometry hypothesis has two nuisance
fits, one on each training fold. Sum the two opposite-fold likelihoods, scoring
every row once. All four fits and held scores must qualify for a preference.
An absolute summed-NLL tolerance of 1e-6 defines ties; ties and incomplete
comparisons remain unresolved. No cross-arm winner is selected.

Evaluate both geometry hypotheses only after the complete seal, using the
original geographic convention. Authenticate the pinned 107 evaluation
authority, evaluation-source closure inherited from 154, and session, input,
analysis, evidence and prior identities against the inference-only binding.
The source hypothesis label and final c arm are distinct identities.

Report 12-member and four-per-dataset coverage for each arm. Preference accuracy
uses only resolved comparisons with both geographic errors available and a
difference greater than 1e-9 km. Equal geographic errors are neutral, not
arbitrarily correct or incorrect. Explicitly report resolved, neutral,
incomplete and tied denominators. Report both hypothesis errors and the
preferred-error sensitivity with paired regressions, mean, median, p95 and
worst; incomplete preferences never receive an oracle or fallback estimate.

These hypotheses, banks, starts and satellite centers derive from full-data
inference, including the held rows. This is consumed-data conditional
discrimination, not unbiased cross-validation or independent validation.
Frequency likelihood and geographic accuracy remain separate. No choice
becomes an operational policy; production B7 and the official 193-member
metric remain unchanged.

The helper exposes collect(plan,digest,directory), prepare_evaluation and
evaluate. Collection contains ordered cells with hypothesis/mode/arm and raw
hashes. Only qualified cells reach geographic evaluation; errors are retained
explicitly. Report aggregation must never count the same fixed geometry's
repeated training fits as independent geographic observations.

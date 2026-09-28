# Baseline fitting after export preflight

First fit DS8-001 and DS9-001, the metadata-selected preflight records. Keep all
16 panel members frozen; do not replace or select later rows based on these
results. Validate all bank shapes, numeric finiteness, eligible-track coverage,
causal provider times and observation hashes before freezing each request.

Reuse the DS7 numerical request/response formats with actual DS8/DS9 dataset
digests and session identities. The full88 numerical config and unchanged fast
baseline adapter define the scientific model. The inherited execution-policy
string is historical metadata; the actual per-unit launch below is authoritative.

Run each fit once, capped at 180 seconds and 4 GiB, one numerical thread, nice19.
Retain the original three timing starts, optimizer tolerances and training-only
selection. Qualification uses the unchanged baseline definition: returned,
converged and no boundary. Keep all failures and estimates visible. This is
baseline measurement, not a hyperparameter search or a claim of new-site accuracy.

Seal requests, responses and input hashes before a separate scorer loads the
per-capture pose authority from the corresponding dataset snapshot. Use the
unchanged great-circle horizontal metric. Compute full-mixture held scores with
training-only offsets and weights. Do not use pose information in solver requests.
Individual-record results and later eight-record joint panels remain separate.

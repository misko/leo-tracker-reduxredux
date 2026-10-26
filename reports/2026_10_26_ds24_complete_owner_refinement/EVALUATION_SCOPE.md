# Fixed likelihood membership and endpoint-dependent compatibility

Pre-execution clarification from independent review: preserve original graph
ownership, curved/predictive likelihood IDs, candidate assignments and counts.
Those inputs are fixed by design. Postfit compatibility is evaluated at the
new endpoint and can change, so it must be recomputed and reported separately.
Apply original retained-ID and paired acceptance requirements; a position that
fails them remains a diagnostic endpoint. Do not force postfit association
counts to match or relabel a failure as operational improvement.

The native detector-to-likelihood CFO coordinate, sign and any fixed alias
offset must be established from the actual source and original point values.
Only the measured native CFO delta may change. If an alias is an additive
constant, preserve it; do not unwrap or reassign to improve the fit. Original
graph membership and polynomial degree choices remain fixed. Report exactly
which residual/compatibility checks use the corrected native values.

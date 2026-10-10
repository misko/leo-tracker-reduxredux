# Additional postseal provenance preflight

`postseal_preflight.preflight(plan, results, digest)` is read-only. Run it only
after all 193 resource-batch receipts are terminal. It invokes the frozen
`evaluation.authenticate` gate first, then checks contiguous slice identities,
actual slice evidence for completed phases, terminal/done consistency, expected
cross-phase statuses, and clean binding/document identity. A failed inference
binding remains a covered failure with no document to inspect. DS18's sealed
unpublished member may legitimately have a null mint manifest digest; its later
model and sanitized document identity still must match.

A successful search cannot be followed by an unexplained `not-run-search-failed`
continuation. An explicit dependency or binding admission failure is recorded
as a failure and retained for review rather than being silently treated as a
successful comparison.

An explicit dependency or inference-binding admission failure may seal a phase
after an earlier pending slice. Its pending finish remains recorded and the
terminal failure is accepted only with that admission marker; no retry is
authorized.

The inherited search `*.finished.json` format contains neither member label
nor slot, so this preflight can bind that finish only by its paired filename,
claim slot and terminal status. It cannot prove an arbitrary replaced finish
originated from the claimed recording. The raw byte hashes returned by the
frozen gate preserve the observed state. This preflight does not inspect model
fits, candidate positions, reference coordinates or position errors, and it
does not authorize a deployment or early geographic evaluation.

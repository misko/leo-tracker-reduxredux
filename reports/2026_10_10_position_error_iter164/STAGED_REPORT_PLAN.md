# Staged full193 report publication

Use `staged_report.py` only after all 193 numerical members have sealed. It
requires the frozen evaluation metadata to equal `evaluation_protocol.json`
byte-derived content and requires the immutable47e interpreter. The separate
postseal provenance preflight runs before the frozen geographic callback.
The runner then compares the receipt hashes observed by the preflight and the
evaluation, so a changed raw receipt cannot quietly pass between them.

The report is rendered in a temporary sibling directory. The runner checks
the complete file inventory, JSON round trips, all Markdown image references,
and decodes every PNG before writing an integrity map. A Linux no-replace
atomic rename publishes the completed directory as `sealed-full193-report`.
Any failure removes only its own temporary directory and leaves no final
report directory. An existing final directory is never overwritten.

The report remains consumed development evidence. Position errors are opened
only after the full193 preflight. The original frozen sources remain unchanged;
this entrypoint does not deploy a numerical policy or make unseen-validation
claims. An interrupted process can leave a hidden stage directory for manual
review; it must not be mistaken for a published final report.

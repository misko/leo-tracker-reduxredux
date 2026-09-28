# Checkpoint 01: complete reuse validation

All **148 reusable inputs pass** scientific loader validation. No export,
waveform read or new fit is performed in this checkpoint.

| Dataset | Manifest records | Validated | Missing exports | Ready for complete-dataset fitting |
|---|---:|---:|---:|---|
| DS7 | 88 | **88** | 0 | Yes |
| DS8 | 65 | 30 | 35 | No |
| DS9 | 105 | 30 | 75 | No |

| Validated data | Eligible tracks | Training observations | Held observations | Excluded tracks |
|---|---:|---:|---:|---:|
| DS7, all 88 | 5,131 | 143,207 | 95,894 | 11 |
| DS8, cached 30 only | 1,775 | 48,483 | 31,892 | 3 |
| DS9, cached 30 only | 1,822 | 50,530 | 34,216 | 2 |

Every recording remains in the ledger. Exclusions are the existing track-level
eligibility rules, not removed recordings. All 30 DS9 minted GLRT evidence
bindings match. Complete DS7 input readiness does not claim a new shared-scale
full88 geographic result; full-dataset fitting is a subsequent experiment.

All 148 validation processes exit zero. Summed job wall time is 165.23 seconds,
maximum individual time 1.81 seconds and maximum RSS 163,148 KiB. There are no
failures, timeouts, retries or headroom stops in this invocation. All original
artifact hashes, sample rates, causal provider snapshots and DS9 minted
bindings pass. The existing partition test passes. No component code changes.

[ledger.json](ledger.json) retains all 258 requested recordings and their exact
status, including the 110 not yet started. [panel-inputs.json](panel-inputs.json)
contains a complete ready input list only for DS7; DS8/DS9 cannot be mistaken
for complete datasets. [resource-summary.json](resource-summary.json) records
every validation process. [evidence-sha256.json](evidence-sha256.json) binds the
scientific dependencies, receipts and immutable checkpoint. The later publication
inventory additionally binds report text and bank archive descriptors.

Next: export missing DS8/DS9 inputs in fixed five-record batches, with the
single-worker headroom checks in the [protocol](../../PROTOCOL.md). Do not wait
on or interfere with production tracking to force a full-dataset geographic fit
under inadequate memory headroom.

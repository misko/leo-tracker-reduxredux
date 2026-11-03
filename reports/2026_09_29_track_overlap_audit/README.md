# Sparse repeated observation keys; broader track dependence remains unresolved

The 72-scan audit finds **67 excess observation copies across distinct tracks**, out of **198,806 observations (0.0337%)**. No repeated key appears in both training and held observations. No track repeats a timestamp internally. These are reproducible input-level findings, not a measurement of the resulting geographic effect.

| Dataset | Scans | Tracks | Observations | Reused keys / excess copies | Scans with reuse | Training/held crossover keys |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 24 | 1,434 | 68,744 | 21 / 21 | 11 | 0 |
| DS8 | 24 | 1,434 | 64,384 | 9 / 9 | 5 | 0 |
| DS9 | 24 | 1,460 | 65,678 | 37 / 37 | 6 | 0 |

[Full-precision summary](summary.json) · [Frozen protocol](PROTOCOL.md)

## Equality definition and limits

A reused key has the same scan, receiver, exact RF metadata, timestamp rounded to one nanosecond and measured frequency rounded to one microhertz, but occurs in distinct track IDs. Per-key track IDs and training/held membership are retained in the raw dataset outputs. This is an equality check on exported observations; it does not trace raw IQ sample provenance or establish whether detections were independently generated.

The audit rules out training/held crossover for this particular key definition and corpus. It does not rule out leakage through nearby measurements, shared processing, common signal structure, or repeated acquisition conditions. Nor does the small repeated-key fraction bound its effect on a nonlinear geographic fit. No weights or observations were changed.

## Similar-history check lacks eligible support

The frozen similarity diagnostic required two tracks with the same scan, receiver and RF metadata to share at least eight training timestamps spanning at least one second. **No pair meets that requirement.** Consequently, the report has no supported comparison of longer overlapping frequency histories. A zero count of similar pairs here is a lack of eligible pairs, not evidence that all histories are independent.

Exact RF and timestamp matching deliberately avoids interpolation or aligning potentially unrelated observations. It can miss dependencies between different carrier frequencies and histories sampled at different times. Broader physical dependence therefore remains unresolved.

## Next action

The repeated-key inventory supports a bounded deduplication sensitivity test: assign each repeated observation to one deterministic track owner, preserve source/held labels, and compare training score, gradient and resulting fit against the unchanged baseline. Any track that loses required support must remain an explicit failure rather than silently disappearing. Only a measured fitting effect would justify changing the research inputs or ingestion behavior.

Continue separating exact reuse from common-source correlation. Evidence that two tracks share a satellite or hardware error requires a different test; the present equality audit cannot support a general independence claim or a new correlation model.

## Validation and artifacts

All 24 scans per dataset were loaded from the existing hashed N24 manifests. The [runner](run.py) records every repeated key and every eligible history pair without geographic filtering. [test_overlap.py](test_overlap.py) verifies mean-offset removal, slope preservation, minimum support and receiver/frequency-key distinctions. Both tests passed. Processes completed successfully without retries under 120-second caps.

[launch.py](launch.py), [input/code hashes](manifest.json), per-dataset outputs and receipts, and [summarize.py](summarize.py) are retained. Summary generation verifies frozen hashes; exclusive creation prevents overwriting completed results.

No new RF collection, production modifications, golden-fixture changes or remote publication occurred.

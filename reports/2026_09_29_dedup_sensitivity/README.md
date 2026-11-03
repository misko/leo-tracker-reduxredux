# Repeated-key removal has a small local effect on pooled N24 fits

Removing the 67 extra observation copies in memory and locally refitting the three pooled N24 models moves their locations by **0.49–8.15 m**. All three reference distances become slightly worse. This test provides no useful geographic improvement and does not support prioritizing repeated-key removal as a route to subkilometre accuracy.

| Dataset | Removed copies (training / held) | Position shift (m) | Original reference distance (m) | Deduplicated-fit distance (m) | Matched deduplicated held change (nats) |
|---|---:|---:|---:|---:|---:|
| DS7 | 14 / 7 | 6.19 | 387.52 | 393.16 | +0.8213 |
| DS8 | 6 / 3 | 0.49 | 389.83 | 390.02 | +0.0506 |
| DS9 | 24 / 13 | 8.15 | 107.23 | 114.93 | +1.1916 |

[Full-precision results](summary.json) · [Frozen protocol](PROTOCOL.md)

## Controlled transformation

Retain each repeated key in the lexicographically smallest track ID, independently of reference position, fitted score or receiver preference. Slice observation times, frequencies, training masks and both candidate-state arrays together. Counts match the preceding independent overlap inventory exactly: 44 training copies and 23 held copies removed. All 4,328 tracks remain, with sufficient training and held support. No training/held label changes occur.

The transformation uses the previous scan/receiver/RF/time/frequency equality definition. Exported-key equality is not proof of shared raw-IQ provenance; this is a sensitivity experiment rather than a production deduplication policy.

All archived files remain unchanged. The modified documents exist only in each research process. Candidate arrays for changed tracks are sliced on the observation axis, preserving their candidate and timing-grid axes. Other metadata and candidate-bank membership remain inherited.

## Scores and interpretation

Each refit starts once at the original qualified N24 point. All three pass original optimizer, boundary, gradient and finite-difference gates. On the deduplicated observation support, refitting gains only 0.0409, 0.0022 and 0.0813 training nats for DS7, DS8 and DS9. The held changes in the table compare old versus new parameters on that **same deduplicated support**.

As a separate check, parameter changes evaluated on unchanged original observations yield held changes of +0.7733, +0.0535 and +1.1825 nats. No likelihood difference across different observation dimensions is treated as an improvement. Small held gains coexist with slightly worse reference agreement, consistent with the preceding evidence that this held score is not a calibrated horizontal-accuracy metric.

This establishes small **local pooled-fit sensitivity**, not a global bound. It does not test every short-window fit or rule out nonlinear mode changes under other removal choices. In particular, the two failing joint16 windows were not refitted here. Broader cross-track dependence and shared model error remain unresolved; the audit does not certify independence.

## Decision

Keep the repeated-key inventory as an input-quality finding, but do not alter production ingestion or retrospectively rewrite scientific inputs on this evidence. Prioritize mechanisms capable of explaining the much larger window-to-window disagreement. The pooled baseline remains geographically stable under this particular cleanup.

## Validation and artifacts

Two synthetic tests verify deterministic ownership, aligned candidate-state slicing, original-input preservation, explicit support failure and rejection of train/held crossover. Actual-data checks verify exact removal counts, preserved tracks and source score replay. The three numerical fits pass with no retries.

[dedup.py](dedup.py), [run.py](run.py), [launch.py](launch.py), [input/code hashes](manifest.json), all removed indices and owners, fit outputs and receipts, and [summarize.py](summarize.py) are retained. Summary generation verifies frozen hashes and evaluates geographic distances after fitting. Exclusive output creation prevents overwriting prior evidence.

The reference uncertainty remains unquantified and candidate banks remain site-conditioned. No RF collection, production modifications, golden-fixture edits or remote publication occurred.

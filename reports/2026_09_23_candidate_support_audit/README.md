# Conditional candidate-support audit

This audit compares the production-prior candidate union with an already-computed
full-catalogue training MAP. It covers the seven full-catalogue scans that intersect
the frozen 64-recording training partition, across the same five fixed coordinates.
No propagation or new data access was performed. Candidate identity, integer timing,
and CFO were selected only from each track's randomized training rows. Complementary
rows serve only as an inner diagnostic, not validation.

| Result | Value |
|---|---:|
| Scans | 7 |
| Track-location comparisons | 1,255 |
| Full-catalogue winners absent from conditional pool | 70 (5.58%) |
| Omission, 3–9 s tracks | 12.53% |
| Omission, 10–19 s tracks | 3.60% |
| Omission, 20–39 s tracks | 0.00% |
| Full-catalogue training MAP, training RMS | 189.27 Hz |
| Conditional-pool training MAP, training RMS | 189.49 Hz |
| Full-catalogue training MAP, reserved RMS | 200.35 Hz |
| Conditional-pool training MAP, reserved RMS | 198.67 Hz |

The shortlist does omit identities, especially on the shortest tracks. Across this
bounded sample, however, expanding to the full catalogue changes aggregate training
RMS by only 0.22 Hz and makes complementary-row RMS 1.67 Hz worse. That pattern is
consistent with extra identity flexibility fitting training noise; it does not show
that the shortlist is unbiased. The zero omission among 20–39 s rows suggests that
candidate support is a larger concern for short tracks than for longer arcs.

The comparison remains conditional on the five exposed development coordinates and
only seven training scans. The full-catalogue result artifact contains other sessions,
but the audit filters by the frozen training session IDs and emits no rows or summary
from any other partition. `candidate_support.json` binds the dataset, protocol, source
result, seven retention receipts, cache manifests, and audit source.

Reproduce with:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/audit_position_candidate_support.py \
  --dataset reports/2026_09_23_position_train_val_test/dataset/manifest.json \
  --protocol reports/2026_09_23_day_position_validation/holdout_protocol.json \
  --full-results reports/2026_09_23_day_position_validation/heldout/results.json \
  --retention reports/2026_09_23_day_position_validation/heldout/retention \
  --replication-root reports/2026_09_23_day_position_validation/replication \
  --joint-tool tools/research/sixteen_joint_compare.py \
  --output <fresh-output-directory>
```

# DS1: frozen multi-duration positioning benchmark

DS1 v1 names the existing long-duration dataset; it does not repartition or
relabel its historical results. The authoritative machine-readable membership
is [dataset.json](dataset.json), protected by [dataset.sha256](dataset.sha256).

| Partition | Eight-hour UTC groups | Recordings |
|---|---|---:|
| TRAIN | 2026-09-21 00Z, 2026-09-21 16Z | 72 + 79 = 151 |
| Validation | 2026-09-22 08Z, 2026-09-21 08Z | 44 + 80 = 124 |
| TEST | 2026-09-22 00Z | 64 |

Each group has frozen ordered 1/6/16/all prefixes, producing twenty cases.
Each case uses Sacramento-centred 250-km and Reno-centred 500-km search priors.
The groups contain capture gaps: eight hours describes a calendar interval,
not uninterrupted IQ. Duration views and two starts are correlated, not
independent replicates. This suite does not run every sliding window or every
recording individually.

Within each case, original randomized observation masks separate fitting from
held prediction checks. This inner split is distinct from the outer recording
partition. Whole groups stay in their original partition, with no scan overlap.
The original seed and exposure-aware group allocation remain bound through
the source manifest. No chronological within-track holdout is introduced.

Validation and partial TEST results were previously inspected. DS1 is therefore
a reproducible regression benchmark, not untouched evidence for a new final
accuracy claim. The known TEST recording at position 48 lacks full continuity
authority: full-64 results must explicitly fail until the underlying authority
is legitimately resolved; dropping it would change the dataset.

The baseline/shared-time comparison follows [PROTOCOL.md](PROTOCOL.md).
[DS1_AUDIT.md](DS1_AUDIT.md) records input coverage and scientific limits;
[BASELINE_PROVENANCE.md](BASELINE_PROVENANCE.md) records blind seed provenance.
Benchmark findings and plots are written separately in `REPORT.md` after
inferences have been sealed and evaluated.

Recreate membership without opening track or position outcomes:

```bash
.venv/bin/python reports/2026_09_24_ds1/freeze_dataset.py
```

The generated membership must retain the same seal for DS1 v1. A future corpus
or partition change needs a separately versioned dataset, not a silent update.

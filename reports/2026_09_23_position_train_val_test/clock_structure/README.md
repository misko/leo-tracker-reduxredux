# Train-only timing-structure diagnostic

This development-only diagnostic compares per-track integer timing, one shared
integer timing value per scan, and timing fixed to zero. It uses the first 48
day-inventory scans in replication blocks 01–03 and the first three original
development finalists. Candidate identity and a constant CFO are selected from
each track's saved randomized training rows only. The candidate pool is the
per-scan production-winner union, so this is not full-catalogue inference or an
independent validation result.

`inference.json` contains the train-only point scores and selections before the
reference-error append. `results.json` appends descriptive randomized reserved
row scores and reference errors afterwards. Both bind the three cache manifests,
the locations input and source hashes.

Reproduce from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/position_clock_structure.py \
  --replication-root reports/2026_09_23_day_position_validation/replication \
  --locations reports/2026_09_23_sixteen_scan_comparison/common_finalists.json \
  --output /tmp/clock-structure-reproduction

.venv/bin/pytest tests/tools/test_position_clock_structure.py -q
```

The duration receipt distinguishes a capture-start span from the sum of the
48 nominal 300-second captures; gaps are not counted as recorded RF support.

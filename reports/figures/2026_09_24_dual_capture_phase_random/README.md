# September 24 dual-capture random phase replay

This directory contains the frozen cohort, replay program, canonical compressed
evidence, tabular summary, and figures for the accompanying report. The replay
reads saved IQ and sealed production analysis products without modifying them.
It performs no RF collection.

From the repository root, with access to `/srv/bulk/leo`, run:

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python reports/figures/2026_09_24_dual_capture_phase_random/replay.py
MPLCONFIGDIR=/tmp/leo-mpl MPLBACKEND=Agg \
  python reports/figures/2026_09_24_dual_capture_phase_random/summarize.py
```

`cohort.json` freezes session IDs and capture-manifest digests at the stated
cutoff. `inventory-summary.json` records the independently audited completed
visit and valid-duty counts. `comparison.json.gz` binds each selected dwell to
its IQ digest, deterministic random split, phase-blind priority, training-only
carrier probes, numerical source hashes, held result, and any abstention.
`per-dwell.csv` and `summary.json` are derived views of that evidence.

The `rows/` directory used by the replay is a resumable local checkpoint cache.
It is intentionally excluded from the published evidence because all retained
rows are already present in `comparison.json.gz`.

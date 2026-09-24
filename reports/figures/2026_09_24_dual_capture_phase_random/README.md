# September 24 dual-capture random phase replay

This directory contains the frozen cohort, replay program, canonical compressed
evidence, tabular summary, and figures for the accompanying report. The replay
reads saved IQ and analysis products without modifying them. It uses sealed,
complete production GLRT inventories for 41 captures. For two receipt-V6
captures and one late V4 capture whose frozen sealed inventory was partial, it
validates every retained event as exactly 120 ms and runs the same pure GLRT
numerics directly into report evidence. It neither downcasts nor persists an
analysis product. The replay performs no RF collection.

From the repository root, with access to `/srv/bulk/leo`, run:

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python reports/figures/2026_09_24_dual_capture_phase_random/replay.py
MPLCONFIGDIR=/tmp/leo-mpl MPLBACKEND=Agg \
  python reports/figures/2026_09_24_dual_capture_phase_random/summarize.py
```

`cohort.json` freezes session IDs and capture-manifest digests at the stated
cutoff. `inventory-summary.json` records the independently audited completed
visit and valid-duty counts. The phase-blind screen covers every complete visit
before fixing the strongest eight per capture. `comparison.json.gz` binds each
selected dwell to its IQ digest, deterministic random split, phase-blind
priority, analysis-inventory source, training-only carrier probes, numerical
source hashes, held result, and any abstention. `per-dwell.csv` and
`summary.json` are derived views of that evidence.

`report-local-screen-summary.json` records complete-visit coverage, phase-blind
candidate counts, numerical error counts, configuration, and a canonical
digest of each report-local full screening cache.

The `rows/` directory used by the replay is a resumable local checkpoint cache,
including the three full report-local phase-blind screens. It is intentionally
excluded from the published evidence because the selected rows and frozen
selection rule are already present in `comparison.json.gz`.

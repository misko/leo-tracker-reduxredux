# DS1 historical timing ablations

`run.py` evaluates only timing controls. It imports DS1's cache/membership
loader but no orbit-model code. At each inherited terminal geographic point it
freezes each track's visible-candidate identity from its original randomized
TRAIN rows at tau zero. Constant CFO remains TRAIN-profiled.

The shared control gives every frozen track one global tau. The regularized
control gives each scan a tau on the same 0.25-second cache grid, shrunk to a
global tau with the historic 0.2, 1, and 5 second scales. The scale is chosen
from the two complete outer TRAIN blocks only, sealed, then reused unchanged.
`fractional_diagnostic.py` refines only a *common* global tau to 0.05 seconds.
The separate `fractional_per_track_diagnostic.py` reproduces the historical
independent per-track timing freedom at 0.25-second nodes plus continuous
within-interval profiling. It is evaluated on four non-TEST 16-scan groups at
the inherited DS1 terminal point union and remains diagnostic because its
independent +/-5-second shifts exceed the measured timing authority.

All losses preserve the DS1 occupied-second weights and 800-Hz cap. Candidate,
CFO, timing, point, and scale fitting use no held rows or reference coordinate.
`results.json` records the required full TEST64 input failure rather than
silently omitting its missing continuity authority.

The published timing comparison is assembled from sealed historical fits:

```bash
.venv/bin/python reports/2026_09_24_ds1_timing_ablations/integrate.py
.venv/bin/python reports/2026_09_24_ds1_timing_ablations/fractional_diagnostic.py
for case in train_20260921_00_16 train_20260921_16_16 \
  validation_20260922_08_16 validation_20260921_08_16; do
  .venv/bin/python \
    reports/2026_09_24_ds1_timing_ablations/fractional_per_track_diagnostic.py \
    --case "$case"
done
.venv/bin/python reports/2026_09_24_ds1_timing_ablations/finalize.py
```

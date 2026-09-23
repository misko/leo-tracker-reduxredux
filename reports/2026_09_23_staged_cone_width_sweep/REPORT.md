# Staged fixed-cone width sweep

The sealed 10/25/30-degree full-FOV sweep completed in 44.40 seconds over five
frozen cells and twelve TRAIN scans. All ten owned and independent tests passed.
The 25-degree arm exactly reproduced the published orientations, assignments,
support counts, changed-ID counts, training loss, and held loss.

| cell | full FOV | train / held all-track loss | tracks | occupied-second fraction | supported held RMS | changed IDs | max training angle |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10° | .992 / .992 | 14 / 774 | .008 | 505 Hz | 3 | 4.988° |
| 1 | 25° | .849 / .862 | 207 / 774 | .183 | 441 Hz | 72 | 12.497° |
| 1 | 30° | .755 / .773 | 302 / 774 | .303 | 449 Hz | 92 | 14.984° |
| 2 | 10° | .992 / .993 | 17 / 774 | .009 | 469 Hz | 6 | 4.984° |
| 2 | 25° | .863 / .875 | 192 / 774 | .172 | 484 Hz | 64 | 12.481° |
| 2 | 30° | .783 / .801 | 289 / 774 | .282 | 495 Hz | 96 | 14.992° |
| 3 | 10° | .990 / .990 | 17 / 774 | .010 | 190 Hz | 4 | 4.981° |
| 3 | 25° | .827 / .837 | 205 / 774 | .195 | 358 Hz | 54 | 12.486° |
| 3 | 30° | .706 / .720 | 317 / 774 | .335 | 411 Hz | 71 | 14.980° |
| 4 | 10° | .990 / .991 | 18 / 774 | .011 | 285 Hz | 4 | 4.969° |
| 4 | 25° | .870 / .880 | 181 / 774 | .155 | 535 Hz | 56 | 12.499° |
| 4 | 30° | .779 / .803 | 303 / 774 | .311 | 580 Hz | 98 | 14.946° |
| 5 | 10° | .990 / .990 | 19 / 774 | .011 | 251 Hz | 6 | 4.956° |
| 5 | 25° | .827 / .836 | 203 / 774 | .195 | 361 Hz | 52 | 12.485° |
| 5 | 30° | .707 / .720 | 317 / 774 | .334 | 410 Hz | 68 | 14.999° |

The 10-degree implementation works as specified: 10 degrees is full FOV, its
threshold is exactly 5 degrees, every persisted selected assignment has maximum
training-sample angle below 5 degrees, and independent boundary tests distinguish
4.9°, 5.0°, and 5.1°. With axes 20 degrees apart, the two 5-degree half-angle
caps are disjoint with a 10-degree gap.

Scientifically, the 10-degree hard cone is too restrictive for these data. It
supports only 14-19 of 774 tracks and 0.8%-1.1% of occupied-second support. Its
all-track capped held loss is .990-.993. Between 487 and 493 ordinary baseline
winners per cell already have sampled angular span above the full 10-degree FOV,
so no orientation can contain those winner tracks. Across retained RF-improving
candidate hypotheses, 699-824 per cell fail the same necessary span condition.
The remaining exclusions can arise from the common orientation, mount tilt
limit, grid, receiver assignment, or competition among tracks.

The 30-degree arm retains 28.2%-33.5% of occupied-second support and has lower
all-track loss than 25 and 10 degrees at all five cells. This ordering is an
observed result, not an assumed monotonic guarantee: every width independently
re-optimizes the orientation and refits candidates. Supported-only RMS can look
small at 10 degrees because it describes a tiny selected subset; the all-track
penalty is the appropriate comparison.

The spherical caps have zero overlap at 10-degree full FOV. At 25 and 30 degrees
their ideal geometric overlap is about 10.50% and 22.11% of one cap,
respectively. This is geometry only, not detection probability or antenna gain.
No truth, VAL/TEST, geographic tuning, new RF, QNAP write, or deployment was
used.

These are exhaustive optima on the prescribed finite orientation grid, with a
15-degree maximum mount tilt; they are not certified continuous-orientation
optima. Compatibility requires the entire track's sampled training directions
to fit, rather than crediting only the part of a trajectory crossing a cone.
No new geographic position was estimated by this fixed-cell comparison.

Reproduce with the existing authorized local TRAIN caches and metadata:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_23_staged_cone_width_sweep/run.py
.venv/bin/python reports/2026_09_23_staged_cone_width_sweep/plot.py
.venv/bin/python -m pytest reports/2026_09_23_staged_cone_width_sweep -q
```

`results.json` records per-track assignments and their maximum sampled training
angles; `results.sha256` seals it. The executed source and all source/cache
bindings remain unchanged after the run.

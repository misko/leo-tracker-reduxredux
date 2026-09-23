# Conditional shared-position comparison

This bounded experiment fits one stationary receiver location to the frozen 16-scan
evidence. It retains all 553 eligible tracks and 14,043 observations and copies the
production randomized training masks exactly. The baseline profiles integer timing
offsets from -5 through +5 seconds and preserves several separated spatial incumbents.

The identity universe is the per-scan union of every NORAD selected by either the
published Sacramento or Reno production search. Every track in that scan may be
reassigned to any identity in that union. This is a broader reassignment test than
freezing each track's old winner, but it remains conditional on prior-selected
shortlists and is not full-catalogue blind recovery. The saved evaluation rows already
participated in the production position/identity selection, so the score is a selection
score rather than untouched predictive validation.

The numerical cache contains receiver-independent ECEF position and velocity states at
0.25-second spacing, propagated from each scan's exact causal TLE snapshot and exact
qualified first-sample epoch. `cache_manifest.json` records its scope and accounting.
The coordinator's independent replay of 1,106 production fixed-winner cases found a
median absolute RMS difference of 0.000715 Hz and maximum of 0.004641 Hz.

`results.json` reports the 1/2/4/8/16 chronological accumulation sensitivity. These
prefixes are not chronological train/test splits: every fit uses the same fixed
randomized masks. The geographic search is constrained to the intersection of the
Sacramento 250 km and Reno 500 km supports so every estimate has common prior support.
Nelder-Mead is capped at 35 evaluations per retained basin and the coarse incumbent is
always re-evaluated and preserved; optimizer non-convergence therefore means the
bounded refinement exhausted its budget, not that the incumbent is invalid.

Replay the comparison from a disposable checkout with the committed cache (no
production API or source-store access required):

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/sixteen_joint_compare.py \
  --selection reports/2026_09_23_sixteen_scan_position_resolution/selection.json \
  --scans reports/2026_09_23_sixteen_scan_position_resolution/scans.json \
  --output reports/2026_09_23_sixteen_scan_comparison/joint \
  --budget-seconds 600
```

To rebuild the cache instead, add `--build-cache`; that step requires the original
source stores and local API. It uses the repository's read-only `ScannerTrackingInputStore` and
`TleArchiveReader` under the local `leo` service account. It performs no RF collection
and does not modify either source store.

# 10 MS/s versus 2.5 MS/s Starlink tracking comparison

These figures support the comparison in the
[RX0 10 MS/s per-recording TLE review](../../2026_09_15_rx0_10msps_recording_tle_review.md).

- `10msps-vs-2p5msps-tle-comparison.png` compares catalogue-leader RMS,
  winner-to-runner separation, and within-protocol exploratory outcomes.
- `10msps-session-association-summary.png` shows track counts, descriptive
  passes, heldout RMS, and rank stability for all 47 ten-minute recording slots.
- `summary.json` preserves the exact source-derived statistics and all 47
  session rows.

The inputs are the 47-recording 10 MS/s evidence directory and the September 7
2.5 MS/s scan's `tle-match-all-candidates.json`. The cohorts use different
receivers, track consolidation, time-shift grids, and acceptance gates. The
figures are descriptive comparisons and do not estimate a causal sample-rate
effect or satellite-identification probability.

Reproduce from the repository root:

```bash
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  tools/plot_scanner_tle_rate_comparison.py \
  --ten-msps reports/figures/2026_09_15_rx0_10msps_recording_tle_review \
  --two-point-five-msps reports/figures/2026_09_07_scan_09970e_trajectory_tle_review/tle-match-all-candidates.json \
  --output /tmp/10msps-vs-2p5msps-starlink-tracking
```

# Exact coarse-peak heap selection

The server profile attributed 532,322 calls to the acquisition peak-sort key.
The candidate replaces the full ordering of every local coarse-grid peak with
a heap and removes only enough peaks to retain the configured eight separated
basins. It preserves the original order key exactly: score descending, absolute
CFO ascending, epoch ascending, and stable discovery order for complete ties.
No score, grid, separation rule, retained count, or downstream evidence changes.

The original and candidate acquisition sources are frozen in `original/` and
`candidate/`; `SOURCE_LOCK.json` records their hashes. The candidate is also
applied to `src/leo/analysis/starlink/acquisition.py`, with a component-owned
randomized exact-equivalence gate in `tests/dsp/test_starlink_acquisition.py`.

Validation:

- focused randomized, tie, boundary, and all-zero equivalence: 66 passed;
- acquisition component suite plus focused experiment: 93 passed;
- Ruff: passed;
- synthetic 11-row by 3,333-epoch selection: 4.07 ms baseline versus 2.07 ms
  candidate, 1.96x for this selection step.

The expected whole-visit gain is modest because native coarse correlation,
fine FFT scoring, conditioned scoring, and final normalized scores are
unchanged. The combined four-rate archived-input screen kept every detector
output exactly equal and measured 1.110x, 1.102x, 0.986x, and 1.012x speedups
at 2.5, 5, 7.5, and 10 MS/s respectively. These single-case high-rate results
do not establish a gain. The stronger alternating five-case 2.5-MS/s full
analyzer comparison, which also includes the independently audited immutable
pilot-reference cache, measured a 4.31% CPU reduction (1.045x) with all output
products exactly equal. See `../paired-summary.json` and `../REPORT.md`.

The published Standard entry point is
`src/leo/cli/scanner.py:run_published_standard_scanner_analysis`, which builds a
verified CI16 source and calls `src/leo/scanner/standard_analysis.py`.
`tools/run_adaptive_capture_cycle.py` is a different workload: it uses the
external `pluto_plus.Ci16EnergyDetector` and `AdaptiveScanArchive`, and does not
call the Standard scanner analyzer.

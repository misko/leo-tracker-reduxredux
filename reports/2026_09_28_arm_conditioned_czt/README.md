# Conditioned frequency search using chirp-Z convolution

See `PERFORMANCE_REPORT.md` for final ARM timings and exact DS7 recovery counts.

Report-local experiment against the qualified scoped no-prefetch build from
`../2026_09_28_arm_coarse_tiles/`. No production pipeline code is changed.

The conditioned search evaluates all of its original regularly spaced 100 Hz
frequency bins using single-precision FFT convolution. It retains the previous
FP64 normalization, near-maximum FP64 rechecks, winning-frequency refinement,
and final GLRT. No windows, candidates, bins, or frames are intentionally dropped.

`conditioned_czt.c` caches chirps, kernel FFT, plans, and work arrays for the
current template length and rate. It uses a shifted kernel and reads convolution
indices `n-1+j`, with inverse FFT normalization by `L`. The independent Python
check uses the equivalent wrapped kernel and reads indices `j`.

The existing `128*FLT_EPSILON` screen guard is empirically qualified, not a
proved bound on FFT rounding error. Quality claims apply to the tested corpus.
The cache is process-global and intended for serial execution in this research
benchmark; it is not a thread-safe production interface.

Qualified-build candidates:

- ARM: `/var/tmp/leo-arm-conditioned-czt-v3`, CPU0 on `192.168.1.15`.
- Host: `/var/tmp/leo-host-conditioned-czt-v2`, used for larger recovery tests.
- Source archives and hashed build receipts: `builds/`.

Tests use saved IQ only. Hardware timings cover the GLRT kernel with samples
in RAM, without concurrent radio capture; file transfer and workspace creation
are not included. First-use CZT planning occurs inside the timed search.

The original oracle comparison in `arm_run.py` reports expected inherited FP32
coarse differences and exits nonzero after completing the run. Do not treat that
raw receipt as a pass. `probe-comparison.json` compares this experiment directly
with the qualified preceding ARM implementation, including complete candidate
objects and byte-for-byte coarse grids.

The 704-dwell cohort samples eight dwells from each of 88 DS7 recordings. This
is 0.361% of DS7's 194,934 dwells, not the full dataset. Each dual-RX dwell runs
22 overlapping 20 ms windows: 11 per receiver at 10 ms stride. Each window retains
eight candidates. A positive candidate has final GLRT margin at least 0.025.
Positive-window recovery and individual positive-candidate recovery are separate
metrics.

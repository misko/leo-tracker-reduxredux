# RMS for the three plotted long trajectories

All entries are Hz normalized to 11.2 GHz. Every setting uses the same 447 probes.

| Candidate | Grid | Probes | Shared display cubic RMS | Own cubic full RMS | Own cubic held-out RMS |
|---|---:|---:|---:|---:|---:|
| STARLINK-32536 | 512 | 118 | 113.2 | 113.2 | 135.4 |
| STARLINK-32536 | 8192 | 118 | 120.8 | 117.3 | 138.1 |
| STARLINK-36469 | 512 | 207 | 108.5 | 108.5 | 113.6 |
| STARLINK-36469 | 8192 | 207 | 87.5 | 81.5 | 89.6 |
| STARLINK-30251 | 512 | 122 | 43.2 | 43.2 | 47.3 |
| STARLINK-30251 | 8192 | 122 | 68.8 | 54.7 | 60.6 |
| ALL (pooled) | 512 | 447 | 96.7 | 96.7 | 106.9 |
| ALL (pooled) | 8192 | 447 | 93.2 | 86.7 | 98.8 |

The shared-display column reproduces the residuals in the PNGs using the fixed 512-point cubic for both settings. The own-cubic columns refit a cubic for each setting; the held-out metric excludes whole three-second blocks, grouping each visit and both receivers together. All fits have shared time coefficients and a constant per source tracklet.

The pooled rows weight mean squared residuals by probe count. They are not medians across trajectories. No probes were removed.

These are model-consistency metrics, not absolute Doppler errors. The shared reference is baseline-conditioned, while the own-cubic metric can absorb smooth bias. Track selection and acquisition seeds remain conditional on the original configuration.

The earlier reduction from 181.6 to 6.8 Hz measured recovery of imposed
frequency increments with acquisition fixed, on 72 probes from 12 tracks.
It primarily exposes frequency-grid quantization and is not a 27-fold
improvement in real-track precision. See
[why the two experiments give different improvements](../2026_09_10_scan_glrt_search/README.md#why-1816-to-68-hz-does-not-mean-27-times-better-track-precision)
for the error definition, bin example, shared-error cancellation, and cohort
differences.

See trajectory-rms.csv for the trajectory table, lane-rms.csv for individual lane values, and rms-table.json for definitions and source provenance.

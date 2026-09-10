# GLRT hyperparameters on the last 24 hours of 300-second scans

This study covers 67 completed nominal 300-second scans from 2026-09-09
00:40:00 through 2026-09-10 00:40:00 UTC, with the end excluded. Offline replay
examines window duration, stride, timing and frequency search resolution,
acquisition controls, and long Starlink candidate trajectories.

**The deployed settings are not established as optimal.** The cubic-fit
comparisons measure conditional consistency, with original acquisition seeds
and preselected tracks. They do not provide independent frequency truth.
Changing the stride evaluation reference changes the ranking.

Increasing the residual GLRT frequency grid from 512 to 8192 points reduces
known-increment error from 181.6 to 6.8 Hz when acquisition and timing are held
fixed. That is improved response to a controlled frequency change, not a
demonstrated 27-fold improvement in real Doppler precision. Shared errors can
cancel between the original and shifted copies, and the chosen shifts favor
the finer grid. The
[detailed explanation and 137 Hz bin example](2026_09_10_scan_glrt_search/README.md#why-1816-to-68-hz-does-not-mean-27-times-better-track-precision)
distinguish this test from the real-track results below.

## Three highlighted long trajectories

These are candidate satellite associations. Every row uses the same individual
20 ms probes for both configurations, with separate fractional timing
refinement and no trajectory feedback into the GLRT estimator. RMS values are
Hz normalized to an 11.2 GHz RF reference.

| Candidate | Span | Probes | Shared display cubic: 512 | Shared display cubic: 8192 | Held-out own cubic: 512 | Held-out own cubic: 8192 |
|---|---:|---:|---:|---:|---:|---:|
| STARLINK-32536 | 64.0 s | 118 | 113.2 | 120.8 | 135.4 | 138.1 |
| STARLINK-36469 | 56.4 s | 207 | 108.5 | 87.5 | 113.6 | 89.6 |
| STARLINK-30251 | 49.2 s | 122 | 43.2 | 68.8 | 47.3 | 60.6 |
| All, pooled | — | 447 | 96.7 | 93.2 | 106.9 | 98.8 |

The shared display cubic is fitted to the baseline and subtracted from both
settings. Held-out errors fit each setting separately while excluding whole
three-second time blocks. The pooled held-out RMS is 7.6% lower at 8192, with
one trajectory improving and two worsening. None of these metrics is an
absolute Doppler-error measurement.

## Reports, figures, and evidence

- [Original 24-hour cohort, window/grid sweeps, and orbital candidates](2026_09_10_scan_24h_glrt_rms/README.md).
- [Reference audit and qualification of the original parameter recommendations](2026_09_10_glrt_reference_audit/README.md).
- [Stride, probe position, and wider timing search](2026_09_10_scan_glrt_stride/README.md).
- [Frequency/timing search resolution, acquisition sweeps, and controlled shifts](2026_09_10_scan_glrt_search/README.md).
- [Individual-probe PNGs for all three highlighted trajectories](2026_09_10_long_glrt_probe_png/README.md).
- [RMS definitions and CSV tables, including individual receiver/edge lanes](2026_09_10_long_glrt_rms_table/README.md).

Each report preserves its per-probe or per-track numerical outputs and source
bindings. Analysis receipts and checksum manifests accompany the original
cohort and replay studies. The original cohort's sealed evidence is unchanged;
later reports qualify its interpretation. The repository's `tools/` scripts
and component-owned numerical tests provide the associated replay and
evaluation code. No new RF recording or production configuration change was
made for this study.

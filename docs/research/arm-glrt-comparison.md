# ARM methods compared with the standard GLRT pipeline

See [new prototype results and architectural priorities](../../reports/2026_09_29_arm_realtime_review/PROTOTYPES.md)
for exact FFT reuse, FP32 proposals and causal same-channel frequency prediction.

Use the standard analysis pipeline's individual positive GLRT candidate
entries as the recovery denominator. Count one-to-one matches in the same
receiver/window. Do not substitute native-baseline parity, positive-window
coverage, raw positive totals, timing-proposal coverage or supplied-coordinate
scorer equivalence for recovered detections.

The common DS7 benchmark contains 704 dwells from all 88 recordings, not all
DS7 data. Standard analysis executes 15,488 receiver-specific 20 ms windows
and returns 19,581 positive candidate entries. Its 2.5 MS/s subset contains
152 dwells, 3,344 windows and 4,573 positive candidate entries.

| ARM approach | Original 2.5 MS/s hits recovered | Original mixed-rate hits recovered | Mixed-rate recovery | ARM CPU time per 120 ms dual-RX dwell at 2.5 MS/s |
|---|---:|---:|---:|---:|
| Reduced rank-six/confirm-one detector | 126/4,573 | 499/19,581 | 2.55% | 69.24 ms |
| Exact refinement reuse V2 | 4,573/4,573 | 19,581/19,581 | 100% | 33.167 s |
| Selective boundary fallback | 4,573/4,573 | 19,576/19,581 | 99.9745% | 25.085 s |
| Lag-structure proposals plus restricted timing search | 4,551/4,573 | 19,400/19,581 | 99.08% | 7.377 s, separately timed stage sum |
| Restricted timing search plus exact lazy FFT reuse | 4,551/4,573 | 19,400/19,581 | 99.08% | 6.449 s, separately timed stage sum |
| FP32 lag proposals plus restricted timing search and lazy FFT reuse | 4,551/4,573 | 19,400/19,581 | 99.08% | 6.313 s, separately timed stage sum |
| Sparse coarse search, eight frames | 4,347/4,573 | 18,404/19,581 | 93.99% | 27.808 s |
| Tracking with full refresh every second window | 3,898/4,573 | 17,076/19,581 | 87.20% | 33.997 s |
| Fine-frequency result directly into GLRT | 3,894/4,573 | 16,333/19,581 | 83.41% | 24.455 s |
| Sparse coarse search, four frames | 3,715/4,573 | 15,545/19,581 | 79.39% | 22.918 s |

Large-cohort quality runs for the fuller searches use host executions of the
ARM-targeted algorithms, with separate physical-ARM qualification and timing
subsets. The reduced detector's complete 704-dwell quality run was on ARM.
The 69.24 ms runtime includes concurrent saved-IQ RAM replay; other timings
exclude concurrent capture. Tracking timing uses two dwells; the other full
search timings use four. Do not treat this as one paired timing experiment.

The reduced-detector historical matching gate is two microseconds and 8 kHz;
the subsequent fuller-search audits use two samples and 8 kHz. Both use
one-to-one matching within the same receiver/window. The reduced detector
therefore has a looser timing tolerance, not an unfairly stricter criterion.

The restricted timing search also returns 18,328 unmatched positive entries
on DS7. Its high recall does not imply an equivalent output inventory or
verified false-alarm behavior. Boundary fallback returns two unmatched
positive entries and remains the preferred near-baseline quality reference.

Lazy FFT reuse preserves all 123,904 candidate objects on the DS7 subset.
FP32 proposals change 200 candidate objects in 57 windows but retain the same
per-rate recovered-hit counts and the same overall unmatched-positive count.
Their ARM proposal timing uses three repeats of four dwells; lazy search uses
two repeats of the same four dwells. No combined capture measurement is implied.

Final-scorer optimization is not a separate discovery method: 274.0 ms scores
all 176 supplied-coordinate entries; 46.7 ms is the retrospective positive-only
sum. Its 19,581/19,581 matching positive decisions are numerical equivalence
at original coordinates, not discovered-hit recovery.

## Smaller PSD cohort, separate denominators

These prototype results use 96 mixed-rate dwells across DS7/DS8/DS9, with
2,536 standard positive hits (595 at 2.5 MS/s). They cannot populate the
19,581-hit DS7 denominator above.

| ARM approach | Original 2.5 MS/s hits recovered | Original mixed-rate hits recovered | ARM CPU s per dwell at 2.5 MS/s |
|---|---:|---:|---:|
| Three PSD-ranked frequency lanes | 192/595 | 642/2,536 | 14.708 |
| Five PSD-ranked frequency lanes | 304/595 | 1,106/2,536 | 21.623 |
| Nine log-PSD-ranked frequency lanes | 497/595 | 2,227/2,536 | 28.514 |
| Confidence gate, five or eleven lanes | 485/595 | 2,346/2,536 | 23.856 |

PSD timings include PSD calculation and GLRT, on a separate four-dwell ARM
subset containing 90 original hits; they are not full-cohort timings.

## Authoritative reports

- [Reduced detector recovery](../../reports/2026_09_28_ds7_large_arm/REPORT.md)
  and [RAM replay timing](../../reports/2026_09_28_arm_ram_pipeline/REPORT.md).
- [Exact refinement reuse](../../reports/2026_09_28_arm_refinement_cache/REPORT.md).
- [Boundary fallback](../../reports/2026_09_28_arm_boundary_fallback/REPORT.md).
- [Lag-structure discovery](../../reports/2026_09_29_arm_lag_discovery/REPORT.md).
- [Exact lazy FFT reuse](../../reports/2026_09_29_arm_fine_reuse/REPORT.md).
- [FP32 proposals and downstream GLRT](../../reports/2026_09_29_arm_float_proposal/REPORT.md).
- [Sparse coarse search](../../reports/2026_09_28_arm_sparse_proposal/REPORT.md).
- [Tracking](../../reports/2026_09_28_arm_glrt_tracking/REPORT.md).
- [Fine-direct GLRT](../../reports/2026_09_28_arm_direct_glrt/REPORT.md).
- [Final scorer](../../reports/2026_09_29_arm_scoring_kernel/REPORT.md).
- [PSD proposals](../../reports/2026_09_29_arm_psd_proposal/REPORT.md).

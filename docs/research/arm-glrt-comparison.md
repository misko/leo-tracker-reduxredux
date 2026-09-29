# ARM methods compared with the standard GLRT pipeline

Current selection: **raw FP32 fine FFTs without fine-FFT FP64 fallback**.
The [ARM progress index](arm-glrt-performance.md) records the selected research
baseline, milestones, remaining limitations and links to reproducible evidence.

The [sixth-wave comparison](../../reports/2026_09_29_arm_subsecond/WAVE6.md)
separates compiler, SIMD, shared folding, input reuse, and approximate smaller
FFT experiments. Its exact combination measures **0.815 seconds mean** on
152 ARM dwells, conserving **4,506/4,573** standard hits and every prior ARM
candidate across all 3,344 windows; mixed-rate host recovery remains
**19,217/19,581**. It saves 10.98% versus Wave5 on the same larger ARM panel.
The exact combination plus ARM-trained PGO reaches **0.776 seconds** on a
disjoint 32-dwell panel versus 0.918 seconds for Wave5, with the same
**904/921** standard hits. Its target qualification is currently that smaller
panel; the report keeps the two timing cohorts separate.

The [fifth-wave final combination](../../reports/2026_09_29_arm_subsecond/WAVE5.md)
measures **0.915 seconds/dwell mean** on 152 physical-ARM dwells at 2.5 MS/s,
recovering **4,506/4,573** hits across all 3,344 windows. P95 is **1.219
seconds**; 105/152 dwells finish below one second. The larger host audit has
**19,217/19,581** standard hits recovered on 704 mixed-rate DS7 dwells. It runs
all 15,488 windows and emits 86,439 candidates. Rate-based coarse rejection
provides the largest saving; exact input preparation and sparse peak extraction
add no further lost detections. Quadratic search retains the gated method's
hit identities across DS7, DS8 and DS9. This is research-only static-input
processing, not 120 ms real-time operation or concurrent-capture validation.

The [fourth-wave follow-up](../../reports/2026_09_29_arm_subsecond/WAVE4.md)
measures **1.686 seconds/dwell**, retaining **19,226/19,581** standard hits and
every Wave3 candidate object. It precomputes proposal geometry and rank values
and selects the same four peaks with less work. Capture remains excluded.

The [third-wave combined method](../../reports/2026_09_29_arm_subsecond/WAVE3.md)
measures **1.710 seconds/dwell** (two-run mean) and recovers
**19,226/19,581** hits, with 21,505 unmatched positives. It retains every window
and candidate entry. Two-lag proposals reach 1.652 seconds in one run but
recover fewer hits (19,189). These remain static-IQ research measurements.

The [second-wave follow-up](../../reports/2026_09_29_arm_subsecond/WAVE2.md)
measures the fused omit-power plus NEON-moment method at 1.866 seconds/dwell, retaining
19,225/19,581 original hits with 21,418 unmatched positives. Its outer timer
includes proposals, region construction, conversion and search. This remains
above the subsecond goal and excludes capture and initial setup.

The [subsecond-goal checkpoint](../../reports/2026_09_29_arm_subsecond/REPORT.md)
adds a 2.010-second tradeoff retaining 19,249/19,581 original hits. It keeps all
windows and candidate entries but increases unmatched positives to 21,555.
The subsecond goal is not achieved; timings remain separately measured stage sums.

The latest [compiler and packing experiment](../../reports/2026_09_29_arm_low_precision/REPORT.md)
reduces raw-FP32 search CPU by 8.1%, with unchanged standard-hit recovery.
Q15 integer FFTs and packed spectrum caches were slower, including NEON packing.
Compiler relaxation is qualified for the tested finite-data workload only.

The latest [FP32 fine-FFT and batching experiment](../../reports/2026_09_29_arm_fine_precision/REPORT.md)
reduces restricted-search CPU by 11.0% without changing candidate positive
decisions on the 704-dwell DS7 subset. The tested FP64 batches are slower.

See [per-stage ARM runtime](../../reports/2026_09_29_arm_endpoint_interpolation/RUNTIME_PROFILE.md)
and [first/last-window interpolation results](../../reports/2026_09_29_arm_endpoint_interpolation/REPORT.md)
for the latest smaller-cohort experiment. Endpoint interpolation recovered
56.23–77.46% of 843 standard hits and did not meet the recovery target.

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
| Above, with raw FP32 fine FFTs | 4,551/4,573 | 19,400/19,581 | 99.08% | 5.711 s, separately timed stage sum |
| Raw FP32 plus corrected compiler/local-arithmetic tuning | 4,551/4,573 | 19,400/19,581 | 99.08% | 5.319 s, separately timed stage sum |
| Full-frame moment conditioned screen with FP64 near-max rechecks | 4,551/4,573 | 19,400/19,581 | 99.08% | 4.567 s, separately timed stage sum |
| Two-frame fine estimate, moment screen, radius 2, exact final reuse | 4,521/4,573 | 19,249/19,581 | 98.30% | 2.010 s, separately timed stage sum |
| Fused omit-power proposals and NEON moments | 4,516/4,573 | 19,225/19,581 | 98.18% | 1.866 s, outer timer |
| Resampled proposals, squared ranking, boundary margin gate | 4,515/4,573 | 19,226/19,581 | 98.19% | 1.710 s, outer timer |
| Above, exact proposal geometry/rank preplanning and top-four selection | 4,515/4,573 | 19,226/19,581 | 98.19% | 1.686 s, outer timer |
| Resampled lag1 + lag5 proposals, original boundary rule | 4,513/4,573 | 19,189/19,581 | 98.00% | 1.652 s, outer timer, single run |
| Above, with guarded FP32 fine FFTs | 4,551/4,573 | 19,400/19,581 | 99.08% | 5.802 s, separately timed stage sum |
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

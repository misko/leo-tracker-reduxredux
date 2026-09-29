# Next steps toward one-core real-time GLRT: tested results and design priorities

The comparison report was published to main in commit `36ec93edc`. This
follow-up tests two CPU optimizations and a same-channel frequency-prediction
design. Every detection-recovery count below is relative to the standard
analysis GLRT pipeline, not a reduced detector's baseline.

## New measured results

Common scientific cohort: 704 DS7 dwells across 88 recordings, 15,488
receiver-specific 20 ms windows, and 19,581 original positive candidate
entries. The 2.5 MS/s subset has 4,573 original hits. This is not all DS7.

| Method | Standard mixed-rate hits recovered | Standard 2.5 MS/s hits recovered | ARM CPU ms per 120 ms dual-RX dwell |
|---|---:|---:|---:|
| Previous lag-proposal restricted search | 19,400/19,581 | 4,551/4,573 | 7,376.891 |
| Same proposals plus exact lazy FFT reuse | 19,400/19,581 | 4,551/4,573 | 6,449.296 |
| FP32 proposals plus lazy FFT reuse | 19,400/19,581 | 4,551/4,573 | **6,312.502** |

CPU values add separately timed proposal and search stages on physical
PLUTO+ CPU0 at 2.5 MS/s, with saved input in RAM. They exclude real capture,
the adaptive frontend and setup. The latest search timing uses two repeats
of four dwells; proposal timing uses three repeats of those four. Large-cohort
quality is host execution of the ARM-targeted algorithm, with physical ARM
qualification on the timing cohort (119/119 standard hits recovered).

The latest result is **1.169x faster** than the previous restricted search,
and about **3.97x faster** than the 25.085-second near-baseline-quality
boundary-fallback method. It is still **52.6x a 120 ms real-time budget**, or
**87.7x the 72 ms budget** for 40% analysis-core headroom. Real time has not
been achieved, and no production detector was changed.

The cache alone preserves all 123,904 candidate objects. FP32 proposals change
200 candidate objects in 57 windows but leave the per-rate recovery counts
unchanged. Both inherit 18,328 unmatched positive entries overall and 181
missing original hits from the restricted-search design. That output quality
issue remains open; high recall is not identical scientific evidence.

The first cache design calculated all frequency-bin magnitudes and was slower:
6,536.563 ms search versus 6,388.459 ms. The selected cache stores complex
spectra and computes only requested magnitudes, reducing search to 5,460.863
ms. Maximum cache storage is 9.77 MiB at 2.5 MS/s and 39.06 MiB at 10 MS/s.

Details: [FFT reuse](../2026_09_29_arm_fine_reuse/REPORT.md) and
[FP32 proposals](../2026_09_29_arm_float_proposal/REPORT.md).

## Can a hit narrow the next same-channel dwell?

Yes, as a prior. Track each signal independently by channel, edge, receiver
and configuration, keep its measured frequency and time, and predict
`f_next = f_last + estimated_drift * elapsed_time`. Search a neighborhood that
grows with elapsed time, fit uncertainty and recent prediction errors. One
past hit supports a constant-frequency guess; at least two associated past
hits are needed to estimate drift. A new hit must not be silently associated
with a different signal or frequency alias.

The new retrospective short-gap DS7 test supplies prior standard positives
as oracle seeds. Same-channel gaps are 0.120--1.322 seconds:

| Prediction design | Eligible standard frequencies within +/-8 kHz | Proposal-bank size | Scientific authority |
|---|---:|---|---|
| Reuse previous positive-frequency bank | 662/685 (96.64%) | Median 16 unique; maximum 43 | Frequency coverage only |
| Bounded causal drift, nearest older association within fixed 20 kHz | 378/399 (94.74%) | Median 11; maximum 43 | Frequency coverage only |
| All-pairs drift extrapolation, rejected as an economical predictor | 384/399 (96.24%) | Median 154 unique; maximum 1,677 | Frequency coverage only |

Different eligibility denominators reflect one versus two available history
dwells; they are not comparable recall rates for the whole stream. There are
1,154 standard hits overall and 469 cold-start hits. Previous-bank coverage is
only 662/1,154 (57.37%) before any cold-start discovery is added. None of these
coverage figures counts as recovered GLRT detections, checks timing, enforces
one-to-one hypothesis recovery, or measures ARM runtime.

An earlier implemented current-IQ prior-CFO-plus-fallback search recovered
904/1,154 standard hits (78.3%), including 562/761 at 2.5 MS/s. Its measured
speedup was 1.11x on a server, not ARM. Thus warm starts are useful but must
be paired with blind discovery, multiple-signal tracking, and uncertainty
handling. The 704-dwell stratified benchmark has 37--263 second gaps and is
unsuitable for judging normal next-dwell tracking.

Details, source hashes, cold starts and tests:
[cross-dwell prediction](../2026_09_29_arm_dwell_prediction/REPORT.md).

## Architectural priorities

These are design hypotheses and budgets, not promised speedups.

| Priority | Approach | Why it could matter | Main validation risk |
|---|---|---|---|
| 1 | Cheap pilot-structure discovery at two resolutions | Replace the current 852 ms proposal with a low-rate or incremental screen, refining only a few timing regions | Weak/multipath signals disappear under decimation or screening |
| 2 | Prior-guided frequency bank plus cheap blind discovery | Short-gap hits constrain likely CFO; avoid broad fine searches when a track is trustworthy | New signals, cold starts, alias branches and wrong associations |
| 3 | Resolve residual-frequency aliases with a small verification bank | Full fine FFT still costs 2.84 seconds after exact sharing; a different estimator is needed | Earlier coarse/fine-direct methods lost roughly 17--19% of original hits, largely through frequency branches |
| 4 | Shared final-GLRT statistics and selective candidate evaluation | Optimized all-176 scoring is still 274 ms; about 30 original positive entries/dwell already cost 46.7 ms retrospectively | Rejecting weak positives or conflating repeated original entries |
| 5 | Incremental overlapping-window statistics | Reuse the 50% shared samples while still returning each window's evidence | Normalization, support edges and frame alignment differ between windows |

An illustrative target allocation is discovery 10 ms, frequency refinement
15 ms, scoring 35 ms, and dispatch/fallback 12 ms. Achieving it requires
algorithmic changes, not multiplication of the small isolated speedups above.
The existing direct-CI16 final scorer should be integrated and measured in
the resulting pipeline, but its oracle-coordinate benchmark is not a detector.

Next scientific gate: freeze a causal multi-signal tracking policy and a
cheap blind screen, run consecutive saved IQ with cold starts and stale
tracks included, then count standard one-to-one hits and unmatched positives.
Only after acceptable recovery should CPU0 analysis run with concurrent RAM
production. Real DMA/IIO capture remains a separate qualification step.

## Publication and verification

The accompanying publication includes report-local prototype sources, build
receipts, numerical summaries and standard-hit audits. It excludes IQ files,
compiled binaries and large raw candidate inventories; their hashes are kept
in the receipts, and the full artifacts remain in the development workspace.
No radio collection, source-recording changes or production deployment occurred.

Validation completed: all-rate host/ARM cache component tests; host
ASAN/UBSAN with leak detection; exact 123,904-candidate cache differential;
actual 704-dwell FP32-proposal GLRT rerun; frozen standard-hit audits; all-rate
zero/full-scale proposal controls; and four causal-prediction unit tests.

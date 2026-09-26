# Frame and filter methods (ledger 01–18)

## Final cohort update

The completed replay supersedes the interim census below: all 128 visits have dense acquisition products, yielding 124 acquired receiver arcs and 10,301 cached frames. On 86 evaluation receiver arcs, median per-arc modulo-π RMS is 8.47° for even/odd agreement, 26.74° for adjacent prediction, and 51.91° for forward-half prediction. These are different validation tasks, not absolute phase errors.

The actual full-span ordinary and modulo-π trackers complete on 122 arcs, with two no-results each; reset counts are 2,284 and 668 respectively. PNT V1 and V2 each produce zero inner phase locks across the 124 acquired arcs. See [full-span evidence](fullspan/fullspan-trackers.json) and the [final 30-method ledger](../REPORT.md). The bounded V3/V4 and batch experiments below retain their stated smaller scope. Final plots and frame-method-summary.json use all 128 visits; older checkpoint prose below is historical progress only.

This package consumes only the sealed 128-visit cache and corrected dense acquisition. It never selects an epoch, CFO branch, or receiver from a phase outcome. Within each receiver, the full-dwell frame lattice starts from the earliest corrected-GLRT qualifying 20 ms probe. All coordinates remain native 10 MS/s, upper edge, with corrected absolute tuner-baseband CFO.

## Current census

The report is resumable while dense acquisition finishes. The latest summary covers the exact counts in `frame-method-summary.json` out of 128 eligible visits. Visits without a qualifying corrected acquisition are retained as `not_acquired`; they are not numerical estimator failures. `frame-fold-index.json` in `/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/frame-folds/` binds each checkpoint to its dense-acquisition digest.

Each acquired receiver is extracted once over all remaining clean support in its 120 ms dwell. Every cached frame contains the actual full-Qin 300-symbol/eight-tone phase-slope result, rolled-symbol control, and the actual even-trained/odd-held `estimate_edge_pilot_frame_complex_split` result. The all-Qin lane applies the fractional acquisition epoch. The historical guarded even/odd estimator is integer-frame based and is explicitly retained as a timing-sensitivity lane.

On the latest checkpoint, 88 selected visits have dense products, 85 receiver arcs were acquired, and 6,950 frames were cached. The frame-local exact-minus-rolled-control margin is positive for 97.11% of frames. Even-trained/odd-held phase difference has 0.268 rad modulo-π RMS. Adjacent constant-increment prediction has 0.504 rad modulo-π RMS, while train-half to forward-half linear prediction has 0.913 rad. These are within-recording descriptive errors, not absolute transmitter phase or false-alarm calibration.

## Actual tracker ablations

The expensive kernel lane calls the repository implementations directly:

- `analyze_contiguous_pilot_phase_doppler_tracking` with `phase_symmetry_order=1` for ordinary 2π and `=2` for causal modulo π;
- `analyze_contiguous_pilot_pnt_kalman`, V2, and phase-safe V3;
- V4 seeded discrete acquisition with the unchanged V3 tracking core on the sealed smoke-eight cohort;
- `track_piecewise_locklets` and `robust_blockwise_cfo_rate` from `pilot_locklet_prototypes` on cached observations.

Historical 50, 75, 80, 100, and 120 ms durations use actual contiguous within-dwell samples. Twenty-millisecond probes are acquisition/extraction units only. A 20 ms window cannot satisfy a 20-frame or 75/80 ms historical gate and is never used to claim such a failure.

The actual V3 bounded lane currently contains 14 independent 75/120 ms spans: 10 completed numerical tracking and four returned no result after their own full-frame alignment. The actual V4 smoke lane attempted all 16 receiver cases: eight processed, seven were not acquired, and one earliest qualifying seed left less than 80 ms. V4 produced numerical completion for its retained modes but zero phase-qualified modes; its thresholds remain explicitly uncalibrated. No threshold was lowered.

The sealed smoke-eight replay also exercises four historical kernels directly. Method 04 tested prompt phase against the integral of its robust degree-one frequency fit: exact accepted 126/632 transitions and rolled control accepted 124/632, with respective innovation RMS 0.295 and 0.292 cycles. This bounded result shows no exact-pilot continuity advantage. Method 05 produced 44–75 carrier observations per acquired arc and ran the same five-state replay with phase feedback enabled and disabled on all nine acquired receiver arcs; enabling phase changed the final rate by a median 102.5 Hz/s, so numerical completion is not evidence of a held phase lock. Method 08 used the historical per-frame channel/delay separation followed by the noncausal doubled-phase polynomial branch fit; eight receiver arcs met the frozen training-support gate and eight did not. Its median in-fit modulo-π residual was 0.777 rad, and because this is an offline batch fit it is not reported as held causal evidence. Method 14 used the historical normalized likelihood curves and disjoint even/odd frequency-line fitter for 20, 50, and 100 ms. All nine 20 ms and nine 50 ms cases completed; eight 100 ms cases completed and one late acquisition had only 60 ms remaining, recorded as `insufficient_remaining_span`. Median even/odd frequency splits were 25, 0, and 0 Hz, while slope splits were 600, 500, and 400 Hz/s. Two 20 ms fits reached a search boundary; none of the eligible 50 or 100 ms fits did. These are bounded smoke results rather than full-cohort population estimates.

For row 11, the bounded actual span inventory applies the inner phase qualification before considering any production outer gate. The exact pass/fail counts are recorded in `method-summary.csv`. A failed required inner gate proves the corresponding outer pipeline cannot qualify; no synthetic outer score is assigned to such a span.

The research locklet kernel ran on every currently cached acquired receiver arc. Support is a binary admission flag (`margin > 0` and exact coherence at least 0.02), never the raw coherence value. The common summary accepted 4,578 and rejected 3,232 frame observations. Its default robust 75 ms block fitter formed no eligible blocks in this summary path; the separately preserved historical row-16 replay in `row16-root/results.json` reports its own causal scoring convention and is authoritative for that ledger row.

## Ledger boundaries

`method-summary.csv` accounts for rows 01–18. Row 01's cross-boundary transport belongs to package G; D publishes counter-referenced local CFO for it. Rows 02–04, 07–08, and 14 use the common full-frame cache. Rows 05–06, 09–13, and 17 use actual tracker checkpoints plus common-fold population accounting. Row 15 overlays the capture result: this scan has no classified invalid payload row, while every unobserved gap and retune remains a reset boundary. Row 16 uses the actual research locklet implementation. Row 18 is a bounded actual smoke ablation, not a full-population V4 claim.

No method joins independently acquired probe phases, bridges a retune, or fits an evaluation-window intercept. Carrier phase results state ordinary 2π or modulo π explicitly. The even/odd split is disjoint-symbol validation. A seed GLRT consumes its complete 20 ms probe, so tracker outputs before that probe completes are acquisition-conditioned offline values; forward scoring begins only after the seed is available. Correlated frames are summarized within receiver visits rather than treated as independent satellites.

## Reproduction

`extract_frame_folds.py` incrementally adds newly available dense visits and never rereads completed IQ. `summarize_frame_methods.py` produces the CSV/JSON summaries and overview PNG/SVG entirely from cached folds. `run_actual_05_14.py` and `run_actual_08.py` reproduce the bounded historical-kernel smoke results. `run_frame_methods.py` owns digest-bound actual tracker checkpoints; its early repeated-duration implementation was stopped after runtime measurement and is retained only for its bounded actual ablation. `run_v4_smoke.py` reproduces the sealed smoke-eight V4 run.

The naive repeated-IQ path measured 300.3 seconds for eight visits and projected to multiple hours, so it was not expanded. The shared extraction cache replaced that path and keeps the all-method population replay bounded. Peak measured RSS for the repeated tracker benchmark was 2.80 GB; the cached fold inventory is compact and report-local/bulk-only.

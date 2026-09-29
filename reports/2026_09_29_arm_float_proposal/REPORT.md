# FP32 proposal probe

This is a bounded proposal-stage experiment. It preserves the four feature definitions (lag 1, lag 3, lag 5, and power), percentile-rank combination, circular local-maximum rule, and five-sample minimum peak separation from the FP64 proposal probe. It does not run or replace the recovered GLRT.

The implementation uses FFTW's float-complex API throughout the FFT and score path. CI16 operands are explicitly converted to `float` before products, avoiding signed-integer multiplication overflow. Existing complex128 template files remain the CLI contract and are converted to float once at startup.

## ARM result

The CPU0 PLUTO+ run covered four saved 2.5 MS/s dwells, 88 unique windows, and three repeats. Mean proposal time was 851.639 ms per dwell versus 988.433 ms for the FP64 probe, a 13.84% reduction. All 264 repeated top-four outputs matched the existing Python proposal rows. This is proposal cost only, not end-to-end real-time performance or GLRT equivalence.

## All-rate host audit

The complete 704-dwell DS7 benchmark subset covered 15,488 windows at 2.5, 5, 7.5, and 10 MS/s; this is not the entire DS7 corpus. Strict top-four equality differed in 257 windows: 16, 20, 96, and 125 by ascending sample rate. Of these, 229 were a one-sample shift in one selected candidate with the other three unchanged.

At the established radius-2 timing criterion, FP64 proposals covered 19,391 of 19,581 original positive epochs and FP32 covered 19,390. The sole coverage loss was ordinal 219, window 7, receiver 0 at 10 MS/s: the first proposal moved from epoch 13044 to 13045 for a labeled epoch at 13042. Therefore exact all-rate rank parity is false and downstream GLRT results require an actual audit.

Zero and alternating full-scale CI16 inputs completed all 22 windows at every rate. The eight exact templates were SHA-256 checked against the saved oracle metadata; `template-bindings.json` records that post-run binding, and the validator performs the check before future runs.

## Completed downstream GLRT audit

The FP32 proposals were subsequently fed into the actual restricted search
with lazy FFT reuse, on all 704 DS7 benchmark dwells and 15,488 windows.
Against the standard analysis pipeline, recovery is **19,400/19,581 (99.08%)**:
4,551/4,573 at 2.5 MS/s, 5,420/5,466 at 5 MS/s, 5,137/5,186 at 7.5 MS/s,
and 4,292/4,356 at 10 MS/s. These are the same per-rate recovered-hit counts
as the FP64-proposal restricted search. They are actual final GLRT results,
not the radius-2 proposal coverage above; the actual timing regions use +/-4
samples and downstream refinement.

Scientific output equivalence is not exact: 200 candidate objects change in
57 windows. There are still 18,328 unmatched positive entries overall, with
one extra at 2.5 MS/s and one fewer at 5 MS/s. Boundary fallback calls increase
by two, to 18,992; 123,904 candidate entries require 142,896 GLRT calls. These
findings do not establish false-alarm equivalence or generalization beyond
this development subset.

The ARM timing dwells have unchanged proposal selections. Adding the measured
851.639 ms proposal cost to the separately measured lazy-search mean of
5,460.863 ms gives **6,312.502 ms per dwell**, versus 7,376.891 ms for the
previous FP64-proposal restricted search: 14.43% less CPU (1.169x faster).
This is a separately timed CPU-cost sum, not a fused pipeline or concurrent
capture measurement. The scorer-only direct-CI16 improvement is not integrated.

Evidence lives in the sibling `arm_fine_reuse` report directory:
`host704-float-lazy-v1` and `host704-float-standard-audit.json` (the full directory
name is `2026_09_29_arm_fine_reuse`).

## Build and feature artifacts

- Host executable: `builds/host-v1/proposal_probe`
- ARM executable: `builds/arm-v1/proposal_probe`
- Reproducible build receipts: `builds/host-v1/build.json` and `builds/arm-v1/build.json`
- ARM measurements: `arm4-v1/summary.json`
- Full compatible feature rows: `host704-v1/rows.jsonl`
- Full parity details: `host704-v1/summary.json`

The host and ARM source snapshots both hash to `b938e81e44dc14f8cf4b477e898b14695c36cf716e285b3299797b6af3c6f9da`. The host binary hashes to `dc4c9af396dd49631a23107d4e21930c4d0b664387b92f3670c37bbd07f52300`; the ARM binary hashes to `97d4c71bcf2825ebc626a4cd6ceb1ccd473c75447f8cb5289bd5b880a88d75db`.

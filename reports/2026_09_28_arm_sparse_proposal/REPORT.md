# Sparse coarse proposals: ARM speed versus individual-hit recovery

Using fewer frames for discovery, followed by full coarse rescoring around
128 proposed centers, provides a measured speed/recall tradeoff. The final
fine search, conditioned search, verification, and GLRT formulas remain
unchanged. This is an **approximate detector**, not exact equivalence: omitted
discovery peaks cannot be recovered by exact local rescoring.

All settings process all 22 overlapping 20 ms receiver windows in each 120 ms
dual-RX dwell. All completed real-data windows emitted eight fully scored
candidates. No dwell-confirmation metric is substituted for individual hits.

## ARM CPU0 timing at 2.5 MS/s

PLUTO+ 192.168.1.15 processes saved input from RAM. No RF collection or
simultaneous capture ran during these benchmarks. Transfers and workspace
creation are outside search CPU time. The baseline is verification-fusion V1,
which preserves all original positive hits on the larger cohort.

| Search | Four-window mean, three repeats | Speedup |
| --- | ---: | ---: |
| Full search | 1.532125 s/window | 1.000× |
| 8 frames, 12 symbols, 128 centers | 1.266909 s/window | 1.209× |
| 4 frames, 12 symbols, 128 centers | 1.044850 s/window | 1.466× |

The complete-dwell measurement for eight frames is **27.807735 CPU s/dwell**
versus **33.728123 s/dwell**, a **1.21290×** speedup. Its 88-window ARM sample
recovers **113/119 individual hits**, **44/49 positive windows**, and emits
7 unmatched positive hypotheses. This hardware sample is separate from the
larger host quality measurement below.

Four frames measures **22.918122 CPU s/dwell**, a **1.47168×** speedup, but
recovers only **87/119 hits (73.11%)** and **33/49 positive windows** on the
same ARM sample, with 18 unmatched positive hypotheses. Both methods process
all 88 windows and all 704 candidate GLRTs. Restricting the completed host
results to these exact four dwells reproduces 113/119 and 87/119 respectively
(`matched-host-subset.json`). This is case-dependent loss, not evidence of an
ARM-only numerical failure. The four-frame mode is therefore **not qualified
as a robust 80% setting**, despite clearing 80% on the larger 2.5 MS/s aggregate.

The inherited exact-oracle runner exits with a mismatch for these approximate
builds. The completed-run receipts, independently scored recovery, and saved
timings establish their measured behavior; no claim of exact parity is made.

## Larger DS7 recovery, host execution

704 dwells span all 88 DS7 recordings, eight selected dwells per recording:
15,488 windows and 123,904 completed candidate GLRTs per method. This covers
0.361% of the 194,934 published DS7 dwells, not full DS7.

| Rate (MS/s) | 20 ms windows run | Original individual hits | 8-frame hits recovered | 4-frame hits recovered |
| ---: | ---: | ---: | ---: | ---: |
| 2.5 | 3,344 | 4,573 | 4,347 (95.06%) | 3,715 (81.24%) |
| 5 | 4,752 | 5,466 | 5,183 (94.82%) | 4,415 (80.77%) |
| 7.5 | 4,048 | 5,186 | 4,841 (93.35%) | 4,081 (78.69%) |
| 10 | 3,344 | 4,356 | 4,033 (92.58%) | 3,334 (76.54%) |
| **Total** | **15,488** | **19,581** | **18,404 (93.99%)** | **15,545 (79.39%)** |

The eight-frame setting meets 90% individual-hit recovery at every tested
rate. The four-frame setting meets 80% on the 2.5 and 5 MS/s aggregates only; it misses 80%
across the mixed-rate cohort and at 7.5/10 MS/s. Do not label it an all-rate
80% option. Higher-rate sparse ARM timing is not measured here; the preceding
exact FFT-coarse variant may be preferable there.

| Rate (MS/s) | Original positive windows | 8-frame windows with a recovered hit | 4-frame windows with a recovered hit |
| ---: | ---: | ---: | ---: |
| 2.5 | 1,682 | 1,587 | 1,326 |
| 5 | 1,874 | 1,734 | 1,451 |
| 7.5 | 1,933 | 1,772 | 1,473 |
| 10 | 1,518 | 1,387 | 1,149 |
| **Total** | **7,007** | **6,480** | **5,399** |

Hit matching is one-to-one within the same receiver and window, with epoch
error <= 2 samples, tracking CFO error <= 8 kHz, and margin >= 0.025 for both
entries. Hits are individual candidate hypotheses, not unique transmitters.

Eight frames emit 844 unmatched positive hypotheses and make 151 formerly
baseline-negative windows positive. Four frames emit 1,575 unmatched positive
hypotheses and make 171 formerly baseline-negative windows positive. These
are not automatically false positives, but they are changed scientific output
and do not count as recovered baseline hits. Independent details are in
COHORT_AUDIT.md and COHORT_AUDIT.json.

## Selection and validation

The initial 64-dwell screen rejected 32-center budgets: 1/3 recovered
101/1,669 hits, 2/6 recovered 403/1,669, and 4/12 recovered 1,036/1,669.
Widening to 128 centers recovered 1,247/1,669 for 4/12 and 1,521/1,669 for
8/12. These results guided the expanded tests and are not held-out evidence.

Excluding exactly those 64 selected dwells, eight frames recover
**16,883/17,912 hits (94.26%)** on the remaining 640; four frames recover
**14,298/17,912 (79.82%)**. At 2.5 MS/s the corresponding figures are
3,893/4,088 (95.23%) and 3,327/4,088 (81.38%). This is a held-out portion of
the same corpus, not proof of generalization to future RF conditions.

The full-budget control matches all 11,264 candidate objects and 1,669 hits
in the 64-dwell cohort. Host normal and sanitizer tests cover repaired-grid
identity, partial/zero input and all rates. Endpoint fixtures require peaks
at epochs zero and N-1 to remain eligible and retained. Both 128-center ARM
units pass all-rate partial/full/zero and endpoint checks. The independent
scorer rejects missing windows and incomplete GLRTs and uses maximum-cardinality
matching rather than greedy association. Exact source archives and receipts
are under builds/; original fixtures and production analyzers are unchanged.

## Remaining real-time goal

These profiles reduce cost but do not meet the 40% headroom goal. Even the
eight-frame result consumes roughly 27.8 CPU seconds for 0.12 seconds of
dual-RX input, versus the 0.072 CPU-second budget. Concurrent capture remains
unqualified at these costs. Faster discovery and cheaper per-candidate
refinement are both still needed; no real-time deployment is claimed.

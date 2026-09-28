# Selective boundary fallback for fast GLRT refinement

**The requested 90% recovery target is exceeded on this development cohort:**
19,576/19,581 individual original hits recovered (99.9745%), including
4,573/4,573 at 2.5 MS/s. Measured ARM runtime is 25.084860 CPU seconds/dwell:
1.32218x faster than the latest exact-cache baseline and 1.34456x faster than
the preceding full verification-fusion baseline. This is not yet real time.

The fine-direct path loses original hit matches mainly when residual CFO
crosses the principal GLRT interval boundary. This variant first executes
fine-direct, then runs the original conditioned search and a second GLRT only
when residual CFO is within 1 kHz of either +/-113.636 kHz boundary. It uses
the current IQ result alone, not baseline frequencies or labels.

All original windows and eight coarse candidate entries remain present.
The fallback uses the original conditioned grid, screen, guarded exact
near-maximum rechecks, and tie-breaking. Nonfallback candidates retain their
fine-direct results. Normalized verification and its candidate ordering remain
skipped. Thus this is an approximate fast path with measured hit recovery,
not exact equality of all scientific fields or candidate ordering.

## Qualification

The completed 704-dwell run covers the following original windows and hits:

| Rate (MS/s) | 20 ms windows run | Original hits | Recovered hits | Original positive windows | Positive windows recovered |
|---|---:|---:|---:|---:|---:|
| 2.5 | 3,344 | 4,573 | 4,573 | 1,682 | 1,682 |
| 5 | 4,752 | 5,466 | 5,464 | 1,874 | 1,873 |
| 7.5 | 4,048 | 5,186 | 5,185 | 1,933 | 1,933 |
| 10 | 3,344 | 4,356 | 4,354 | 1,518 | 1,518 |
| Total | 15,488 | 19,581 | 19,576 | 7,007 | 7,006 |

All 123,904 candidate entries are evaluated. There are 9,477 fallbacks
(7.65%) and 133,381 actual GLRT kernel calls, including second evaluations.
The new method produces 19,578 positive hypotheses, of which two are unmatched
to the original. No originally negative window becomes positive. The five
missed original hits are nonfallback margin crossings near the 0.025 gate:
original margins 0.025029178–0.025252592 become 0.024487588–0.024957637.
Cases are recorded in `margin-crossings.json`.

The initial 64-dwell host run processes 1,408 overlapping 20 ms windows and
11,264 candidate entries. It recovers **1,669/1,669 original individual hits**
and **691/691 positive windows**, with one unmatched new positive hypothesis.
There are 854 conditioned fallbacks and 12,118 actual final-GLRT kernel calls.

An independent per-proposal path audit requires all computed final fields
(epoch, acquired/tracking CFO, exact/control score, margin) to exactly equal
the full-refinement baseline for fallback candidates and fine-direct for
nonfallback candidates. It also checks conditioned-field presence and that
uncomputed verification fields remain null. This audit passed both the initial
64-dwell and full 704-dwell cohorts. Scientific recovery is scored separately with one-to-one matching
within the same receiver/window, <=2 samples and <=8 kHz, margin >=0.025.

The inherited harness's `summary.json` exact-equality flag remains false:
candidate ordering and uncomputed verification fields intentionally differ.
The recovery result comes from `hit-and-work-audit.json`, not that flag.
`final-verification.json` verifies identical saved ARM inputs across all four
methods and the hashes of all 48 sources and three binaries in each build.

Host normal and ASAN/UBSAN units cover all four rates, partial/full/zero input,
direct GLRT equality at the returned frequency, the nonregular clipped grid
endpoint, and both signs of the residual boundary. The ARM unit passes these
tests. Archived host v1, strengthened-test host v2, ASAN and ARM builds have
identical core algorithm source; source and binary hashes are in builds/.

## Selection limitation

The threshold was chosen using the preceding fine-direct results across the
same 704 DS7 dwells. All 3,370 observed baseline-positive per-proposal frequency
mismatches lay within 1 kHz of the boundary, while 9,477/123,904 candidates
were flagged in total. The subsequent IQ run is necessary implementation and
recovery evidence, but this is development-set validation. Neither the full
704 nor its 640-dwell remainder is an independent holdout for this threshold.
No modulo frequency correction is used to manufacture baseline matches.

The cohort spans all 88 recordings but only 0.361% of the 194,934 DS7 dwells.
It is not full DS7. Newly positive hypotheses are counted separately and are
not automatically labelled false positives.

## ARM scope

The timing experiment processes saved IQ from RAM on CPU0 of PLUTO+
192.168.1.15. It uses the same four 120 ms dual-RX dwells as earlier full
and fine-direct comparisons, without RF collection or simultaneous capture.
File transfer and workspace setup are outside search timing. Conditioned
and GLRT stage timings are disjoint; the total includes the fallback overhead.

| Method | ARM CPU seconds / dwell | Individual hits recovered on ARM |
|---|---:|---:|
| Full verification fusion | 33.728123 | 119/119 |
| Latest exact refinement cache | 33.166615 | 119/119 |
| Fine-direct without fallback | 24.454528 | 100/119 |
| Selective boundary fallback | 25.084860 | 119/119 |

The four ARM dwells contain 88 overlapping windows and 704 candidate entries.
The new method recovers all 49 original positive windows, has zero unmatched
positive hits, and runs 757 GLRT kernel calls including 53 fallbacks. It costs
0.630332 seconds/dwell more than fine-direct while restoring its 19 lost hits.
Versus the latest exact cache, CPU time falls by 24.37% (8.081755 seconds/dwell).
The coarse search still consumes 19.771048 seconds/dwell, about 79% of the new
total, and is the next substantial runtime target. Mixed-rate recovery above
was evaluated on the host; ARM timing here is specifically at 2.5 MS/s.

Meeting the requested 90% recovery/speed tradeoff does not establish the
broader real-time 40% headroom objective. Every result remains far above
the 72 ms CPU budget per continuously arriving 120 ms dual-RX dwell.

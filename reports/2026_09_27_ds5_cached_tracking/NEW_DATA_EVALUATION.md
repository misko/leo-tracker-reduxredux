# New-recording evaluation

Current scope is general server compute; ARM qualification is deferred. New
recordings were used in the completed server SIMD and concurrency experiments.
The 320-case paired validation retained 169/169 reference positives with no
extras, but integer SIMD added only 1.0006x CPU speedup over stable FP32. Total
FP64-to-SIMD CPU speedup was 1.4128x. Separately, eight-worker stable FP32 replay
of the 256 real receiver cases reached 3.08x batch throughput versus FP64 while
retaining all 129 reference positives. Two-receiver parallelism worsened p95
latency and increased CPU. These are separate measurements, not multiplicative
gains. See `SERVER_COMPUTE.md` and the linked detailed reports for timing
boundaries and limitations.

The operator pause blocks physical-radio qualification through the capture
authority. It does not block reading saved recordings or server-side replay.
This evaluation uses newly completed recordings identified on 2026-09-27 after
04:34 UTC, separately from the original DS5 development and unopened holdout.

Before inspecting detector outcomes, select the latest completed eligible
2.5 MS/s session and 5 MS/s session and a deterministic consecutive 64-visit
120-ms block in each, using metadata and channel coverage only. Both receivers
are included. Treat these as new development evidence, not an untouched final
holdout. The current native comparison does not support 7.5 or 10 MS/s.

Run the existing configurations unchanged:

- `config.dev.v6.strided.json`: full-aperture cached tracking with direct
  strided blind ingest, compared with independent packed blind acquisition.
- `config.dev.v5.partial2.json`: two-frame cached checks with the original
  packed blind fallback, compared with its own independent blind reference.

Each replay retains the existing chronological state rules, fresh-IQ checks,
reference matching tolerances, one warmup and three timed repetitions. Failed
checks and actual blind fallback count toward total cost. Report reference
retention, extra unadjudicated positives, cache attempts/hits, blind calls,
whole-replay cost and hit-only cost separately at each rate. Ratios from the
two variants are not multiplied or interpreted as ARM measurements.

Do not tune thresholds or choose a different block based on these outcomes.
Keep the original DS5 fixtures and holdout unchanged. No new RF collection is
part of this work.

## Results from unchanged configurations

The new manifest SHA-256 is
`b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845`.
It contains visits 1077–1140 from upper-edge 2.5 MS/s session
`scan-fw-40ebc07665464c7d` and lower-edge 5 MS/s session
`scan-fw-e76c229e9dc498b3`. Both completed on 2026-09-27. Each row below measures
all 256 receiver-visits against an independently executed blind reference.

| Variant | Cache attempts / hits | Blind calls | Whole CPU speedup | Hit-only CPU speedup | Reference identity matches |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full aperture + strided ingest | 126 / 74 | 182 | 1.797x | 9.179x | 120/129 |
| Two-frame checks + packed fallback | 126 / 69 | 187 | 1.336x | 29.501x | 120/129 |

The reference has 62 positives at 2.5 MS/s and 67 at 5 MS/s. Both strategies
remain positive on all 129 reference-positive receiver-visits and produce no
positive on a reference-negative visit. However, the same nine cached outputs
do not match the reference timing/frequency identity: two at 2.5 MS/s and seven
at 5 MS/s. CFO differences are approximately 39–152 kHz and circular timing
differences 90–371 microseconds. Positive counts alone therefore do not qualify
either strategy. Neither meets the frozen reference-retention gate.

Restricting the hit-only timing comparison to identity-matched cache hits gives
9.227x for the 65 full-aperture hits and 28.899x for the 60 two-frame hits. These
conditional costs do not replace the whole-replay result or its retention gate.

All 182 full-aperture fallback results and all 187 two-frame fallback results
match the independent reference's scientific fields exactly. The mismatches
arise in accepted cached outputs. Whether they represent a continued different
signal or incorrect acceptance requires separate diagnostic evidence; these
recordings have no independent physical truth labels.

A post-outcome diagnostic independently searched all six windows on those nine
receiver-visits, using the unchanged blind detector without cached seeds. Seven
cached identities were recovered by a positive, freshly fitted candidate within
the original 2-us/8-kHz matching bounds; two were not. This supports competing
signal/alias hypotheses as an explanation for many differences, without proving
physical identity or clearing the two unresolved cases. The original 120/129
gate result is unchanged. This selected diagnostic does not contribute timing
or qualification evidence. See `new_data_mismatch_diagnostic.json` and
`review/NEW_DATA_MISMATCHES.md`.

The full-aperture replay falls back after 52 failed predictions; 38 of those
visits are reference-positive. Simply treating a failed cache check as absence
would therefore lose substantial reference coverage. The stronger signal
population in this new cohort makes tracking continuity and competing timing/
frequency hypotheses concrete next questions, rather than grounds for silently
relaxing matching tolerances.

Receipts are `new_data_v6.json` and `new_data_partial2.json` in the parent
directory. They record native/source/input hashes and per-case timings. These
are server development results, not ARM qualification or a 10x whole-pipeline
claim. The operator pause remains relevant only to physical ARM execution.

## Follow-up local-recovery experiment (specified before execution)

Run `config.new_data.recovery.json` once on the same new development dataset.
It changes only `local_recovery` from the full-aperture V6 configuration. The
existing native implementation checks timing at minus/plus one sample, then
interpolates a bracketed peak; it does not search a different CFO hypothesis.
Charge the failed point check, recovery and any blind fallback. Keep the same
2-us/8-kHz identity gates, thresholds, warmup and three timed repetitions.
Report whole-replay cost, matches and cache hits even if this fails. No tuning
or holdout use follows from the result.

The completed replay (`new_data_recovery.json`) recovered no additional cache
hits: 74 hits, 52 failed predictions, 182 blind calls and 120/129 identity
matches remain. Whole CPU speedup was 1.653x against its independent baseline,
versus 1.797x in the earlier no-recovery run. Separate run timings are not a
paired estimate of the regression, but there is no scientific or hit-rate
benefit to offset the added recovery work. Do not promote this variant.
The receipt-only coordinate audit in `review/NEW_DATA_CACHE_FAILURES.md`
explains the limited recovery range and distinguishes oracle historical
hypothesis availability from actual causal recoveries.

## FP32 transfer result

The separate frozen unseeded strided FP32 FFTW comparison retained **129/129**
reference positives, including 67/67 at 5 MS/s, with zero extras or rank/window
changes. All 24 constructed controls retained their decisions. Complete detector
CPU cost including receiver ingress improved **1.620x** (1.618x at 2.5 MS/s,
1.621x at 5 MS/s), excluding file loading and hashing. This passes its numerical
transfer gate on the new development cohort. It does not establish physical
truth, ARM performance, combined cache performance or 10x pipeline speedup.
See `new_data/fft32_transfer/REPORT.md` and its frozen `results.json`.

The next promising development experiment is a bounded causal bank of timing/
frequency tracks per channel, with explicit identity and ambiguity handling,
fresh-IQ confirmation and blind discovery/fallback costs retained. Seven of
nine disagreements have independent lower-ranked candidate support, but two
remain unresolved; this cannot justify relaxing the original gate. The bank
must be specified and evaluated before assigning any speedup to it.

## Measured combination and remaining budget

The frozen combined experiment uses FP32 FFTW for actual blind fallbacks and
the unchanged full-aperture V6 cache. It measures **1.960x** complete replay CPU
speedup (1.892x at 2.5 MS/s, 1.997x at 5 MS/s), with 74 cache hits and 182 blind
calls. Identity matching remains **120/129**, with all nine disagreements in
accepted cache outputs. All 55 reference-positive fallback rows match and no
fallback rank/window changes occur. This is not a qualified combined variant.
See `new_data/combined_fp32_cache/REPORT.md`; gains are measured, not multiplied.

The complete-cohort independent all-window diagnostic finds 159 receiver-visits
with at least one positive fit, compared with 129 first-ranked positives. The
existing cache outputs match some independent positive candidate in 127/129
cases; two remain unresolved. This is diagnostic evidence only, with the
original identity gate unchanged. See `review/ALL_WINDOW_RESULTS.md`.

The V6 cost audit shows that free accepted cache hits alone would cap whole
speedup at 1.906x. With their observed cost retained, average nonhit work must
fall from 1.919 ms to at most 0.249 ms to reach 10x against that replay baseline.
See `review/TEN_X_REMAINING_BUDGET.md` for measured versus modeled bounds and
the proposed acquisition redesign. A cache-only optimization cannot close this
gap while preserving current discovery coverage.

## Three-track causal bank: rejected

The separately frozen bank stores at most three tracks per key, scores every
live prediction with fresh full-aperture IQ, and selects the largest accepted
current margin. Actual blind discovery confirms three ranked windows, retains
distinct positive fits and charges all three confirmations. Expiry remains two
seconds and periodic discovery is global across tracks. Reference results do
not enter state, selection or eviction.

It retains **118/129** top-reference identities, with 11 unmatched positive
outputs, and runs at **0.779x** baseline speed (28.4% more CPU). It makes 264
cache checks across 161 attempted visits, accepts 58 cache hits, and performs
198 blind calls containing 594 confirmations. All 24 isolated control decisions
remain unchanged. Both scientific and cost gates fail; adding tracks in this
form worsens performance and is not promoted. See `multitrack/results.json`
and `multitrack/REPORT.md`. No outcome-driven retuning or holdout run followed.

The subsequent source/operation-count audit rejects a literal visit-wide
timing-by-CFO surface: it would require 26.2/52.4 million cells per receiver at
2.5/5 MS/s before final GLRT work. `review/AMBIGUITY_ENGINE_FEASIBILITY.md`
supersedes that architectural suggestion in the budget review. It specifies a
smaller lag-3 sparse proposal feasibility test with an early 0.080-ms budget;
this was a proposed new statistic, not a demonstrated speedup; results follow.
The complete detector must still meet its own cost and scientific gates,
including nuisance treatment and final scoring. The 10x objective remains open.

## Lag-3 proposal: rejected at the early gate

The isolated lag-3 prototype now exists and has been measured on all 256
new-development receiver-visits. Complete caller thread CPU medians were
0.461 ms at 2.5 MS/s and 0.994 ms at 5 MS/s, versus the frozen 0.080-ms proposal
budget. It stopped before GLRT integration. See `lag3_proposal/REPORT.md`.

An independent 20-case dual-RX synthetic dataset was frozen before candidate
evaluation, with continuous CFO, physical fractional frame timing, band-edge
carriers, noise, tones and pilot mixtures. The proposal-only audit matches
injected coordinates within 2 us/8 kHz for just 9/24 single-pilot receiver cases,
0/4 pilot-plus-tone cases and 2/4 two-pilot cases (one trajectory only). None
of eight noise/tone receiver cases has a supported proposal; this is not a
false-alarm measurement. See `lag3_controls/README.md` and
`lag3_validation/REPORT.md`. The kernel and dataset were not tuned afterward.

Many failures concern timing proposals, not only carrier phase. Lag-3's
alias-free range therefore does not establish usable acquisition accuracy.
This prototype supplies neither a qualified detector improvement nor a
measured 10x result. It does provide a reusable constructed challenge set
and rules out this particular projected timing/phase implementation.

## FP32 adversarial transfer and exact-work audits

The unchanged packed FP64 and strided FP32 FFTW detectors were independently
run on all 40 receiver cases of the new constructed challenge set. Both return
32 positives, with all 32 FP32 outputs matching FP64 within 2 us/8 kHz, zero
extras, and no rank or selected-window changes. Both associate a supported
positive to an injected pilot on all 32 pilot-bearing cases. Each two-pilot
case selects trajectory `a`; this does not establish recovery of both signals.
The comparison is science-only and adds no new speed measurement. See
`new_data/fft32_adversarial_transfer/REPORT.md`.

Two source audits avoid low-payoff implementation work. Conditional reuse of
the rank lag fold is mathematically possible when tone subtraction is not
applied, but coarse acquisition still needs folded power and its own search.
Even eliminating all coarse work has only a 1.17–1.20x caller ceiling in the
available server profile (`review/RANK_ACQUISITION_REUSE.md`).

The apparent scalar CI16 hotspots in the x86 build already have NEON paths in
the prepared ARM implementation (`exact_loop/AUDIT.md`). An SSE port would
therefore improve server-specific timing without establishing a new ARM gain.
The remaining packing work misses the server projection gate; its physical ARM
cost is still unknown. Neither audit establishes an ARM performance bound or
a 10x result. No new candidate implementation or replay followed these audits.

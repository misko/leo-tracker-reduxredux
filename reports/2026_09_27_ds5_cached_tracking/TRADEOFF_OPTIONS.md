# Options for a 10x speedup with explicit quality tradeoffs

**Recorded qualification update:** the frozen candidate fails quality on both
original holdout sessions despite 19.21x/19.05x CPU savings. Retention is 37/43
and 5/6, rescue adds two unmatched outputs at 2.5 MS/s, and one associated visit
is lost at 5 MS/s. Prioritize compatible native scoring and temporal discovery
coverage before considering this a small-loss replacement. See
`tone_recorded_holdout/REPORT.md`; the original holdout is now consumed.

**Validation update:** the frozen candidate passes its 26-case reserved
constructed evaluation at 40.80x/48.17x aggregate CPU gains, with 38 associated
positives, ten correct negatives and four weak inactive pilots. No native rescue
confirmation runs in this split; it does not independently qualify recorded
recovery. Validation IQ and original real holdout are now consumed.
See `tone_validation/REPORT.md`; earlier unopened statements below
are historical.

**New measured compromise:** native tracking plus bounded same-receiver rescue
with the native blind tone-removal step now achieves 23.55x/21.12x aggregate CPU
speedup at 2.5/5 MS/s on 64 recorded development visits. Reference receiver
retention improves from 67/79 to 78/79 (1.27% remaining reference loss), with
no additional extras from rescue and all constructed control gates passed.
This supersedes the earlier 18–22x planning estimate for this implemented
variant. It does not qualify a real-time replacement: 28/32 5-MS/s calls exceed
120 ms, and reserved validation remains unopened. See
`native_tone_rescue/REPORT.md`. The earlier 76/79 inventory opportunity count
was not a true ceiling: guided confirmation recovered hypotheses absent from
the independent application probe-two search inventory. The raw rescue's
failed gate remains preserved and is not retroactively repaired.

The user now explicitly accepts a small loss in accuracy or other metrics to
reach 10x. Exact agreement with the old scanner is therefore not a universal
acceptance requirement for future experiments. Existing frozen experiments and
their failed gates remain unchanged; those failures describe their original
contracts. Future candidates should be compared on measured cost, sensitivity,
constructed false positives, timing/frequency accuracy, discovery delay and
reporting coverage. A large or unmeasured error rate is not a demonstrated small
tradeoff.

## Baseline and strongest evidence

The complete current scanner processes eleven overlapping 20 ms probes from
each receiver and retains ten acquisition candidates per probe. TG11-v1 uses
native C and FP32 FFTW processing, a much smaller candidate inventory, and a
different final statistic. Both process the same 120 ms dual-RX input in the
paired four-visit experiment; initialization, loading and hashing are excluded.

| Rate | Current scanner CPU | TG11 CPU | Observed ratio |
|---|---:|---:|---:|
| 2.5 MS/s | 1515.495 ms | 16.032 ms | 94.53x |
| 5 MS/s | 4071.329 ms | 33.150 ms | 122.81x |

These are two recordings per rate, not a corpus-wide accuracy or tail-latency
claim. All routes were blind, so the ratios do not measure track reuse. Three
comparator-positive visits were retained. The fourth had an additional native
positive, and the current Python point scorer also passes that hypothesis when
given its timing/frequency. The old acquisition search did not retain it. This
is additional GLRT evidence, not established physical truth or a known false
alarm. TG11 passed its strong constructed controls; weak-signal behavior is
still unqualified. See `tg11/PHASE1_REPORT.md` and `tg11_diagnostic/REPORT.md`.

## Practical option portfolio

**Broader recorded-data update:** the new frozen native experiment completed
64 saved visits. Native blind measured 100.06x/122.80x aggregate CPU speedup;
tracked measured 131.02x/167.04x at 2.5/5 MS/s. All 56 application-positive
visits retained an associated native detection, but only 67/79 positive
receiver identities were retained (15.19% loss overall), plus two additional
native-positive visits. This is promising for visit-level discovery, not a
demonstrated small dual-receiver measurement loss. Tracking added
1.309x/1.360x over blind with no additional activity or identity disagreements
in the replay. See `native_tradeoff/REPORT.md`. These supersede the small
four-visit study as the broadest current paired evidence, without altering it.

| Option | Evidence or potential | Main tradeoff |
|---|---|---|
| Use TG11's native decision detector | Measured 94.53x/122.81x in the small paired study | Different search/report/statistic; weak-signal and multisignal retention unknown |
| Spend TG11 headroom on more candidates and stronger confirmation | Two candidates now tested: candidate zero was unchanged in all 2,904 recorded engine observations, but candidate one recovered none of the K1 reference losses; original reference-point scoring accepted 11/12 strongest supplied hypotheses and the qualified boundary guard accepted 12/12 | More computation; two-candidate tracking introduced one additional active identity mismatch, and oracle-supplied point coordinates do not provide causal acquisition |
| K1 native first, then one same-RX probe-0 acquisition and native probe-2 confirmation for an inactive receiver | Implemented bounded control stage; baseline passed 84/84 original receiver policies | Rejected: rescue passed 82/84 and the paired orientation audit exposed three distinct tone parent/RX false-positive sources; diagnostic/real stages did not run |
| Fast detector plus selective full-scanner fallback/audit | Budget model below leaves 10x room if full calls are sufficiently rare | Unflagged errors can escape; full-call tail latency remains; audits must sample confident negatives too |
| Reuse a found channel's timing/frequency, with fresh confirmation | Four genuine guided receiver confirmations; 1.225x on a ten-step constructed sequence within the canonical prototype | Drift, wrong tracks and new signals require fallback/discovery; cache alone does not cover cold/quiet traffic |
| Stop as soon as a valid pair is found | Exact decision-only early exit measured 3.874x/1.761x on two positives | Loses complete diagnostic report; no gain on fully negative scans |
| Reduce retained candidates in the existing scanner | Untested tradeoff; cannot remove its dominant shared coarse search | Misses secondary/weak basins; ten-to-one candidates does not imply tenfold total speed |
| Reduce windows, e.g. eleven overlapping to six disjoint or two selected | Approximately 1.83x/5.5x fewer probe calls before overhead, not measured speed | Boundary/short-burst losses; two probes inspect only 40 ms of the 120 ms record |
| Use one receiver, or process the second only when needed | At most about 2x fewer receiver calls; unmeasured here | Loses diversity or secondary-signal evidence; cannot reuse the other receiver's CFO without qualification |
| Shorten integration or confirmation support | Earlier two-frame cache had large hit-only savings but only 1.336x whole replay on its separate native baseline | Weaker evidence, poorer low-SNR sensitivity and less precise estimates |
| Coarser timing/CFO grids, restricted search around a track, fewer refinements | Untested new variants; targets acquisition, which dominated measured scanner cost | Off-grid loss, alias selection, weaker CFO/timing accuracy; occasional broad discovery required |
| Filter/decimate or process a narrower band | Untested on identical input with complete conversion cost | Discards bandwidth and possible signal components; needs anti-aliasing and counter/template correctness |
| Cheap energy/correlation/cyclostationary or learned proposal/screen | Untested qualified fast-negative route; potentially useful on mostly empty traffic | Weak signals can be screened out; classifier drift; a screen is not pilot identity evidence |
| Process fewer visits/channels, or revisit quiet channels less often | Up to proportional workload reduction by policy, not a faster detector | Slower discovery, stale tracking and reduced coverage; skipped visits must be labeled unmeasured |
| Parallelize independent probes/receivers on CPU | 22-worker full-report prototype measured 8.20x/10.69x wall speed on two visits | Aggregate CPU increased 43%/29%; 169/373 ms latency still exceeded 120 ms |
| GPU/offload and batched acquisition/FFT | Untested here; can preserve a broad search rather than prune it | Transfer, dispatch, queueing, power and hardware cost; batching may hurt immediate scan decisions |
| FPGA or dedicated DSP accelerator | Longer-term untested hardware option | Substantial implementation/verification cost and less flexibility; not needed to explain the existing server speedup |
| FP32, SIMD, buffer/plan reuse, fused passes and overlap reuse | FP32/strided native work measured about 1.41x on a different one-confirmation workload; compact scanner workspace only 1.05x/~1.00x | Useful building blocks, not measured standalone 10x; precision changes need error checks |
| FP16/fixed-point, fewer pilot symbols, alternative matched-filter/pilot detector | Exploratory, no qualified whole-call results | Dynamic range, interference rejection and sensitivity can degrade; keep raw evidence for audit |

The raw canonical-confirmation prototype is **not** currently a small-accuracy-
loss candidate: it activated six of twelve base tone-only receiver controls.
It did demonstrate cache mechanics. Native TG11 rejected those tone controls,
so retaining nuisance/interference rejection is important. Frame-timing
consistency is a plausible additional check: the failed canonical tone pairs
had grossly inconsistent epochs. That observation is post-outcome diagnostic,
not a validated repair. See `canonical_tracking/REPORT.md`.

Fewer Python candidates alone cannot solve the full problem: the measured
shared coarse search occupied approximately 44.4%/68.5% of diagnostic CPU.
Even deleting all other work would leave only about 2.25x/1.46x speedup if that
coarse work were unchanged. Generic NumPy correlation/FFT replacements already
tested slower than the current AVX2 coarse kernel. A specialized visit-wide or
GPU implementation remains a distinct, untested architecture.

## How much slower verification can we afford?

The completed two-candidate experiment retained 67/79 application-positive
receiver identities in blind mode, recovering none of the one-candidate losses;
tracked mode retained 66/79. It added one unadjudicated visit at 2.5 MS/s.
All constructed true/false checks passed, but expansion alone did not solve
recorded receiver coverage. Candidate zero remained scientifically identical,
so the outcome is attributable to the extra proposals and pair/state selection,
not a regression in the original hypothesis. See `native_candidates/REPORT.md`
and `native_candidates/OBSERVATION_AUDIT.md`. The original one-candidate
detector remains the faster development baseline; the choice of what extra work
to perform matters more than simply doubling candidates.

The completed reference-point diagnostic supplied application timing and both
acquired and physical CFO directly to the native final scorer. The strongest
pair passed for 11/12 missed receivers, and 15/17 selected missed-receiver pairs
passed overall. This shows that most missing identities have usable native point
evidence when their coordinates are already known. It does not supply a causal
search, reuse blind nuisance fitting, or measure a detector. One strongest point
was rejected at the mathematical half-symbol CFO-support boundary because of a
roughly `2.8e-9 Hz` floating-point excess. The completed microhertz-scale guard
qualification admitted that point: guarded acceptance increased from 19/21 to
20/21 supplied pairs, and all 12 strongest missed-receiver pairs passed. All 41
ordinary point results were scientifically identical, and both engines passed
all 42 control/sequence cases with identical truth decisions and routes. The
remaining rejected pair still failed the unchanged physical-innovation status,
so the guard did not hide its roughly 226.8 kHz alias error. These coordinates
were supplied from the application receipt; this is numerical admission and
parity evidence, not causal discovery. See `native_reference_points/REPORT.md`
and `native_guided_boundary/results.json`.

The bounded same-receiver rescue has now been implemented and rejected at its
first scientific gate. It preserved every K1 primary positive, permitted one
Python acquisition for the first inactive receiver, and required guarded native
evidence at both probe zero and nonoverlapping probe two. The tracked baseline
passed all 84 original control receiver policies; rescue passed 82/84 after
accepting two constructed 5-MS/s tones. The twelve-parent paired orientation
audit recorded three false-active executions: two repeated those original
failures, while RX swapping exposed a third distinct 2.5-MS/s tone parent/RX
source. Thus five receipt failures correspond to three distinct physical tone
parent/receiver failures. The diagnostic and recorded-data stages did not run,
so the earlier 9/11 proposal coverage and 22x/18x mixed-receipt estimates remain
planning ceilings rather than measured recovery or speed. The native K1
baseline remains valid. See `native_rescue/REPORT.md` and
`native_reference_points/RESCUE_FEASIBILITY.md`.

For planning only, let `B` be full-scanner cost, `F` fast-detector cost, and `p`
the fraction of visits receiving an additional full call. Then average CPU is
`F + p*B`, before any new verification/dispatch overhead. Applying the measured
four-visit medians gives:

| Additional full-call fraction | 2.5 MS/s estimated CPU | Estimated ratio | 5 MS/s estimated CPU | Estimated ratio |
|---:|---:|---:|---:|---:|
| 0% | 16.03 ms | 94.53x | 33.15 ms | 122.81x |
| 1% | 31.19 ms | 48.59x | 73.86 ms | 55.12x |
| 2% | 46.34 ms | 32.70x | 114.58 ms | 35.53x |
| 5% | 91.81 ms | 16.51x | 236.72 ms | 17.20x |
| 8% | 137.27 ms | 11.04x | 358.86 ms | 11.35x |

The algebraic 10x limits are about 8.94%/9.19% additional full calls. Actual
limits depend on which visits trigger fallback and their costs; uncertainty and
weak signals may be correlated with slower calls. This table is not a measured
hybrid benchmark or a claim that auditing corrects every error. A random audit
must supplement uncertainty triggers to detect confident mistakes.

Tenfold faster is not the same as real time. Tenfold over these scanner medians
still means 151.5/407.1 ms for a 120 ms recording. For average processing below
120 ms on one core, the same simple model permits approximately 6.86%/2.13%
additional full calls, before overhead. Any synchronous fallback still takes
roughly the full scanner's time; background audits exchange immediate correction
for lower foreground latency and must count toward total compute.

## Current decisions and remaining options

1. Keep the completed same-RX rescue rejected unchanged. It failed constructed
   tone controls despite two native confirmations; do not advance it to the
   diagnostic or recorded-data stages or count its planning ceiling as recovery.
   Compare the measured result with the 76/79 proposal ceiling and the 22x/18x
   planning model; neither is an acceptance result.
2. The qualified numerical support-boundary guard was carried into the failed
   rescue comparison. Its admission fix remains valid, but it did not prevent
   tone false positives because those hypotheses passed the unchanged status,
   margin, timing and physical-innovation gates. Continue to keep
   acquired/scoring CFO separate from residual-corrected physical CFO.
3. If fixed probe zero/two misses remain, compare one preregistered bounded
   extension for the two observed later-return identities at probes three/four.
   Count its extra work on every eligible visit. Do not use the application
   inventory or the other receiver to select coordinates at runtime.
4. Keep the exact parallel scanner as a latency-oriented alternative if spending
   more cores is acceptable. Its result is not a CPU-efficiency improvement.

Compare a quality/compute frontier rather than a single equality gate. Proposed
comparison bands are 0%, 1%, 3% and 5% additional missed reference detections;
these are experiment bands, not an assertion that the user authorized any
particular loss. Also report constructed false alarms, injected-pilot
association, timing/CFO errors, multisignal coverage, first-discovery delay,
median/p95/p99 wall latency, aggregate CPU, memory and fallback frequency.
Always stratify by SNR, rate, interference and cold versus tracked state.

The new dataset has 26 development cases and 26 reserved validation cases.
The fixed native blind/tracked experiment has now evaluated all development
cases: 38 injected-truth-associated native positive receiver cases, ten inactive
constructed negatives and four inactive weak pilots in each mode. Blind native
CPU improved 94.49x/115.48x at 2.5/5 MS/s; tracked native improved
105.37x/126.60x. Both modes agreed in activity and identity on all 52 receiver
cases. These are a new paired experiment, not multiplied earlier gains. See
`native_tradeoff/REPORT.md` for timing boundaries and symbol-region differences
from the comparator. The limited negative sample cannot establish a very low
field false-alarm rate; larger fixed-seed negative cohorts will be needed for
precise small-error claims. Validation IQ remains ungenerated and the original
holdout stays unopened until a candidate and its tradeoff criteria are frozen.

Implementation references for accelerator experiments: FFTW permits concurrent
execution but requires care around planning/destruction
(https://www.fftw.org/doc/Usage-of-Multi_002dthreaded-FFTW.html); NVIDIA cuFFT
supports batched, strided transforms
(https://docs.nvidia.com/cuda/cufft/index.html). Neither reference supplies a
speed prediction for this workload.

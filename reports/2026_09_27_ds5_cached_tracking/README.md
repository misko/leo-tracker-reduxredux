# DS5 causal cached-channel GLRT evaluation

**Expanded proposal result:** `expanded_proposals/REPORT.md` records 318 searches
over 106 inactive receiver visits. Fixed seeds 0/5/10 recover only one of four
expanded-cohort misses; the late seed adds one unmatched output. The three
remaining misses share a recent earlier detection on channel 3 RX1, which the
current tracker forgets after a negative visit. Next test an expiring dormant
search hypothesis with fresh confirmation; no cache recovery is claimed yet.

**Expanded development reveals later-window misses:** `expanded_development/`
evaluates 64 fixed visits in two additional exposed sessions. The local-confirmed
primary retains 9/13 receiver identities at 2.5 MS/s and loses three associated
visits despite 107.49x CPU savings. The 5 MS/s cohort has no reference positives,
so it cannot establish sensitivity. Three missed 2.5 MS/s receivers have no
probe-zero member in their reference pair inventory. Use this broader exposed
cohort for the next proposal diagnostic; original holdout remains consumed.

**Distributed proposal diagnostic:** `distributed_proposal/REPORT.md` records
171 searches over every inactive development receiver. Seeds0/5/10 each recover
the same eleven missing identities, while the late seed adds one unmatched
output. Extra windows add cost without new recovery in this cohort. Broader
development coverage and fresh-confirmed rescue caching remain necessary;
these are proposal diagnostics, not a new end-to-end speedup claim.

**Local timing follow-up:** `early_local_tracking/REPORT.md` restores both
early-confirmation regressions through three integer timing checks, retaining
67/79 development identities at 14.09/26.45 ms mean candidate CPU. All 132
constructed receiver policies pass. It still misses 12 identities and needs
broader acquisition; this is a saved-reference replay, not a new paired
application speedup or held-out qualification.

**Controller follow-up remains unqualified:** `early_confirmed_tracking/`
passes all 132 constructed receiver checks, but recorded development retention
falls from native baseline 67/79 to 65/79. It removes two unmatched 5 MS/s
outputs and costs 13.18/23.20 ms mean CPU. This confirms cheap compatible
confirmation is feasible, but acceptance plus discovery still needs work.
See its `REPORT.md`, including the preserved reporting failure and corrected
replay; it does not replace the earlier candidate's failed holdout result.

**Next mechanism verified:** `native_early_profile/REPORT.md` records a separate
early-symbol raw native scorer agreeing with the current application at all
144 supplied recorded-development points and passing 37 generated/import tests.
This enables compatible fresh confirmation; it is not yet a replacement
controller or a new detector speed/quality result.

**Recorded holdout failed quality:** both 64-visit sessions completed at
19.21x/19.05x CPU savings, but receiver retention is 37/43 and 5/6. Rescue adds
two unmatched receiver decisions at 2.5 MS/s; 5 MS/s retains 41 baseline
unmatched decisions and loses one reference-positive visit. The candidate is
not qualified. See `tone_recorded_holdout/REPORT.md` for failure localization
and next experiment. Both original real holdout sessions are now consumed;
earlier unopened statements in frozen reports are historical.

**Reserved constructed validation completed:** `tone_validation/REPORT.md`
records 40.80x/48.17x aggregate CPU gains on the 26 previously reserved cases,
38 truth-associated positives, ten correct negatives and four weak inactive
pilots. All frozen constructed gates pass, but no native rescue point is reached
on this split, so recorded rescue recovery remains development-only evidence.
This validation IQ is now consumed, stored under `tone_validation/iq`; older
"validation unopened" statements describe the historical experiments only.
Original real holdout subsequently failed as recorded above; 5 MS/s latency exceeds 120 ms on
four of thirteen validation calls.

**Latest result:** `native_tone_rescue/` measured 23.55x/21.12x aggregate CPU
speedup on 64 recorded development visits, retaining 78/79 reference receiver
identities versus native tracking's 67/79. It recovered all 11 inactive misses
and preserved existing positives/extras; one active frequency alias remains.
All original and mirrored negative controls pass. This is development evidence,
not held-out qualification: 28/32 calls at 5 MS/s still exceed 120 ms. See
`native_tone_rescue/REPORT.md` for paired timing, reporting-adapter provenance,
and limitations. Research verification now passes 543 tests and 11 subtests in
two shards (the older frozen duplicate test basename remains unchanged).

**Current scope: general server compute.** The user has deferred ARM-specific
work. The radio pause does not block server SIMD or parallel evaluation; see
`SERVER_COMPUTE.md`. Earlier hardware-specific stopping decisions below are
historical and do not apply to these new server experiments.

**Updated evaluation preference:** the user accepts a small accuracy or other
metric loss for 10x speed. New experiments should measure the quality/compute
tradeoff rather than require exact scanner agreement universally. Historical
frozen gates and their outcomes remain unchanged. See `TRADEOFF_OPTIONS.md`
for the measured options, untested alternatives, fallback budget and proposed
evaluation bands.

**Latest recorded-data result:** `native_tradeoff/` completed 64 saved visits
against the current scanner. Native blind measured 100.06x/122.80x aggregate
CPU speedup; tracked measured 131.02x/167.04x at 2.5/5 MS/s. All native calls
were below 120 ms and all 56 scanner-positive visits retained an associated
detection. However, only 67/79 positive receiver identities were retained,
with two additional native-positive visits. This is not a demonstrated small
receiver-level loss. Tracking introduced no additional activity or associated
identity differences from native blind on 128 receiver occurrences and added
1.309x/1.360x incremental CPU benefit. See `native_tradeoff/REPORT.md`.

**Candidate expansion tested:** `native_candidates/` then compared two native
candidates per probe with the original one-candidate detector. K2 blind still
retains only 67/79 application-positive receiver identities, recovering none;
K2 tracked retains 66/79 due to one additional active identity mismatch. K2
remains 67–130x faster than the full scanner across rates/modes, but costs more
than K1 and is not adopted as a coverage improvement. All constructed truth
checks passed; all 132 fixed development cases completed with source hashes
stable. See `native_candidates/REPORT.md`. The research suite now passes
522 tests and 11 subtests. The guided-boundary qualification below does not
change the candidate-expansion coverage result.

**Search versus scoring diagnosis:** `native_reference_points/` supplied fixed
application hypotheses for all twelve missed receivers. The raw native point
statistic accepted the strongest pair for 11/12; the remaining pair hit a
nanohertz-scale input-support boundary, confirmed by a separate direct API
call. All 42 Python point scores reproduced the original receipt. This is
oracle-coordinate diagnostic evidence, not a causal rescue or new speedup.
It favors a bounded rescue acquisition plus fresh confirmation over further
blind candidate-count expansion. See its `REPORT.md` and
`RESCUE_FEASIBILITY.md`. The separately frozen `native_guided_boundary/`
experiment qualified a `1e-6 Hz` admission tolerance: all 41 ordinary point
results were scientifically identical, the single roundoff-boundary point
became a valid status-zero observation, and both engines passed all 84 causal
control receiver policies with identical decisions. Those point coordinates
were supplied from the application receipt, so this fixes the API boundary but
does not demonstrate that blind search discovers the missed identity.

**Same-receiver rescue rejected:** `native_rescue/` implemented the bounded
inactive-receiver path with one Python probe-zero acquisition and fresh native
probe-zero/probe-two confirmation. The unchanged tracked baseline passed all
84 original control receiver policies; rescue passed 82/84 after accepting two
constructed 5-MS/s tones. The paired original/RX-swapped negative audit found
three false-active executions. Two repeat the original failures, while the
swapped orientation exposed a third distinct 2.5-MS/s tone parent/RX failure
that fixed RX0-first selection had hidden. These five receipt failures represent
three distinct physical tone parent/receiver sources. Diagnostic and recorded
stages were not opened. The native fast-detector baseline remains valid; this
raw selective rescue is rejected. See `native_rescue/REPORT.md`.

The new track-guided decision experiment passed its complete constructed-control
gate: 42 dual-RX rows covering independent controls and appearance/dropout/change
sequences. All decisions took blind routes, so this establishes neither guided
cache accuracy nor a cache speed benefit. Paired complete-call server timing then
measured 16.03/33.15 ms against 1,515.49/4,071.33 ms at 2.5/5 MS/s. However, one
of four real visits produced an extra detection relative to the scanner, failing
the scientific gate. The larger replay was therefore not run. These are different
detectors, not an accuracy-qualified 94.53x/122.81x replacement. See
`tg11/REPORT.md` and `tg11/CONTROL_AUDIT.md`.

A subsequent frozen point-scoring diagnostic found that the existing Python
GLRT also passes both hypotheses of the disputed extra pair: margins 0.13562
and 0.11677 versus the unchanged 0.025 gate, with tracking CFOs 12.9 Hz apart.
The original application acquisition did not retain those hypotheses. This is
evidence of a search discrepancy, not proof of a physical false positive or
physical signal identity. The original TG11 gate remains failed. See
`tg11_diagnostic/REPORT.md`. A separate canonical-scoring tracker and a new
constructed dataset were developed without changing the failed experiment or
its original holdout. The canonical tracker has now completed
the frozen controls: it achieved four genuine guided receiver confirmations,
but falsely accepted six base tone receiver cases and one repeated tone case.
Its science gate failed. The ten-step synthetic sequence measured 1.225x CPU
benefit from caching within this new detector; that is separate from TG11's
16/33-ms server result. See `canonical_tracking/REPORT.md`.

The new diagnostic dataset has 26 materialized development recordings (93.6 MB)
and 26 reserved validation cases with frozen metadata/seeds and no generated IQ.
It includes a fixed analytic SNR ladder, colored noise, multitone interference,
symbol-region controls and fresh causal sequences. A new frozen native
blind/tracked evaluation has completed all 26 development recordings: 38
truth-associated positive receiver cases, ten true negatives and four inactive
weak pilots per method. The fixed ladder brackets the native decision boundary
at both rates. Native blind CPU improved 94.49x/115.48x; tracked CPU improved
105.37x/126.60x at 2.5/5 MS/s. All native calls were below 120 ms. These are
development results, not a production qualification. See
`native_tradeoff/REPORT.md` and `tg11_diagnostic/dataset/README.md`.
The preceding research component suite passed 444 tests and 11 subtests; that
does not override either historical failed scientific gate.

Latest full-response latency experiment: 22 persistent workers processing the
independent probes within one dwell achieved **8.20x at 2.5 MS/s and 10.69x at
5 MS/s**, with exact complete outputs on two development cases. This uses more
cores and increased aggregate CPU by 43%/29%; it does not establish a general
10x compute reduction. See `application_parallel/REPORT.md`. Exact decision-only
early exit measured 3.87x/1.76x CPU on the same positive examples, while generic
correlation/FFT coarse replacements were slower and were rejected. These gains
were measured separately and must not be multiplied.

The subsequent complete repository scanner profile identifies acquisition as
the main remaining target. Two metadata-selected 120-ms dual-RX visits took
1.615/4.143 seconds wall at 2.5/5 MS/s, each running 22 acquisitions and 220
GLRT scores. These full-analysis calls have a different output contract from
the one-confirmation native measurements below. See `APPLICATION_WORKLOAD.md`
and `application_profile/REPORT.md`; this is diagnostic evidence on two visits,
not a deployed-system timing or corpus qualification.

Latest server experiments: existing FP32/strided processing measured **1.412x
CPU speedup** against packed FP64 in a paired 320-case run. Additional integer
SIMD adds essentially no corpus benefit, despite exact result preservation.
Eight-worker FP32 processing achieved **3.08x batch throughput** on the new real
recordings; it does not establish comparable CPU savings or live latency gains.
All 169 reference positives in the 320-case validation were retained without
extras. See `server_simd_validation/REPORT.md`, `server_parallel/REPORT.md` and
`SERVER_COMPUTE.md`. Earlier timing ratios below are separate experiments.

New recordings are usable without radio access. The unchanged cached strategies
have now been replayed on 128 newly completed dual-RX visits, including 67
reference-positive receiver-visits at 5 MS/s. Full-aperture cached replay is
1.797x faster overall, but nine of 129 reference identities differ, so this is
**not a qualified transfer result**. The earlier 36/36 retention statements
below apply only to the original development cohort. See
`NEW_DATA_EVALUATION.md` for the new results and limitations.

The independent FP32 FFTW transfer **passes on the new recordings**: 129/129
reference positives, unchanged 24 controls, no extra positives or rank/window
changes, and **1.620x** complete detector CPU speedup. Local timing recovery
adds no cache hits and remains at 120/129 identity matches. See
`new_data/fft32_transfer/REPORT.md` and `NEW_DATA_EVALUATION.md`.

Further measured experiments: combining FP32 fallback with V6 caching reaches
1.960x but retains only 120/129 reference identities; a three-track causal bank
runs at 0.779x and retains 118/129. Both are rejected. The cache cost audit shows
why acquisition also needs redesign: free accepted hits alone cap the observed
V6 replay at 1.906x. See `review/TEN_X_REMAINING_BUDGET.md`.

The lag-3 proposal experiment is also rejected: its 0.461/0.994-ms caller
medians exceed the 0.080-ms budget, and an independent injected-coordinate
audit matches only 9/24 single-pilot receiver cases. See
`lag3_proposal/REPORT.md`, `lag3_controls/README.md` and
`lag3_validation/REPORT.md`. No GLRT integration followed the failed cost gate.

FP32 also passes the new adversarial constructed controls: 32/32 positive
receiver cases match FP64 and an injected pilot, with no added positives or
rank/window changes. This adds scientific evidence, not another speed result;
see `new_data/fft32_adversarial_transfer/REPORT.md`. Exact-loop and work-reuse
audits previously found no material new server prototype aligned with the ARM
target. That hardware-specific scope is now deferred; it does not block the
general compute experiments above.

Current full-coverage development variants run **about 1.5x faster across the
complete server replay**, retaining all 36 reference positives. The causal
full-aperture cache plus strided blind ingest measured 1.477x; an independent
all-blind FP32 FFTW variant measured 1.505x. These are separately measured
variants, not multiplied gains. The **10x whole-pipeline objective is not
achieved**. Separately, a two-frame cached check is 24.05x faster on its
twelve accepted hits but only 1.024x faster across all 256 receiver-visits. These
are server measurements, not ARM qualification.

Three SOL workers built the independent dataset, native scoring prototypes,
screening experiments, cost diagnostics and adversarial review. Everything uses
saved IQ. No RF collection, production deployment, public contract change or
golden-fixture update was performed. Earlier experiments remain unchanged.

Validation: the complete report tree passes 522 tests and 11 subtests. It is
collected in two shards because two frozen experiment directories intentionally
contain the same `test_run_evaluation.py` basename. Root replay/state/stress files pass Ruff. All native work remains
an isolated research prototype.

## Dataset and evaluation

`dataset/cases.json` freezes 256 real dual-receiver 120-ms visits: 128 development
and 128 fresh held-out visits, drawn from four 64-visit sessions at 2.5 and 5 MS/s.
The fresh sessions exclude previously evaluated sessions. Membership was selected
without detector outcomes. IQ is materialized locally with byte hashes and source
counters; QNAP sources are read-only. Dataset SHA256:
`4874540dfe94bd5ced2d5496d6c53635de22c8f5d59d8edf0a159c62a899d401`.

The fresh holdout remains unopened. The development reference finds 36 positives,
all at 2.5 MS/s; it cannot qualify positive sensitivity at 5 MS/s. Reference
misses are not noise truth. Prior constructed pilot, tone and noise controls are
separate from real data and cannot establish field false-alarm rates.

The strategy and reference independently process the same IQ with the same
native detector profile. Only the strategy's earlier observations update its
cache. Cost includes receiver packing, state, attempted checks and real blind
fallback; both receivers count. Each stateless action has one warmup and three
timed repetitions, with reference/candidate order counterbalanced. Ratios use
sums of per-case median costs. Loading/hash verification and initialization are
outside streaming compute. See `PROTOCOL.md` for the endpoint and guardrails.

## Development results

| Variant | Accepted cache hits / 256 | Reference positives retained | Hit-only CPU speedup | Whole-replay CPU speedup |
| --- | ---: | ---: | ---: | ---: |
| Point state, original ingest | 2 | 36/36 | 5.72x | 1.00x |
| Timing drift, original ingest | 12 | 36/36 | 4.93x | 1.01x |
| Timing drift, direct full-aperture ingest | 12 | 36/36 | 7.91x | 1.01x |
| Separate scoring/physical CFO, full aperture | 16 | 36/36 | 7.27x | 1.02x |
| Separate CFO, two-frame aperture | 12 | 36/36 | 24.05x | 1.024x |
| Separate CFO, full aperture, strided blind ingest | 16 | 36/36 | 7.38x | 1.477x |

The last row is `dev_strided_v6_final.json`: 1.567x at 2.5 MS/s and 1.435x at
5 MS/s, with 1.476x overall wall speedup. All 240 blind-fallback results match
every reference scientific field exactly, excluding timing instrumentation.
Native unit comparisons additionally cover both rates/receivers, all six
confirmations, seeded/unseeded paths, rank screens and CI16 extrema. An earlier
`dev_strided_v6.json` ran during a header documentation change and is explicitly
superseded; its sidecar forbids using it for qualification. Final replay verifies
all source and native binary hashes before and after execution.

Small whole-replay differences are not strong performance conclusions. The full
and partial latest variants report three and one additional positive cases,
respectively. These are unadjudicated, not proven new detections. Two-frame
scoring changes the statistic; full-aperture V2/V3 scoring preserves the original
final GLRT at identical coordinates. Same-visit oracle checks are explicitly
noncausal diagnostics, not the causal results in this table.

The important state fixes are a timing drift fitted only between independent
timing measurements, a separate fitted anchor that point checks cannot train,
and separate acquisition/scoring CFO versus physical tracking CFO. A signal may
have physical CFO beyond the scoring search range while its acquired scoring
coordinate is supported. Innovation is evaluated in physical CFO, without
clamping the residual or assuming carrier phase survives retuning.

Full-aperture development stress results:

- Clear state at offsets 16/32/48: all 36 reference positives retained.
- Wrong-channel cache over offsets 40–47: 32 injected receiver-visits, eleven
  available cache attempts, zero accepted poisoned hits; all 36 retained.
- Processing outage over offsets 24–27: sixteen receiver-visits explicitly
  unprocessed, including two offline-reference positives. All processed reference
  positives retained. Reduced coverage is ineligible for a speedup claim.

The server queue model for `dev_direct_v3.json` sums both RX costs per visit:
candidate CPU service p50/p95/p99 is 4.35/6.63/7.08 ms. At the actual saved source
arrival times there is no modeled backlog. This excludes capture/IO and does not
establish ARM real-time operation. See `review/queue_dev_direct_v3.json`.

## Rejected screening shortcuts

At thresholds selected to retain every development positive, native rank sends
222/256 receiver-visits to blind acquisition; sparse three-frame-lag coherence
sends 231/256. Their modeled whole costs are 0.767x and 0.803x baseline speed,
respectively: both are slower. Even free screening has only 1.19x/1.13x ceilings.
Neither is promoted to fresh holdout. See `scout/REPORT.md` and `scout/results.json`.

## Further acquisition and ARM preparation

`acquisition/REPORT.md` compares independent acquisition variants against the
frozen FP64 V4 baseline, with no fallback hiding losses:

| Acquisition variant | Whole CPU ratio | Reference positives retained | Decision |
| --- | ---: | ---: | --- |
| Rank-proposed timing replaces coarse search | 1.943x | 8/36 | Reject: 28 losses and failed pilot controls |
| Built-in FP32 FFT, strided unseeded acquisition | 1.393x | 36/36 | Development numerical evidence only |
| FP32 FFTW, strided unseeded acquisition | 1.505x | 36/36 | Development numerical evidence only |

Both FP32 variants preserve the eight pilot control positives and produce no
positive noise/tone controls, no additional real-data positives, and no changed
rank/window choices. Maximum matched margin drift is 6.12e-8 across the two
variants; the nearest observed complete-result margin is 0.002284 from the gate.
These observations do not prove behavior on arbitrarily near-threshold signals
or unobserved 5-MS/s real positives. See `fft32/README.md` for the numerical tests.

`cadence/REPORT.md` separately tests minimum blind-search intervals of one and
five seconds. They cover only 24/36 and 6/36 reference-positive visits, with two
and three reference-positive keys never discovered. Their unpaired descriptive
CPU ratios (2.56x and 7.84x) are not full-coverage speedups or maximum discovery-
latency guarantees. Neither cadence policy is promoted.

Native V5 adds a sample-aligned dual-RX pointer plus explicit receiver lane for
safe ARM NEON folding. Host scientific equality tests pass, and Cortex-A9
cross-compilation/disassembly verifies vector instructions. The bounded QEMU
check in `review/arm_probe/qemu.functional.json` also executes the ARM/NEON path
on one development visit and one pilot control. This is functional evidence,
not physical-target execution or speed. The ARM denominator review in
`review/ARM_BASELINE.md` distinguishes the current Standard Python analyzer,
host adaptive lane, historical ARM workers, and this research detector; timings
from those different contracts cannot be combined.

Two further bounded experiments were rejected. Transposing fractional
interpolation into pilot coefficients preserved scores to approximately 1e-15,
but rebuilding coefficients on each invocation made the kernel 4.7% slower
in the aggregate median comparison (`coeff/REPORT.md`). Fixed four/eight-center
short-GLRT CFO banks recovered only 11/36 and 22/36 reference CFOs even with
oracle timing; the eight-center bank already cost more than the fine-search
stage it sought to replace (`acquisition/GLRT_CFO_PLAN.md`). Neither used holdout.

`review/arm_probe/README.md` describes the prepared physical-ARM component
comparison: packed built-in FP64, packed FP64 FFTW, and aligned V5 FP32 FFTW.
The metadata-only plan contains four development visits and twelve controls,
with both receivers, C packing, and detector work timed. Binaries, dependencies,
and inputs are hash-pinned. No physical target has been contacted for this
experiment. This small development benchmark cannot qualify causal cache
fallback, the production scanner contract, or whole-pipeline 10x performance.

The host-side runner and strict result assessor now have component tests. The
runner binds the current successful v0.59 deployment and SSH host key, stages
saved IQ in temporary storage, enforces process/idle-slot deadlines, verifies
hashes, and preserves the existing capture schedule. The assessor rejects
partial schedules and emulator timing as physical ARM evidence. Local binding
and payload validation passed. A read-only preflight stopped **before SSH** when
the capture authority rejected admission with `operator stopped capture from
web UI`; the pause was not changed. See `review/arm_probe/PREFLIGHT.md`.

The receipt-only cross-RX review found only two positive pairs in 128 physical
visits, with physical CFO differences of 229–456 kHz. Direct cross-RX CFO reuse
does not fit these observations. `native/NEXT_EXPERIMENT.md` freezes a separate
lag-4 correlation phase proposal experiment for reducing blind fine-search
work. That experiment is now rejected: it retained 31/36 reference positives,
needed 125/256 structural fallbacks, and cost 13.5% more CPU overall (0.881x
speedup). Its 24 constructed-control decisions were unchanged. No retuning or
holdout evaluation followed; see `phase_cfo/REPORT.md`.

Two further audits found no hidden explanation for the limited cache benefit.
`review/COUNTER_TIMEBASE.md` confirms the development source-counter scale:
divide counter deltas by sample rate, without an extra factor for two receivers.
Both development captures postdate the same-radio v0.59 deployment, although
their manifests do not embed firmware/FIT identity. `review/PERIODIC_DISCOVERY.md`
confirms that accepted checks outside the drift-learning bound still advance
the periodic discovery counter. The real development replay's longest cached
streak is only three, so its receipts do not themselves exercise that limit.

## What the next 10x attempt must change

Positive caching alone cannot cover this traffic mix. Even free recovery of all
36 reference positives leaves 220 receiver-visits requiring discovery unless a
new negative decision is qualified. Cached absence or skipped processing cannot
be substituted for a fresh observation.

The measured blind-cost prefix attributes 38–40% of server outer-call cost to
packing/boundary overhead. Removing all of it has only a 1.62–1.67x ceiling;
the remaining native DSP would still need about 6x improvement for 10x overall.
This is a server-harness measurement, not a measured ARM production saving.
Within native confirmation, coarse search is the largest aggregate stage, with
fine acquisition and fractional/final scoring also substantial. Details and
exact stage receipts are in `scout/BLIND_COST_PLAN.md`.

Direct strided blind ingest now has development decision equality. The next
sequence is to measure the prepared safe ARM NEON/FP32 variants, then compare batched
CFO/timing evaluation, fused memory passes, and selective FP32 kernels one stage
at a time. A coarse-to-fine pruning scheme must use a valid upper bound if it
claims equivalent results. Shorter blind support or learned screens are new
detectors requiring their own retention/false-alarm evidence. Two-core execution
can reduce wall latency but is not a CPU-work reduction.

V4 uses scalar strided rank loads on ARM and could regress against packed NEON.
V5 implements the safe sample-aligned interface described above; integration and
target qualification remain outstanding. No server gain is projected onto ARM.

ARM precision work has a concrete motivation: the Zynq Cortex-A9 NEON unit
supports vector single-precision and scalar double-precision computation;
FP32 conversion still needs numerical qualification, rather than an assumed
speedup. See the [AMD Zynq NEON reference](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/NEON).

Before ARM qualification, freeze candidate code/configuration, native binary and
build receipt, and dataset hashes; run the fresh holdout once without retuning.
Use the existing bounded saved-IQ ARM route with lease/serial locking, before/
after idle attestation and temporary payload cleanup. No new RF capture is
needed. The 10x goal remains open.

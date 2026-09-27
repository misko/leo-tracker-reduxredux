# General compute optimization

**Latest qualification fails quality:** the original recorded holdout delivers
19.21x/19.05x CPU savings but only 37/43 and 5/6 retained receiver identities,
with two new unmatched rescue outputs at 2.5 MS/s and one lost associated visit
at 5 MS/s. See `tone_recorded_holdout/REPORT.md`. These sessions are now consumed.
The compute objective is not complete with the requested small quality loss.

The 26-case reserved constructed split is now evaluated in `tone_validation/`:
40.80x/48.17x CPU gains, all required truth gates passed, zero unassociated
positives. It does not exercise native rescue confirmation, so it cannot qualify
the 11 recorded development recoveries. This split is consumed validation;
original real holdout was subsequently evaluated as reported above. See `tone_validation/REPORT.md`.

**Latest bounded rescue result:** `native_tone_rescue/REPORT.md` reports
23.55x/21.12x aggregate CPU improvement on the same 64 recorded development
visits, with 78/79 reference receiver identities retained (baseline 67/79),
all constructed control gates passed, and no new extras from rescue. The
5 MS/s mean CPU remains 158.69 ms per 120 ms recording, with 349.59 ms wall p95;
therefore the compute target is met on development data but real-time and
held-out qualification remain outstanding. All 543 research tests and 11
subtests pass across two collection shards. Earlier results below remain
historical evidence with their original contracts.

The user clarified that the current priority is compute performance in general,
without an ARM requirement. The radio's capture-authority pause therefore does
not block this work. Previous ARM-specific stopping decisions remain historical
evidence, not restrictions on server optimization.

The latest tradeoff experiment is `native_tradeoff/`, preserving the original
TG11 native blind engine and adding actual causal two-probe tracking. Its
constructed development replay measured 94.49x/115.48x blind and
105.37x/126.60x tracked aggregate CPU speedup, with every native positive
associated to injected truth and all ten new negative receiver cases inactive.
Separate controls exercise disappearance/change and near-CFO tone replacements.
See `native_tradeoff/REPORT.md` for complete scope and limitations. This is a
different detector, and no production component has been replaced.

Its subsequent 64-visit recorded replay measured 100.06x/122.80x blind and
131.02x/167.04x tracked aggregate CPU speedup. All 56 scanner-positive visits
retained an associated detection, but only 67/79 positive receiver identities
were retained, with two additional positive visits. This is not a demonstrated
small receiver-level loss. Tracking added 1.309x/1.360x over native blind with
no additional activity/identity disagreements. The current choice is therefore
which detection/measurement coverage to preserve while spending the native
speed headroom, not whether server compute can be reduced dramatically.

The subsequent `native_candidates/` experiment tests that idea with two native
candidates per probe. It remains 67–130x faster than the application across
rates/modes, but blind retention stays 67/79 receiver identities and tracked
retention falls to 66/79 through one active identity mismatch. The expansion
is not adopted: it adds compute without recovering the original losses.
All constructed truth checks pass; frozen observations now permit diagnosis
of rejected hypotheses without another IQ campaign. See its `REPORT.md`.

`native_reference_points/` then supplied the missed application hypotheses
directly to the unchanged raw native point scorer. Strongest pairs passed for
11/12 missed receivers; a tiny numerical API support-boundary discrepancy
blocked the remaining pair. `native_guided_boundary/` subsequently qualified a
`1e-6 Hz` admission tolerance: all 41 ordinary supplied-point results were
scientifically identical, the one roundoff-boundary point became a supported
status-zero observation, and both engines produced identical decisions while
passing all 84 causal control receiver policies. The reference hypotheses were
supplied rather than discovered, so this is an API numerical fix rather than
measured end-to-end recovery. Acquired CFO stays within +/-400 kHz even when
residual-corrected physical CFO exceeds it; frequency-range arguments must
distinguish those quantities. See both diagnostic reports and the bounded
one-acquisition rescue feasibility note.

The bounded `native_rescue/` implementation then tested that acquisition path.
The tracked baseline passed all 84 original control receiver policies, while
rescue passed 82/84 after accepting two constructed 5-MS/s tones. A separate
paired original/RX-swapped audit found three false-active executions: two
repeat those original failures and one exposes a third distinct 2.5-MS/s tone
parent/receiver source hidden by fixed RX0-first selection. The five recorded
control failures therefore represent three distinct physical tone parent/RX
failures. The frozen protocol stopped before diagnostic and recorded stages.
This rejects the raw rescue path while leaving the native fast-detector baseline
and its existing measurements unchanged. See `native_rescue/REPORT.md`.

The earlier experiment is `tg11/`: a native decision detector that tries to
confirm previously acquired timing/frequency on fresh samples, with full blind
fallback and periodic discovery. The constructed-control stage passed all 84
receiver results, but all used blind acquisition. Its four-visit paired cost gate
passed at 16.03/33.15 ms CPU per dual-RX visit, while its scientific gate failed
on one additional detection relative to the current scanner. The larger replay
was not run. See `tg11/REPORT.md`; this is unqualified detector redesign evidence,
not an established equivalent-computation gain or benefit from tracking.

The follow-up point-scoring diagnostic confirms that the current Python GLRT
passes the additional real pair when given the native hypotheses; the original
application search did not retain them. A separate canonical-scoring tracker
then demonstrated four actual cached confirmations on repeated-pilot controls,
but failed its constructed science gate on tone-only inputs. This isolates a
remaining interference-rejection problem rather than a radio/ARM blocker. See
`tg11_diagnostic/REPORT.md` and `canonical_tracking/REPORT.md`. Neither experiment
is a qualified production replacement.

## Experiments

1. `server_simd/`: implement exact SIMD for the scalar CI16 ranking, coarse
   folding and nuisance correlation paths. Every signed-16 product fits int32;
   complex sums and accumulated power require widening before addition. Preserve
   scientific fields, thresholds, tie order and floating-point reductions.
   Compare complete calls against both the existing FP32 FFTW implementation
   and the original packed FP64 reference in the same run.
2. `server_parallel/`: evaluate independent receiver workspaces concurrently.
   Measure two-receiver visit latency without waiting for future visits, plus
   separate queued-batch throughput at 1/2/4/8 workers. Initialize and destroy
   FFTW plans serially. Keep per-worker buffers private and input IQ immutable.

The host is an Intel Core Ultra 9 285K with 24 physical cores. The current
sysfs CPU-type masks identify performance cores 0–7 and efficiency cores 8–23.
Record and control benchmark affinity so heterogeneous-core migration does not
masquerade as a speedup. Do not alter host-wide frequency or scheduling policy.

## Evidence and interpretation

Use the frozen 256 new-development receiver-visits, supported original controls
and the new adversarial controls as applicable to each preregistered design.
Keep the original 2-us/8-kHz association gates and expose every loss, extra,
rank change and unsupported result. No reference result enters candidate state.
Do not open the held-out recordings or modify previous scientific fixtures.

Time receiver ingress, actual detector calls and relevant dispatch overhead.
Report initialization, file loading and hashing exclusions explicitly. Serialize
independent benchmark campaigns to avoid avoidable contention, with warmups and
counterbalanced repetitions. Compare each variant with its contemporaneous
baseline; do not multiply speedups measured in separate runs.

CPU reduction, single-visit wall latency and batch throughput are distinct
results. Parallel throughput alone does not prove a 10x CPU reduction or a 10x
improvement in live adaptive-scan latency. The full 10x objective remains open.

FFTW execution permits independent concurrent plans, while other FFTW routines
must be serialized; see the [FFTW thread-safety documentation](https://www.fftw.org/fftw3_doc/Thread-safety.html).

## Completed results

The unchanged SIMD candidate passed all 320 receiver cases: exact scientific
outputs versus stable FP32, 169/169 reference positives retained, no extras and
no repeatability failures. However, its incremental CPU speedup was only
1.0006x overall (1.0041x on the 256 real recording cases). The total improvement
versus packed FP64 was 1.4128x CPU, almost entirely attributable to the existing
FP32 FFTW and strided input work. The original random-input component gate
remains failed: about 1.065x against a required 1.10x. The subsequent full-data
validation was explicitly outcome-informed and kept the candidate unchanged.
See [SIMD validation](server_simd_validation/REPORT.md).

Parallel evaluation of the unchanged stable FP32 implementation retained all
129 reference positives on the new real recordings, with exact serial FP32
scientific outputs and no extras. Eight workers reached 1,064 receiver-visits/s,
or 3.08x batch wall speedup versus packed FP64. This consumes multiple cores;
it is not a 3.08x reduction in CPU work. Two-receiver parallelism reduced median
pair latency from 3.74 to 3.17 ms but worsened p95 from 6.25 to 10.04 ms and
increased aggregate CPU by 17%. Do not promote that mode for live tail latency.
See [parallel report](server_parallel/REPORT.md).

The parallel measurements include result compaction and scientific-signature
pickling/hashing inside task timings. Their scaling limit therefore cannot be
attributed solely to native DSP or the GIL. The single-core SIMD validation
keeps signature construction outside timing; ratios across these experiments
must not be combined. No combined SIMD/parallel claim is made.

Keep stable FP32 as the measured compute improvement and treat batch parallelism
as an optional throughput mode. The new integer SIMD prototype does not justify
integration on performance grounds. A next experiment should measure the actual
production caller and its output overhead, then target its dominant acquisition
cost. These research calls confirm one ranked window; they do not establish
production end-to-end latency or a 10x improvement.

Validation: the complete research suite passes 240 tests and 11 subtests.
Duplicate test basenames were renamed for full-suite collection; frozen
benchmark runners, binaries and result files were unchanged. The three detector
binary hashes and the SIMD validation runner/result hashes match their receipts.

The next completed diagnostic is the actual repository scanner call, described
in `APPLICATION_WORKLOAD.md` and `application_profile/REPORT.md`. Its 22
acquisitions and 220 GLRT scores per selected dwell make it a materially different
workload from the native one-confirmation benchmark. Acquisition consumed
81.5%/93.0% of diagnostic CPU at 2.5/5 MS/s. The coarse grid is the largest
measured target. Timing and scientific claims must retain this workload
distinction rather than dividing the slow full-analysis baseline by the fast
one-confirmation prototype.

The complete scanner now has a measured parallel latency option: 8.20x/10.69x
at 2.5/5 MS/s using 22 workers within one dwell, with exact full responses on
two development cases. Aggregate CPU increases 43%/29%. Eight workers deliver
6.61x/7.04x with roughly 3%/2% more CPU. See `application_parallel/REPORT.md`.
Separate early-exit CPU gains are 3.874x/1.761x on positive examples and no
material reduction on zero controls. Generic short-FIR/FFT coarse alternatives
were slower. The full research suite now passes 522 tests and 11 subtests in
two collection shards because two frozen experiments share one test basename.
Broader qualification and acquisition-work reduction remain open.

# Native detector and causal tracking: development tradeoff evaluation

This is a new development experiment under the user's explicit willingness to
trade a small amount of accuracy or other metrics for 10x speed. It does not
revise the failed TG11 or canonical-tracker experiments. It measures a fixed
quality/compute comparison and does not authorize production promotion.

The preceding turn produced a reviewed option portfolio and fallback cost
budget. This turn tests the leading native architecture over more than the
four previously timed recordings and isolates actual channel reuse.

## Fixed methods

1. **Application reference:** current checkout `analyze_glrt64_dwell`, eleven
   overlapping 20 ms probes, both receivers, ten acquisition candidates.
   Enumerate every qualifying positive pair. Its search is a comparator, not
   physical truth for real recordings.
2. **Native all-blind:** unchanged frozen TG11 native engine/profile, all eleven
   windows per receiver, complete native support and fractional final scoring,
   fixed 0.025 margin and same-receiver nonoverlap/CFO pair rules. Force blind
   discovery for every visit through the new controller. This is a different
   detector and a smaller report than the application reference.
3. **Native tracked:** the same blind engine and pair rules with a causal
   two-probe guided route. Preserve the native blind path's interference
   protections. Use the last independently fitted pair's probe locations and
   predicted timing/scoring CFO. Do not compare the uncalibrated rank epoch
   with the fitted epoch. Guided point measurements operate on fresh raw IQ;
   they do not inherit blind tone removal or constitute independent timing
   fits. This distinction remains visible in the assessment.

Native tracked state is isolated by continuity/session, receiver, channel,
edge, sample rate, tuning and calibration identity. Keep two-second expiry,
31 guided accepts followed by forced discovery, and integer-first source
coordinate arithmetic. A failed point check immediately invokes full native
blind discovery on that receiver. A blind negative clears the tracked state.
Point timing is a prediction and never trains timing drift. Only fitted blind
pairs train timing/CFO rates; stale rates cannot transfer across an incompatible
new trajectory. Expected physical CFO is checked against the measured residual
estimate, not used as the reported measurement.

No margin, candidate count, window schedule, expiry or discovery cadence is
selected from this experiment's outcomes. No reference result enters state.
The current native binary is reused unchanged. Candidate-count expansion and
new coherent-timing selection rules are separate future variants.

## Fixed stages and membership

Freeze the detector, adapter, runner, this design, relevant component tests,
native binary/build sources, actual current Python/native acquisition backend,
input manifests and case membership before opening detector outcomes. Each
stage writes a separate immutable result; later-stage runners may have a new
lock but must retain the original detector and assessment hashes.

**Stage A: original constructed controls and sequences.** Use the exact 32
physical cases and ten sequence occurrences from the frozen TG11 dataset helper.
Run both native methods, both receivers. Evaluate all expected pilot/noise/tone
truth and all sequence rows. Require outputs to report actual guided, failed
guided, cold and forced routes. Prior repeated-array controls test causal
mechanics, not field cache-hit rate. No application rerun is needed in this
stage. Execution budget: 120 seconds.

**Independent cache stress diagnostic:** after Stage A, run the separate frozen
`cache_challenge_fixtures.py` inventory and challenge runner. At each rate, reuse
the existing strong zero-CFO pilot in four alternating steps, replacing it in
the intervening steps with freshly seeded white noise plus a tone at 0 Hz,
a tone at +4 kHz, and a three-tone mixture including 0 Hz. There are seven steps
per rate, 14 physical occurrences and 28 receiver results per method. The tone
amplitude is 8,000 CI16 units with noise-component sigma 300, no clipping; all
negative frequencies, weights, phases and seeds are fixed in the generator.
Pilot replays explicitly reset carrier phase and use virtual integer source
counters above 2**55, translated by whole seconds and advanced by 120 ms.
Run native blind and tracked methods and assess all true pilot pairs and every
known negative. This challenges same/near-frequency interference after a real
state establishment; it does not infer cache safety merely from tones whose
CFO is far outside the innovation gate. Its separate 120-second budget and
source lock leave all existing inventories unchanged. Generated negatives have
array hashes and construction provenance, not an inherited pilot file hash.

**Stage B: new constructed development dataset.** Use all 26 materialized
development cases in `../tg11_diagnostic/dataset/cases.json`, SHA-256
`71c8bf508a54b83fd8990e05771c592944f850059ecc4651016f4f3ecc655ef8`.
This contains 13 cases per rate, 52 receiver rows, the fixed analytic pilot-power
ladder, negative and interference controls, partial symbol-region controls and
fresh four-visit causal sequences. Run the application once and each native
method once per physical case. Keep all development cases, including the
weakest pilots and all partial-region controls. Execution budget: 300 seconds.

**Stage C: real development replay.** Use the frozen first 32 new-data visits
per rate returned by TG11 `real_cases()`: 64 physical visits and 128 receiver
rows. Process in source-time order within each session, preserving channel
keys, with empty initial state. Run the application once and each native method
once per physical visit. This is broader outcome-exposed development evidence,
not the blocked original TG11 phase-two promotion run. The user's relaxed
tradeoff preference permits measuring additions and losses rather than treating
one comparator addition as an automatic rejection. Execution budget: 300 seconds.

All stages preserve the complete fixed inventory even if scientific quality is
poor. Quality failures are reported, never filtered into a passing subset.
Integrity failures, invalid geometry, detector exceptions, changed sources or
an exceeded execution budget produce incomplete/failed evidence and stop
dependent work until diagnosed. A poor quality result does not authorize
retuning and rerunning the same frozen variant.

Both the original holdout and the new 26-case validation IQ remain unopened.
New validation arrays are not generated in this experiment. No RF, QNAP writes,
hardware access, production source changes or deployment is involved.

## Scientific assessment

For each method and receiver, record active/inactive, supporting probe pair,
actual scored epochs, scoring and measured physical CFO, exact/control scores,
margins, support/fractional status where available, routes and work counts.
Absence of a result is an error, not an inactive decision.

For constructed data, report known component presence separately from a
thresholded decision. A low-SNR injected pilot has physical presence even if
neither detector can detect it. Every active pair must be assessed against one
injected trajectory, with both members within 2 us circular timing and 8 kHz
CFO and actual injected temporal/symbol support in each nonoverlapping probe.
Use native alternating early/late support for the native statistic and early
symbols only for the current application statistic. Partial early-only and
late-only signals are separate diagnostic strata, not interchangeable full
pilots. Noise/tone/multitone false detections are known constructed false
positives. A mixed-trajectory pair is an association failure.

Report full point-scored truth association and baseline behavior for every
fixed power level; do not change amplitudes to manufacture a near-threshold
case. Explicitly state whether the fixed ladder brackets the decision boundary
at each rate. This small negative cohort does not estimate a low field
false-alarm rate precisely.

For real recordings, report per-receiver and per-visit reference positives,
retained/lost/additional decisions, and association of every native active pair
to the full application pair inventory at the original 2 us/8 kHz tolerances.
Additional pairs remain unadjudicated unless supported by separate physical
truth. Do not call them physical false positives simply because the old search
did not retain them. Inactive reference recordings are not labeled noise.
Retain both activity agreement and identity agreement; one cannot substitute
for the other. Derive denominators from this exact application replay, not the
older 129-positive one-confirmation native cohort.

Summarize measured additional misses in 0%, <=1%, <=3%, <=5%, and >5% bands
per rate, alongside all false positives/association failures. These are
comparison bands, not universal product acceptance thresholds. Report native
tracked versus native blind changes separately to expose cache-caused errors.

## Timing and interpretation

Run one campaign at a time, pinned to P-core 0, with numerical thread counts
set to one before import. Initialization, file loading and hashes are outside
the timed calls. Natural CI16 conversion, all screens, point attempts, fallback,
state work and decision assembly are inside. Rotate method order by case;
state advances once per actual case. Each method has an independent causal
controller. Do not warm or train state using reference outputs or future visits.

Stages B/C use one full call per method per case: aggregate paired CPU ratio
and observed per-case distributions are development measurements, not stable
population p95/p99 or repetitions-based microbenchmark estimates. Report CPU
and wall separately, by rate and cohort, including cold and failed-fast paths.
The target is >=10x aggregate CPU reduction at each rate against the actual
paired application calls. Also report the fraction of calls below 120 ms;
10x over a multi-second baseline is not automatically real time.

A 10x development measurement with tolerable observed loss is evidence for
the next qualification stage, not by itself achievement of the full goal.
No result inherits TG11's prior 94.53x/122.81x ratios or multiplies them by a
separate cache speedup.

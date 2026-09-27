# Track-guided decision detector: bounded design

## Decision objective and comparison

The next experiment should replace the current scanner's **decision-only** call,
`detect_first_glrt64`, with a new detector.  It should not claim to reproduce the
full `analyze_glrt64_dwell` report.  The current call evaluates eleven overlapping
20 ms probes for both receivers, retains ten acquisition candidates per probe in
the configured application, and finishes all 220 GLRT scores even after a pair has
established the decision.  The proposed detector instead returns one measured
active/inactive decision and, when active, the two fresh observations that support
it.

The comparison is therefore scientific rather than field-for-field.  It must
measure decision retention, false alarms on constructed controls, association,
discovery routes, and complete CPU cost.  Skipped full-response rows and a cached
positive are not allowed to stand in for fresh measurements.

The recent paired full-call medians are the planning denominator:

| Rate | Current decision-call CPU | Hard 10x candidate budget |
|---|---:|---:|
| 2.5 Msps | 1,434.273 ms | 143.427 ms |
| 5 Msps | 3,890.196 ms | 389.020 ms |

The implementation experiment must rerun the current call in the same paired
schedule.  These existing values set the absolute stop gate; they are not a result
for the proposed detector.

## Candidate TG11-v1

TG11-v1 uses the two natural 20 ms lattices in a 120 ms dwell: six windows starting
at 0, 20, ..., 100 ms and five starting at 10, 30, ..., 90 ms.  All coordinates are
mapped back to the common 120 ms source coordinate before matching or state updates.
Both receivers are independent detector streams.

Every visit performs a **fresh rank screen over all eleven windows** directly from
the natural CI16 layout.  The first prototype should reuse the stable FP32 FFTW
native rank statistic and its exact integer lag fold.  The screen is routing
evidence only: it cannot emit an inactive decision, refresh state, or suppress a
blind route.  This avoids turning the previously rejected sparse/rank threshold
into cached absence.

State is keyed by `(continuity epoch, receiver, channel, edge, rate, tuning
identity, calibration identity)`.  A recording `session_id` supplies the continuity
epoch for this saved-IQ experiment; live code must also reset on a source-counter or
timebase reset.  Tuning identity must distinguish retunes even when nominal channel
metadata repeats, and calibration identity must include the frequency-calibration
digest used to interpret CFO.  State contains the last independently fitted
source-coordinate frame lattice, scoring CFO, physical tracking CFO and causally
fitted rates.  Keep the existing two-second expiry and one forced blind discovery
after 31 accepted guided visits.  A point confirmation does not train timing drift.
No reference result enters state.

After the screen, route as follows:

1. **Guided route.** A live track is eligible only when at least two screened,
   non-overlapping windows have projected epochs within 4 us of the predicted
   lattice.  Evaluate those windows in chronological order at the predicted timing
   and scoring CFO with the full native exact/rolled-control statistic.  Accept a
   pair only when both observations have valid boundary support and fractional
   completion, both margins satisfy the application gate `>= 0.025`, their tracking
   CFOs are within 8 kHz of one another, and each physical-CFO innovation is within
   8 kHz.  Return the earliest such pair.  This is predicted-and-verified evidence,
   not a fresh timing fit.
2. **Fail-open blind route.** No state, expiry, periodic discovery, insufficient
   screen agreement, any failed guided check, or excessive innovation invokes the
   blind resolver.  Reuse the already computed rank data rather than screening a
   second time.  Run unseeded FP32 FFTW confirmation for every one of the eleven
   windows and retain both candidates exposed by the native confirmation result.
   Apply the same valid-support, fractional-completion, margin, same-receiver,
   non-overlap and 8 kHz pair rules in chronological order.  A blind negative is a
   fresh eleven-window result; a screen by itself is never a negative.
3. **State update.** Establish or refit a track only from a fitted blind pair.
   Successful guided pairs may advance the accepted-hit/forced-discovery counter
   and the last-seen time, but must preserve the independent fitted anchor and
   slopes.  A failed route never refreshes state and never emits the previous
   positive.

The blind resolver deliberately has a smaller candidate inventory than the Python
application's ten candidates per probe.  It is a new detector whose adequacy is
decided by the gates below.  It must not be described as an exact acceleration of
the 220-score report.

## Why the cost target is plausible

The older common-profile stage receipt measured one native rank plus one
confirmation per receiver at 0.952/2.013 ms for 2.5/5 Msps.  Its per-receiver rank
was 0.267/0.509 ms and confirmation was 0.683/1.493 ms.  A deliberately conservative
linear planning proxy for two ranks plus eleven confirmations is therefore about
8.05/17.44 ms per receiver, or 16.1/34.9 ms for both receivers.  A guided visit with
two confirmations is about 3.8/8.0 ms for both receivers by the same arithmetic.

Those numbers are not a TG11 benchmark.  They come from a different frozen native
experiment, omit the new wrapper/state work, assume repeated-confirmation costs add
linearly, and do not establish the new detector's science.  They do show enough
headroom to justify one implementation: even a fivefold error in the all-blind
proxy remains below the 143/389 ms application budgets.  The experiment does not
depend on a high cache-hit fraction to be computationally plausible.

Time the complete natural-CI16-to-decision call.  Count both receivers, all screens,
guided attempts, failed attempts, blind confirmations, state work and source-coordinate
mapping.  Initialization, input file loading and hash verification stay outside both
methods.  Report CPU and wall separately; parallel receiver work may improve wall
latency but is not CPU speedup.

## Frozen development experiment

Use no holdout.  Select the first 32 manifest-ordered visits at each rate from
`new_data/cases.json`, both receivers included.  This is 64 physical visits and 128
receiver streams; the metadata rule is fixed without consulting the new application
baseline outcomes.  It remains outcome-exposed development evidence.

This real prefix does **not** exercise the forced-discovery interval.  At 2.5 Msps,
the per-session/channel/edge counts are 9, 10, 7 and 6 visits for channels 1--4;
at 5 Msps they are 4, 14, 8 and 6.  Each count applies separately to RX0 and RX1,
so the largest actual cache key sees only 14 visits.  The manifest does not expose a
separate tuning/calibration digest; the replay must bind the fixed recording identity
as a dataset adapter and must not infer that live retune or calibration continuity
has been tested.

Use the current application with ten candidates as the real-IQ comparator.  Run it
once per case for scientific inventory.  For timing, preregister two metadata-selected
cases per rate, one warmup per method and three counterbalanced repetitions.  Advance
causal state once per visit; repeated kernel timing must not advance it.  Freeze code,
configuration, dataset membership and source hashes before running either detector.

Run all 2.5/5 Msps cases in the existing `lag3_controls` set and the existing
pilot/noise/tone controls.  The former includes continuous CFO, fractional timing,
off-grid timing, strong-tone interference and two-pilot mixtures.  Build three
deterministic causal sequences from those already frozen arrays without changing
samples: quiet-to-pilot appearance, established-pilot dropout followed by noise/tone,
and an established pilot followed by a different timing/CFO pilot.  Sequence order
and counter gaps must be frozen before evaluation.

The older pilot controls contain a finite 15-frame injection inside one 20 ms
segment rather than a full-dwell pilot.  Their expected active pair must therefore
use two nonoverlapping natural probes that each contain at least two actually
injected frame starts with complete GLRT symbols 2..65.  The frozen geometry does
provide exactly one such nonoverlapping pair: probe indexes 1 and 3 for the lower
controls and 7 and 9 for the upper controls, with about eight and seven supported
frames respectively.  Circular timing agreement alone must not extrapolate these
finite injections into another probe.  The `lag3_controls` pilots remain
full-dwell injections, subject to the same per-probe injected-support check.  This
amendment is derived from the frozen generators and arrays before any TG11 saved-IQ
outcome is opened.

Exercise periodic discovery separately with a deterministic state-machine sequence
for one complete cache key: one fitted blind establishment followed by 31 accepted
guided observations, then require the next visit to route blind before any guided
measurement.  This constructed sequence tests counter semantics only; repeated or
synthetic observations do not contribute sensitivity, cache-hit-rate or speed
evidence.  Parallel key-isolation cases must change each of continuity epoch,
receiver, channel, edge, rate, tuning identity and calibration identity and verify
that no state is reused across the change.

## Scientific and route gates

Construct the comparator's positive-pair inventory from its full probe responses.
A pair requires two passing candidates from the same receiver, probe starts at least
20 ms apart and tracking CFOs within 8 kHz.  Map epochs to the common dwell coordinate.

TG11-v1 advances only if all of these hold:

- every comparator-active real visit remains active;
- every TG11 active pair on a real visit associates to one comparator pair on the
  same receiver, with each member within 2 us circular timing and 8 kHz tracking CFO;
- no comparator-inactive real visit becomes active; this conservative comparator
  gate is not a claim that the real visit is physical noise;
- every single-pilot constructed receiver is active and associates to injected truth
  within 2 us/8 kHz; every two-pilot receiver associates to at least one injected
  trajectory, with the chosen trajectory reported;
- every noise-only and tone-only receiver remains inactive, and pilot-plus-strong-tone
  cases retain an injected association;
- the wrong-track sequence routes blind and finds the current injected pilot, the
  dropout sequence emits no stale active result, and the quiet-to-pilot sequence
  discovers the pilot on its first pilot-bearing visit;
- the constructed 32-visit cadence cycle forces discovery at the declared
  boundary, and every cache-key dimension isolates or resets state;
- every physical visit has a measured active or inactive result.  Unknown, skipped and
  cached-absence rows fail the experiment rather than improving its speed ratio.

Report comparator positives, retained/lost/additional decisions, pair associations,
selected receiver/window/CFO/timing, guided attempts and accepts, blind routes,
fractional-incomplete and unsupported candidates, expiry, forced discovery and state
resets.  Real comparator negatives do not establish a field false-alarm rate; the
constructed controls are the only false-alarm evidence in this experiment.

## Performance gates and stopping rule

The complete paired median CPU speedup must be at least 10x **at each rate**, and the
candidate's median CPU must also remain below 143.427/389.020 ms respectively.  Require
source and input hashes unchanged, exact repeat decisions, and no non-finite timing.
Report p50/p95 wall latency and the original source-counter queue model, but do not
substitute throughput or parallel speedup for CPU reduction.

Stop after this one fixed configuration.  Any scientific gate failure rejects
TG11-v1 without threshold, window-count, cache-policy or association retuning.  Any
cost failure stops before broader replay.  A later variant would need a new design and
source freeze; the unopened holdout remains untouched.

## Prior experiments this does not repeat

| Earlier result | Why TG11-v1 is different |
|---|---|
| Rank/sparse scouts routed 87--90% of visits and became slower | The screen never declares absence; the blind resolver itself is the proposed low-cost decision detector. |
| Rank-proposed timing retained 8/36 | A screen proposal is not accepted as timing; guided checks fail open to unseeded confirmation. |
| Lag-3 and lag-4 phase proposals had timing/CFO alias failures | TG11 uses the existing native unseeded acquisition and exact/control final statistic, with no differential-phase CFO shortcut. |
| One/five-second cadence achieved speed by leaving visits unknown | TG11 returns a fresh decision on every visit and screens all eleven windows. |
| Three-track caching was slower and mismatched 11/129 identities | TG11 keeps one fitted track, checks at most one guided identity, and routes ambiguity to blind discovery. |
| Existing cache hit checks mismatched 9/129 top identities | Association is evaluated against the comparator's full positive-pair inventory; two unresolved or unsupported identities still fail. |
| Full timing-by-CFO ambiguity surface was computationally infeasible | TG11 evaluates eleven bounded native windows, not a 26--52 million-cell visit grid. |
| Compact GLRT workspace gave only 1.051x/0.999x | TG11 removes most Python acquisitions and confirmations for the decision objective instead of optimizing a minority workspace. |

Passing this experiment would establish a development result for the scanner's
decision objective on general server compute.  It would not reproduce the public
full-analysis report, prove physical signal identity, establish a field false-alarm
rate, qualify ARM behavior, or complete the original objective on an untouched
holdout.

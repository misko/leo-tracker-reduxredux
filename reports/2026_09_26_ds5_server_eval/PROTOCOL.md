# Server-first DS5 acceleration evaluation

Frozen design before worker validation outcomes, 2026-09-26.

## Objective and scope

Find a quality/compute frontier for a future ARM implementation. Run bounded
server experiments on saved DS5 IQ before spending time on ARM integration.
The current server is x86; measured speedups do not establish ARM timing.
No new RF collection, production changes, threshold weakening, golden fixture
updates or changes to historical public contracts are authorized by this plan.

Three SOL workers own dataset construction, search/proposal experiments and
decision-band experiments. Root owns integration, common scoring, evaluation
review and the final held-out run. All implementation is research-only here.

## Dataset and split policy

Freeze source-manifest hash, session assignments, exact counters, raw-IQ hashes,
selection rule and synthetic seeds before scoring. Keep both receivers and all
visits from a session together; prevent source overlap across development,
validation and holdout. Include all four DS5 rates and consecutive visit blocks
to preserve actual arrivals. Cases selected without detector outcomes must not
be replaced merely because they are quiet or difficult. The two sessions used
by the previous speed probe are development-only. Existing retrospective DS5
research means this is held out from this acceleration experiment, not a claim
that nobody has ever studied these sessions.

Target 96 real 120-ms dual-receiver visits: 8 visits per rate per split. Audit
actual channel/edge/receiver coverage after extraction and disclose missing
strata; do not infer coverage from rate labels alone. Dataset builder may
adjust selection metadata to cover edges before detector outputs are opened.
Keep a finite set of deterministic noise/tone/known-pilot controls distinct
from real observations. Synthetic truth is limited to what was injected; a
miss from the reference detector does not label real data as noise.

This small first-stage suite screens ideas; it cannot estimate rare false alarms,
full-pass tracking continuity or deployment p99 reliably. Expand a separately
versioned suite only when a measured gap justifies it. Saved arrivals can test
scheduling over recorded visits, not hypothetical retunes to unrecorded RF.

## Staged procedure

1. Unit-test numerical geometry, sample-rate mapping, alias suppression and
   queue/metric semantics. Verify archive hashes on extraction, then local IQ
   hashes on loading. Native ABI/build identity is recorded.
2. Explore bounded configurations on development only. Each worker freezes
   explicit parameters, source/build hashes and expected semantics before
   opening validation outcomes. Avoid broad sweeps.
3. Run validation without tuning. Separate numerical equivalence variants from
   science-changing variants. A failed configuration remains in the report.
4. Root reviews coverage and fidelity, then freezes source/configuration and
   runs a single final held-out evaluation of predeclared variants. No tuning
   after holdout. Bugs invalidate affected evidence; record a new version and
   the fact that the old holdout has now been seen.
5. Repeat finalist timings serially after parallel worker activity ends. Warm
   plans/buffers before measurements; take at least three repetitions. Preserve
   raw CPU and wall timings, server/load identity and preprocessing costs.
   Report initialization separately. A tiny empirical upper quantile is not an
   established p99 bound.

## Metrics and decision rules

- Reference-positive means fractional confirmation completed and exact-minus-
  control margin >0.025, the current research comparator. Keep raw scores.
- Count a retained reference-positive case only if a proposed positive matches
  the same observation window, CFO within 8 kHz and circular pilot timing within
  2 microseconds in common source coordinates. These existing diagnostic
  association tolerances do not establish physical identity. Multiple-reference
  candidate inventories additionally need per-candidate recall, not only a
  per-case best-match score. Different windows require trajectory association.
- Report lost/matched/additional positives, unknowns, timing/CFO/margin changes,
  coverage by rate/receiver/edge/session, and synthetic known-positive/control
  behavior. Additional real positives are not automatically false alarms.
- Unsupported rates or errors are explicit unprocessed cases, not silent skips,
  negatives or denominator reductions. Full-rate 7.5/10-MS/s quality claims need
  a matched-rate oracle; otherwise report throughput/fidelity only.
- Report paired service CPU/wall time including filter/conversion and fallback.
  Costs from early failure are not equal-work acceleration. Preserve input hashes.
- Replay chronological original source arrivals with two receiver costs summed
  per visit. Include 120-ms collection time in completion age. Report queue age,
  backlogs, unknown/unprocessed coverage and per-target revisit behavior.
  Extrapolated speed factors are labeled scenarios, not ARM measurements.
- First-stage promotion requires no unexplained loss of reference positives,
  no new synthetic-control detections, correct geometry, complete accounting,
  and a measured compute benefit. Any failure blocks an ARM recommendation for
  that configuration. Passing a small suite only earns larger validation.

The provisional hardware goal remains combined service under 100 ms p99 per
dual-receiver visit with capture headroom. Only a later short, saved-IQ replay
on identified ARM hardware under representative capture load can verify it.

## Integration clarifications recorded during development

The two native build helpers use different detector profiles. Search experiments
use the earlier native-tone-CI16 profile; decision-band experiments use the
decimated-replay profile, which additionally enables hybrid/amplitude-weighted
ranking, symbol diversity and energy-support flags. Their baseline detections
differ even on identical development IQ. Each experiment must compare against
its own unchanged baseline. Never pool their positive denominators or rank
their absolute timings as a common-detector competition. A later shared-profile
comparison requires a new explicit experiment version.

The final dataset is 96 real visits plus 24 synthetic controls in a separate
`control` split, crossing all four rates, two edges and three control kinds.
Controls are shared diagnostic smoke inputs, not held-out truth validation.
Final cases.json SHA-256:
`ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48`.
Before this final freeze, development ran briefly against an otherwise identical
manifest with an older embedded builder hash; validation was not opened. That
metadata revision must remain disclosed in the search experiment receipt/report.

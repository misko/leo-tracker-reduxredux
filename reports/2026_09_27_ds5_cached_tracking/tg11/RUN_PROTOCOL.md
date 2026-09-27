# TG11 staged development evaluation

The prior goal turn made progress: it measured complete scanner latency using
parallel probes and exact decision-only early exit. It did not establish a
general 10x reduction in computation. This experiment tests the new decision
detector described in `../application_coarse_alternatives/TRACK_GUIDED_DESIGN.md`.
It does not replace the full-report comparison or reinterpret old native
one-confirmation gains as application-equivalent results.

Freeze implementation, native build receipt, dataset membership, route policy,
association rules and this protocol before evaluating saved IQ. Use the current
checkout's scanner sources as application comparator, with ten candidates,
eleven probes and both receivers. No reference observation may train state.

## Execution order

1. Component and mocked causal-state tests: numerical port equivalence, bounds,
   source-coordinate mapping, key isolation, expiry, forced discovery, no stale
   positive and no repeated-timing state advancement. These do not establish
   sensitivity or corpus performance.
2. Constructed scientific controls: all 24 supported original control receivers
   and 40 adversarial control receivers, plus the frozen appearance/dropout/
   changed-pilot sequences. Evaluate the complete fixed control inventory even
   if an individual case fails, then stop before real replay if any declared
   scientific gate fails. A failed candidate's observations and routes remain
   in the receipt. No threshold or policy tuning in this experiment.
3. Bounded paired cost gate on the first two manifest-selected physical visits
   per rate. Use one warmup and three counterbalanced repetitions, comparing
   complete CI16-to-decision CPU and wall with the unchanged application.
   Clone the causal pre-visit state for each repetition; commit state once per
   actual visit. Timing repeats are not new observations. Require both declared
   per-rate absolute budgets and at least 10x paired CPU speedup before broader
   replay. This is outcome-exposed development timing, not a held-out test.
4. If earlier gates pass, evaluate the fixed first 32 visits at each rate in
   chronological order, fresh state at each session boundary. Run the complete
   application comparator once per visit and compare against its full positive
   pair inventory. Preserve losses, extra decisions, pair associations and every
   route. This stage has a 300-second execution budget and emits per-visit
   progress; earlier stages each have a 120-second budget. These are short
   saved-IQ runs, never RF campaigns. An exceeded budget records incomplete
   evidence, not a passing subset.

Initialization, dataset loading and source/input hashing are excluded from both
timed detector calls. Conversion, screens, failed guided attempts, all blind
fallback, state work and decision assembly are included. Scalar CPU and wall
measurements remain separate from the earlier parallel-worker results.

All frozen real visits remain development evidence, and the original holdout
stays unopened. Passing these gates would justify a separate qualification
stage; it would not by itself establish a deployed 10x result, full-report
equivalence, physical identity, or a field false-alarm rate.

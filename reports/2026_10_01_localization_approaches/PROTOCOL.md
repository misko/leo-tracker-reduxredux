# Admitted-approach comparison protocol

This is a new prospective regression experiment over the exact 64 recordings
in plans/localization-approaches-2026-10-01/benchmark.json. Historical reports,
failed development versions, and their seals remain immutable. Development
scans are not independent validation; reference positions never enter fitting.

## Common acquisition budget revision, before benchmark freeze

The original 40-second acquisition sub-budget failed on development stress
scan DS11-F087 before any fit, despite the much cheaper new hard optimizer.
The official experiment uses a **50-second common acquisition sub-budget**,
with the same deterministic 1,024-point disk grid, eight refined basins, and
three initial fit seeds. No spatial or nuisance prior, sample selection,
likelihood, derivative step, or acceptance threshold changes. This is an
explicit common scheduling revision, not a retroactive repair of the failed
40-second run. Apply it to every admitted arm and the matched control.

Primary external runtime remains 90 seconds; internal fit deadline 85 seconds.
Unresolved primary winners may receive one separately sealed continuation,
at most 90 additional seconds and 180 cumulative. Each stage has at most 24
iterations per seed; no third-stage polish. Pending seeds remain explicit
and are eligible for the continuation. Choose the lowest objective over all
attempted seeds, including unresolved winners. Completed acquisition is part
of each official arm's own measured end-to-end time.

The original solver is replayed under the common 50-second acquisition setting
on the development smoke panel for a contemporaneous timing control. Earlier
40-second pilot timings remain separately labeled. Identical completed seeds
are checked across arms; no method inherits a posterior, fitted nuisance state,
or uncharged acquisition from another method.

## Scientific configuration

- Same 22 DS9 / 21 DS10 / 21 DS11 recordings and retained physical observations.
- Independent uniform 250 km Sacramento map-disk prior on every recording.
- Fixed 30.48 m MSL height, with the pinned NOAA GEOID18 conversion at candidates.
- Same causal, source-bound catalogue and extended orbit banks; no propagation,
  raw-IQ reprocessing, or RF collection.
- Clock σ=1 s, receiver drifts σ=0.5 Hz/s, satellite epochs σ=0.5 s.
- Normalized Student-t ν=4 for signal and background; original covariance
  matrices remain scale matrices, so covariance is twice scale.
- A1 preserves hard joint objective, stopping rules, and iteration caps, with
  selected mean-only scoring and selected-satellite derivatives.
- B1 uses the full soft log-sum-exp objective. Every numerically positive
  satellite responsibility contributes to the derivative; no top-k truncation
  or renormalization. Compact Jacobians and local normal-block assembly are
  computational changes checked against dense/frozen numerical oracles.
- C1 is a development control. Its three equivalent solutions were slower
  than A1 and do not justify a full-panel run. D1 remains deferred under the
  predeclared acquisition/uncertainty gate.

## Execution and reporting

Before official runs, freeze code/config hashes and pilot admission decisions
in FREEZE.json. Use explicit batches of at most eight units and at most two
simultaneous fits, each with one numerical thread. No command launches the full
multi-arm campaign automatically. Rotate admitted arm order by block and review
each arm-batch before the next launch. Continuations are explicit separate
status-selected batches. Keep source snapshots, native and supervisor seals,
not-started seed slots, exceptions, and timeout receipts.

The independent auditor verifies seals, session/observation/source bindings,
support, original priors, initialization, parent lineage, and cumulative budgets
before the evaluator reads the pinned roof reference. Reports contain all 64
units per arm, including not-run, failed, and unresolved outcomes. Show both
primary and two-stage completion, error in meters, failure-inclusive ECDFs,
paired errors, runtime, and per-dataset summaries. No calibrated posterior or
satellite-identity accuracy claim is made.

Runtime counters distinguish scalar predictor requests from B1 bulk derivative
work; zero scalar-Jacobian requests does not mean zero derivatives. End-to-end
time is the authoritative performance measure. If a full-gradient soft method
fails its bounded stress/runtime gates, preserve that result and stop its
expansion rather than silently replace it with an unvalidated truncated method.

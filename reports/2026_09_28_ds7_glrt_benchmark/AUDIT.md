# DS7 local-fallback and runner audit

This is a source-level and metadata audit of the frozen `methods.py` and
`run.py` while `run-01` remains incomplete. It does not assess numerical
outcomes or tune any method.

## Causality and state

`local_fallback` creates one stateful object per method and repeat. It receives
only the current IQ/context plus its own earlier results; no reference result
is passed into the method. The runner processes input rows in frozen source
order, and each local-fallback invocation occurs once per visit, after that
method's earlier visits. A session change clears state, and a new repeat creates
new workers.

The prior key is `(target_index, rate_hz, receiver_id)` within the active
session. A prior is eligible only if its visit index and source counter advance,
and its source-counter age is at most three seconds. In the frozen inputs, each
repeated `(session, rate, target_index)` counter gap is at most 3,304,246
samples: 1.322 s at 2.5 MS/s. The remaining rates have shorter gaps. Thus the
age gate is not being bypassed by this cohort.

The key does not include target content, edge, actual LO, or IF offset. The
frozen input maps each `(session, rate, target_index)` to one stable target and
LO tuple, so this does not mix targets in this run. It limits any claim beyond
this fixed mapping; a changed target-index mapping would need an explicit state
reset or a richer key.

## Fresh confirmation and fallback

`_confirmed_tracking_cfo_by_receiver` applies the scanner's margin,
non-overlap, and 8 kHz CFO condition over the complete returned probe set. It
stores the later hit's CFO for every valid pair, leaving the last such hit for
each receiver. This is causal and does not reuse a prior decision, but it is not
necessarily `analysis.first`, a unique physical track, or the highest-margin
track. Its selection can depend on response/candidate order when several
branches are simultaneously pair-compatible.

During a local attempt, every seeded receiver must make a new confirmation. If
any seeded receiver is missing, the method reruns the entire dwell blind,
returns only the blind analysis, and updates state only from that blind result.
Receivers without an eligible prior are blind-searched during the first pass.
The row diagnostics expose the route, detector-call count, seeded/fresh/missing
receivers, and local versus blind receiver-acquisition calls. The runner starts
the timer before CI16 conversion and method invocation, so both attempts are
included in CPU and wall timing; result serialization occurs afterwards.

## Timing and scope

The timer deliberately excludes input hashing/loading, JSON serialization, and
the separately reported method-construction CPU. It includes resident CI16
conversion, acquisition, GLRT, fallback work, and diagnostics made inside the
method. CPU time is process CPU time and the serial runner pins itself to CPU0.
Method order rotates within a visit, while immutable Python/library caches may
remain warm as documented. The experiment therefore measures the stated
resident-detector scope, not storage or full Standard-pipeline latency.

## Dependency attestation

`run-01/run.json` directly seals `methods.py`, `run.py`, detector/models,
current acquisition/pilot sources, and the two original baseline files. All
eight direct hashes match the files at this audit. That seal does not cover the
transitive Starlink sources, templates, or the loaded native acquisition binary.

`runtime-lock.json` is a supplementary *current-state* attestation: it hashes
all `src/leo/analysis/starlink/*.py` files, the native acquisition module at its
actual loaded path, the direct runner dependencies, plan, and inputs; it also
records Python, platform, and NumPy versions. It was made during `run-01` and
cannot prove that these files were unchanged before its creation. Any final
report should retain that distinction and report the run-header seal as
direct-source only.

## Validation and limits

The focused synthetic method and runner tests passed: `13 passed in 0.86s`.
This audit does not claim oracle truth, physical false-alarm rate, independent
holdout performance, or generalization beyond the exposed DS7 replay cohort.

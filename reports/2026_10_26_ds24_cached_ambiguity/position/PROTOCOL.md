# Exact cached ambiguity position implementation

Scientific law, source and gates are unchanged from the previous position
pilot. Preserve DS24-0011's whole20 native IDs, all8 candidates, GL16/32/64
nodes on every bank interpolation piece, original causal conditioned Student
prior, nominal LOS zero likelihood, full3 phase-dependent physical modes,
9uniform aliases, proper fixed graph-frequency unknown and class mass0.5.
No pruning, node reduction, covariance approximation or prior tuning.

Cache ONLY exact original paired_phase_states nominal position/velocity and
3mode position/velocity at each fixed phase node. Persist read-only float64
NPY, keyed by hashes of both complete banks, native times/IDs, exact phase
nodes, RF and geometry implementations. Approximately2.07GB is local-only,
memory-mapped read-only by the two workers. Receiver ECEF/ENU, look_angles,
frequency and mode-gradient projection recompute at EVERY requested position.
Original positive_costs, alias sum and quadrature weights remain unchanged.
Current raw/C/Gamma/parent coefficient caches belong to each Target instance;
the original outer phase refresh creates a fresh instance. They never enter
the persistent satellite-state cache.

Freeze preparation source/inputs and thresholds BEFORE measuring. Geometry
absolute errors frequency/B<=2e-8Hz and elevation<=2e-11deg; normalized target
objective difference<=1e-6, finite-difference gradient error<=1e-5objective/km
with h=.01km. Controls are the SAME old3 probes plus exactly five regional
points(0,0),(-10,-10),(-10,+10),(+10,-10),(+10,+10)km. All80 point/offset-arm
mixture scores retain all8 candidates. Every candidate/node geometry is
compared at all8 centers once, since it is arm-independent; q and actual
conditionals are tested in both arms. At old3 probes also compare32/64 scores.
Save timings from actual old/cached calls, not a separate profiling rerun.
Actual cross-round tests require changed parent covariance, exact fresh
original component replay and identical satellite keys. Failure or the fixed
240-second preparation cap blocks fits; no rule/tolerance adjustment or retry.

After passed preparation/owned tests and exact B preflight, run the SAME six
slots: no-addition, fixed hard58175, full mixture; c0/fitted arms share native
observations/nominees/other priors/zero starts/25km box. The unchanged original
five outer phase-refresh rounds and48-iteration GN helper have the SAME60s
per-method fit cap. Reuse original parent-only reference updates, unchanged
scalar NLL addition and original residual/ELBO normalization offset. Endpoint
GL16/32/64 and finite-difference checks remain the previous unchanged checks.
Raw endpoint precedes gates/numerical qualification. No-addition and hard
must reproduce prior completed endpoints within1m and parentELBO1e-3, chosen
before values. Report failures and all6 denominator slots without replacement.

600 cumulative worker-seconds INCLUDING preparation/tests/hash verification;
at most2 workers, BLAS1. Each arm gets half the remaining budget. Cache
construction is a new exact implementation, not an extension of the previous
timed-out fit. No scientific retry or cap extension. Keep original source
conditional/profile/ownership and completeaccepted-ID preservation rules.
This one-owner source remains unqualified and operational policy always
retains the exact original reference. No GPS until immutable RF seal, B
terminal audit and explicit root geographic release. No newRF/position prior.

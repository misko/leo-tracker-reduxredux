# Next larger target: independent joint calibration fits

This is an experiment plan, not an integrated optimization or a measured gain.
Finish the endpoint-reuse checkpoint comparison first. Do not stack the rejected
scalar-only path or change likelihood arithmetic.

## Evidence for choosing this target

The owned recovery controller's `joint_experiment` runs each method in the order
fit c=0, audit c=0, fit fitted-c, audit fitted-c. The fits have distinct local
problems and share the same frozen observations, probe and model. They start
independently at the regional origin; one arm's endpoint is not the other's seed.

The earlier [numerical profile](../2026_11_06_algo07v3_joint_phase_lu/numerical-stages.md)
records 42.442 s and 39.712 s for the two joint fits, 7.901/7.850 s for factorized
fits and 4.383/4.675 s for controls. These historical profiled times locate a
larger opportunity than a single endpoint integral. Their sum/minimum is not a
predicted current speedup: the owned LU backend and shared-host conditions have
changed since that profile. Measure the current implementation at one common
native checkpoint before integrating anything.

## Proposed experiment

1. Capture the first actual predictive joint-fit checkpoint on DS26-0102.
   Compare serial c=0/fitted-c fits with two ordered process tasks forked from
   the same checkpoint, retaining both complete results and policy receipts.
   Repeat in opposite orders, then exercise the actual numerical route.
   Use one BLAS thread per process and the existing three-slot allocation.
2. Keep audits outside that two-task operation. Wait for both fitting children
   to exit before running the existing three-batch audit. This prevents nested
   workers from exceeding the allocation. Do not combine whole-arm concurrency
   with concurrently active audit pools.
3. If exact and faster, integrate a narrow execution port for the fit pair.
   Deliver c=0, audit c=0, fitted-c, audit fitted-c in the original order.
   The fitted-c result may be computed early, but its numerical receipt must be
   applied only at its original fit boundary. Ordinary `map_calibration_arms`
   eagerly merges both fit receipts and would reorder the intervening audit's
   reference update; it cannot simply be dropped into this loop unchanged.
4. Validate only append-only deltas from the owned `NumericalPolicy`: immutable
   configuration and receipt prefixes, integer problem-count increments,
   ordered optimizer calls and reference updates. Custom policies/factories
   retain serial behavior. Do not infer independence from equal final scores.
5. Component tests must cover the interleaved receipt order, both methods of
   optimization, all three control/factorized/joint methods, reversed child
   completion order, mutation, incomplete transport and child failure. An
   incomplete pair must not become a scientific rejection or a partial result.
6. Run fresh full native baseline/candidate comparisons on active-joint
   DS26-0102 and an inactive control, with matched inputs, budgets and both
   calibration arms. Require all scientific audits, ownership, histories,
   public grid/path and eight PNGs to remain exact. Preserve stage order,
   stage failures and admission semantics; qualify any ordinary-clock behavior
   separately from the all-work validation policy.

If component clocks improve but complete native time or CPU worsens, keep that
regression and do not promote on a favorable local measurement alone. Existing
audit batching already demonstrates why this distinction is necessary.

## Secondary opportunity

The endpoint-reuse baseline call trace has repeated complete result hashes.
The corrected probe additionally binds every kernel input and contraction mode.
Use those to measure the incidence and cost of exact repeats before proposing
an input-keyed cache. Equal output hashes or equal coordinates are insufficient
dependencies for reuse. Hashing cost, memory, private returned values and cache
invalidation must be included in any later fit-level comparison. This remains
secondary to measuring independent fit concurrency.

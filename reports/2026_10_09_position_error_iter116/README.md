# Fixed-bank search adapter: synthetic-only preparation

This is an unfrozen implementation of the
[iteration 113 queue-score comparison](../2026_10_09_position_error_iter113/SEARCH_COMPARISON_DRAFT.md)
using the [iteration 114 scorer](../2026_10_09_position_error_iter114/README.md).
No recording input, recording objective evaluation, numerical fit, new collection,
protocol freeze, production edit, commit or push was performed for this work.

## Implemented boundary

[adapter.py](adapter.py) contains three small layers:

1. `rescore` accepts only the ordinary coarse `Hard60Objective`, its fitted
   physical vector, a whole-prior bank and the expected native objective.
   It checks satellite IDs, exact old position/velocity nodes, time support,
   physical timing transport, and native-objective agreement within 1e-6.
   Receiver baseline/design terms and timing priors remain unchanged. Streamed
   predictions for old satellites must reproduce their original values within
   1e-9 Hz and identical visibility. Every whole-bank column is supplied once.
   It returns native, normalization-only and whole-bank scores separately.
2. `PointEvaluator` calls the unchanged production bootstrap and fixed-position
   fitter. Bootstrap seeds are shared by coordinate between both c arms; fits
   receive copies. Each fit uses 5 seconds, 200 iterations and the hard ±60 Hz/s
   receiver-slope bound. The zero-c arm must return exactly c=0, and neither arm
   may move position. Failed independent convergence remains in the native fit
   receipt; as in ordinary coarse search, the finite score is not silently
   removed from queue ranking. No new qualification policy is introduced.
3. `search_pair` invokes the existing hierarchy twice with the same ordinary
   40 km initial lattice, 40/20/10/5 km levels, 400-point cap and edge policy.
   Only the scalar queue/retention score changes. Both policies share exact
   point-arm evaluations in memory. Call separately for fitted-c and zero-c;
   all c arms use identical observations, native banks, priors and fit budgets.

Native bank selection and fitting still depend on each candidate location.
Added whole-bank satellites receive zero relative timing and the fitted common
shift, with no new optimized state. This is a **restricted plug-in rescore**,
not a common-bank refit or a marginal likelihood over missing satellite timing.
No known/reference coordinates or evaluation errors are adapter inputs.

## Checks and execution limitations

[test_adapter.py](test_adapter.py) uses synthetic observation/bank contracts,
deterministic fake propagation, and injected fake fitting only. Tests cover
dense score parity at batch sizes 1/3/64, actual receiver/timing composition,
unchanged penalties, mismatched model states/objectives, shared starts,
RF locks, fixed-position/budget options, and a scalar-score intervention that
changes refinement while preserving initial points and total point budgets.
Numerical parity assertions use `rel=0` explicitly. No position optimizer runs
in these tests.

[driver.py](driver.py) now provides a durable `run_slice` API, still without a
recording CLI or frozen plan. It verifies declared source/input file hashes and
reconstructed observation/prior/full-bank digests before inference. Atomic
append-only claims and result files bind every bootstrap and point-arm attempt
to the plan digest. Successful and failed receipts are reused; a claimed process
crash without a receipt blocks automatic retry. Seeds persist across arms and
slices, rather than being regenerated with a new wall-clock stopping time.

The fitted-c native search must match every frozen baseline coordinate, spacing
and score within absolute 1e-6 before candidate search. A fresh 5-second native
fit can stop differently from an archived one: the gate is deliberately strict
and must not be waived. An execution preparation may need verified original
coarse receipts to reproduce the archive; **import of those receipts is not yet
implemented**. No current plan is ready to launch.

The driver budgets at most 12 total claimed slices across all four searches,
with 500 seconds per slice and cumulative elapsed accounting toward 6,000
seconds. It checks deadlines around staged work and replay. These are **soft
between-operation deadlines**: loading, a fit or propagation can overrun; actual
elapsed time is persisted and deducted on resume, never reset. It does not kill
an operation at a hard 500/6,000-second boundary. Point failures remain cached,
may yield sentinel scores to finish coverage, and force terminal `incomplete`
rather than successful completion. Unfinished traces at the aggregate cap are
`budget-exhausted`; input/parity/binding errors are explicit failures.

[traced_search.py](traced_search.py) is a research copy of the production heap
policy with an event observer. It retains queue pops, parent/child links,
evaluations, fit convergence/failure, final score ranks and **actual deferred
cell coordinates**. Six synthetic cases verify exact production evaluation
ordering, scores and deferred counts, including flat-score ties and edge cells.
Trace events are append-only and compared exactly during replay. This avoids
claiming that production's summary-only search result exposes deferred geometry.

[corpus_port.py](corpus_port.py) is a narrow callable adapter to the existing
verified [iteration 105 whole-prior loader](../2026_10_09_position_error_iter105/run.py).
It requires an explicitly hashed, sanitized public document and an exact loader
source binding, rejects reference/error fields, and checks returned evidence.
It does not enumerate or open recordings until explicitly called. Full dependency
closure, sanitized documents, whole-bank identities and baseline trace bindings
still need a separately reviewed preparation/freezer; checking a supplied hash
map is not proof that it lists every dependency. No historical reference-error
provenance loader is silently substituted. No dataset is selected by this code.

## Cost and interpretation

The draft upper bound is four 400-point searches (two score policies × two c
arms), at most 1,600 point-arm fits before reuse, with 12 checkpointed 500-second
slices total per recording and explicit incomplete status at that cap. No
research budget is expanded here. A future operational candidate would use one
search with no extra optimized dimensions, but pay additional propagation and
scoring costs. Those costs remain unmeasured on recordings.

Whole-bank predictions stream in batches of 64. Native prediction matrices are
retained for native/parity checks. Existing bank storage and the iteration 114
zero-sum transport basis also consume memory; this adapter does not claim that
all memory is bounded by one prediction batch. It has not yet been profiled on
an embedded target.

The intended discriminator remains changed initial score ordering versus changed
fine-grid discovery. Reference distances may be evaluated only after operational
receipts are sealed. No accuracy gain, DS18-022 rescue, or independent-validation
claim follows from these synthetic tests.

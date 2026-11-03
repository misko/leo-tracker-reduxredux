# Vector scorer with a 128 MiB endpoint-bank limit

This experimental configuration follows the matched ordinary-build cache
comparison in `../vector-bank-capacity-v1/`. The bank limit is 128 MiB per
scorer context; deployment qualification here targets one worker. Scalar and
vector defaults are unchanged. This does not enlarge the detector queue.

Build recipe arguments are `generate|use LIBRARY OUTPUT immutable vector 128`.
Training uses the existing four training sites and fresh-track LOC1 input,
separate from the 16 held-out timing sites. The first two-worker training
profile failed GCC's value-profile consistency check; the rejected profile,
compiler error and timing are retained. Do not suppress that compiler error.
Retraining the instrumented binary with an explicit single worker in a fresh
GCOV_PREFIX produced a usable profile. `training-single.*` records that run.

The recipe now records and validates cache configuration before profile reuse.
Five recipe tests pass, including rejection of a changed cache size. Physical
ARM location, stencil and immutable-session tests pass for the resulting build.
Source hashes, accepted and rejected profiles, and compiler output are retained.

The full original-cadence overlap is in `../overlap-vector-bank128-v1/`.
Its detector, eight-entry queue, inputs, search budget and nice priorities are
unchanged. The comparison to the previous PGO build includes both cache size
and freshly trained compiler profile; use the ordinary ABBA result to isolate
the cache change. Search and detector overlap still excludes auxiliary stages
and cannot alone qualify a sustained full pipeline.

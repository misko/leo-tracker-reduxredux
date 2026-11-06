# ALGO07v3 experiment recipes and retained evidence

Read only the section relevant to the current measured hotspot. Paths below are
repository-relative unless absolute; they do not resolve relative to this file.
Historical timings are scoped observations, never ratios to multiply together.

Search guide: `screen_geometry`, `reassociation`, `conservative`, `predictive`,
`family_gates`, `position_geometry`, `discovery_schedule`, `annotation`,
`posterior`, `initial-cache`, `grid`, `gradients`, `numerical`, `catalogue`,
`encoding`, `likelihood`, `nomination`, `immutable-bank`, `scalar-phase`, `endpoint`.
The latest run/qualification status lives in the linked report and runtime
scorecard, rather than being inferred from an old recipe's proposed next action.

For residual-screen changes, `tools/benchmark_algo07v3_screen_geometry.py`
reads a completed owned request through the public evidence store and alternates
the frozen original screen with the current one. Run with `--request REQUEST
--output NEW_JSON --repeats 3`, BLAS pinned to one, one-core affinity and an
external `timeout -k 2 360`. It checks every complete screen against the saved
result and verifies inputs remain unchanged. Its prepared-component times do
not replace a fresh complete-pipeline comparison.

For reassociation screening, use `tools/benchmark_algo07v3_reassociation.py`
with `--request REQUEST --output FRESH_DIRECTORY --repeats 3 --timeout 1200`.
It runs fresh native inference, captures each live family-omitted screen, then
alternates the frozen serial implementation and the current one on one CPU.
Every complete screen must match the original invocation. It also profiles
conservative recovery separately. The overall instrumented clock includes
repeated screens and cProfile overhead, so it is not a full-pipeline speed
benchmark. Verify its final science and eight PNGs against the unchanged owned
request using the explicit entry-point-alias audit in
`reports/2026_11_05_algo07v3_recovery_arms/profile_parity.py`. Keep numerical
inputs and runtime sources unchanged until both the run and parity check finish.

For conservative recovery, `tools/benchmark_algo07v3_conservative.py` loads owned
native preparation and initial-fit evidence, builds a fresh scan context for
each trial, and alternates the frozen serial stage with concurrent arms. Use
`--request REQUEST --output NEW_JSON --repeats 3`, CPUs 0–2, one BLAS thread and
an external `timeout -k 2 600`. It compares every complete stage against the
saved serial result and records parent plus reaped-child CPU. This is prepared
stage evidence, not fresh full inference. The complete-run recipe in
`reports/2026_11_05_algo07v3_conservative_arms/run_pair.py` supports
`--candidate-first`; run a fresh normal pair followed by a fresh reversed pair
to record ABBA order. Retain all four complete timings and cross-pair exactness.

To isolate predictive recovery, add `--only-stage predictive` to the profiler.
The full pipeline still runs, but cProfile is active only during that stage and
its forked children. Each child has a matching `profile-PID.json` naming its
target/substage, arm or fold seed, and control/new-family variant where applicable.
Do not combine later numerical-replay substage rows with predictive timings.
Use the unchanged-source parity helper above to verify science and eight PNGs.
See `reports/2026_11_05_algo07v3_predictive_profile/README.md` for the qualified
example and a renderer that exports compact child summaries and a stage plot.

For exact-family gate replay, `tools/benchmark_algo07v3_family_gates.py` runs
fresh native inference and alternates complete old/new inclusion audits on each
live context. Use `--request REQUEST --output FRESH_DIRECTORY --repeats 3
--timeout 900` with CPUs 0–2 and one BLAS thread; audit trials pin one CPU and
restore affinity afterward. Require every full audit fingerprint to match,
then compare final science/eight PNGs with the unchanged-source parity helper.
Repeated trials copy the numerical policy so their problem/refresh receipts
cannot append to the normal run's ordered log; keep this isolation and its test.
The overall clock contains repeated audits and is not a pipeline speed result.
Keep these trials sequential with fresh full-run timing comparisons.

The external `tools/probe_algo07v3_position_geometry.py` experiment compares
fixed-phase prepared geometry with the original `JointMarginal.calculate`.
Use `--request REQUEST --output FRESH_JSON`, one CPU and one BLAS thread, outside
full-pipeline timing runs. It alternates three pairs for each c arm over 50 fixed
seeded regional points, requiring exact full geometry/features. Timing includes
first preparation but excludes problem construction, fitting and publication.
Its historical geometry-only timings do not qualify a pipeline speedup. The
owned calculator now includes the qualified fixed-phase cache; this external
probe retains the frozen original calculator and experimental function explicitly.
Inspect phase/grid/buffer invalidation tests and native receipts when changing it.

For complete fixed-phase geometry impact, use
`tools/benchmark_algo07v3_position_geometry.py --request REQUEST --output NEW_JSON`
with one CPU, one BLAS thread and an external `timeout -k 2 360`. It alternates
three old/new pairs for each c arm, executing all five phase-refresh rounds with
48 optimizer iterations per round on a saved initial hypothesis. Each trial
builds a fresh scan context outside the timer. Full fit/history/state/calculation
fingerprints must match; the temporary calculator substitution is restored even
on failure. Keep this benchmark sequential with full-pipeline timing runs.
This measures a prepared position fit, not discovery, recovery or publication.

To investigate discovery scheduling without changing runtime, use
`tools/probe_algo07v3_discovery_schedule.py --request REQUEST --output FRESH_DIRECTORY`
with three CPUs, one BLAS thread and an external `timeout -k 2 600`. It extracts
the unchanged per-seed body, uses batches of at most three existing workers,
and alternates three complete initial-search pairs. Every search must exactly
match the saved owned initial result; both sides keep existing paired-arm fits.
Fresh context construction is outside the timer. Report nested discovery time,
whole-stage time and parent-plus-child CPU separately. The current prototype
saves 1.649 stage seconds but adds 2.449 CPU seconds on DS26-0002 and remains
external. Do not equate reduced latency with better queue throughput.

For the slow predictive annotation fold, the external
`tools/probe_algo07v3_annotation_arms.py --request REQUEST --output FRESH_DIRECTORY
--target 1 --fold 1 --repeats 3` compares serial with paired training. Pin three
CPUs, one BLAS thread and an external `timeout -k 2 900`. Each trial rebuilds
owned context before timing; both arms retain five phase rounds and 48 position
iterations. Child results carry final-problem recipes, and reconstruction must
match full calculation/state fingerprints before nomination. Every complete
fold output must match. Numerical-policy replay is excluded, not silently
parallelized. This remains a single-fold experiment, not whole-pipeline speed
evidence. The owned worker now uses a bounded queue across fold/arm tasks, then
separate fold scoring; it never nests arm workers under three fold workers.
The annotation-training report records exact native DS26-0002 and DS26-0066
qualification. Use its `run_pair.py`/`run_baseline.sh` for seven
declared module overlays and its renderer for complete timing receipts. Profiler
child metadata now identifies training tasks as `[seed, arm]`. Annotation replay
and selection callbacks remain serial. Paired numerical inclusion now uses the
qualified receipt reconciliation below; preserve the three-live-worker cap.

For posterior-loop changes, measure complete fits as well as array kernels.
`tools/probe_algo07v3_posterior_assembly.py --request REQUEST --output FRESH_DIRECTORY`
alternates three full five-round initial fits per arm; the ordered-bincount
prototype is exact but slower on DS26-0002 and remains external.
`tools/benchmark_algo07v3_training_kernel.py --request REQUEST --output FRESH_DIRECTORY
--repeats 2` targets the previously profiled slow DS26-0066 target-1/fold-1
training fits. Pin one CPU and one BLAS thread, with a 900-second external bound.
It preserves optimizer histories, final state and complete likelihood in both
arms, constructs fresh contexts outside timing and restores kernel aliases on
failure. Its covariance-index candidate is now integrated after exact DS26-0002
native qualification and 727 tests; prepared DS26-0066 training gains are
4.54–5.99%. The helper uses the frozen pre-index oracle so future runs remain
old/new comparisons. The posterior-followup report retains the measured helper
bytes and both source strings, and provides the private-overlay native runner.
Prepared-fit gains do not establish a capture-to-publication or population gain.

For repeated initial calculations, use the observation-only
`tools/profile_algo07v3_initial_repeats.py --request REQUEST --output FRESH_DIRECTORY`
on one CPU and one BLAS thread. It executes every call and checks repeated full
results rather than assuming identical coordinates imply a fixed model. Then
`tools/probe_algo07v3_initial_cache.py --request REQUEST --output FRESH_DIRECTORY
--repeats 3` compares bounded one-entry reuse on three CPUs, alternating complete
initial searches against frozen pre-cache references. Use external bounds of
300 and 600 seconds respectively. The cache is experimental: six searches and
one native pair are exact, but the full native pair regresses 244.609 → 301.029 s
despite a small prepared-stage improvement. Retain that regression and keep the
runtime unchanged until repeated full-pipeline evidence supports integration.
The initial-cache report includes source overlays and a native runner. Do not
treat its archived candidate as deployed or its prepared timings as cumulative.

To refresh the slow posterior profile without a full native replay, use
`tools/profile_algo07v3_training_posterior.py --request REQUEST --expected
PREVIOUS_ARM_CANDIDATE_JSON --arm c0 --output FRESH_DIRECTORY`, pinned to one
CPU/BLAS thread with a 300-second outer bound. It profiles all five training
rounds, checks complete history/state against previously qualified evidence,
and retains the highest-iteration observed kernel input. Profiling is not timing
qualification. The posterior-buffers report records 220/350 calls reaching the
existing 256-iteration ceiling; preserve that ceiling and convergence tolerance.
The associated buffer benchmark uses `--request`, `--expected-root`, `--output`
and `--repeats 2` with a 900-second outer bound. Its eight exact fits show no
useful speed gain. Combined lower solves and direct upper solves are rejected
for numerical and signed-zero differences respectively; do not silently revive
them or treat mathematical equivalence as byte equivalence.

For finer posterior attribution, use `tools/profile_algo07v3_posterior_parts.py
--capture CAPTURE_DIRECTORY --output FRESH_DIRECTORY` with one CPU and one BLAS
thread. The capture contains the training profiler's bound `hardest.npz` and
`hardest.json`. This external AST instrumenter times posterior expressions while
returning their original results, validates expected boundaries and compares
three complete likelihood results exactly, including unchanged inputs. It does
not measure pipeline speed. The full-runtime-profile report records inverse
solving and covariance/factorization as the main captured-call costs; changing
the solver or precision ceiling still requires the existing exactness gate.

For diagnostic-grid execution, `tools/benchmark_algo07v3_grid.py --request REQUEST
--reference FROZEN_POSITION_GRID_PY --output FRESH_DIRECTORY` runs the owned
pipeline and alternates three complete serial/batched grid pairs on its live
selected likelihood. Use three CPUs and one BLAS thread. Its outer 1200-second
supervisor bounds the entire experiment. This clock includes repeated grids
and must not be presented as pipeline speed. Each grid must be complete and
match all scores, paired-arm failures, locations, order and policy; only elapsed
time is excluded. Source bindings, CPU counters and failed receipts are retained.
Use the unchanged-source publication parity helper to check the experiment's
final science and all eight PNGs against a fresh uninstrumented candidate.
The grid-batches report supplies a five-module frozen-overlay native pair runner.
Three contiguous process batches preserve a deadline-checked paired location
and publish only a contiguous prefix if time runs out. Near-deadline point counts
can differ with execution speed; do not claim exact partial-grid equivalence
from complete-grid fixtures. Keep worker failures as operational failures and
qualify parent cancellation/reaping using the existing bounded executor tests.

The hard-case grid report adds fresh DS26-0066 qualification and a complete
historical-science/PNG check across the intervening covariance-index change.
Both complete grid cases are exact, but DS26-0066 total time regresses
564.831 → 585.201 s while its plot stage improves 10.222 → 9.005 s. Preserve
that mixed evidence; the earlier 2.151× isolated grid ratio is not a pipeline
or dataset-wide speedup.

For gradient scheduling, `tools/probe_algo07v3_gradient_axes.py --request REQUEST
--output FRESH_DIRECTORY --repeats 1` runs four complete prepared training fits
on the slow DS26-0066 target-1/fold-1 case. Pin three CPUs and one BLAS thread,
with an external `timeout -k 2 900`, sequentially with native timing trials.
Each derivative axis uses one child for its ordered plus/minus pair; remaining
optimizer arithmetic is unchanged. Full history, evaluations, phase reference,
state and final likelihood must match in both arms. Four unit tests pass;
observed prepared-fit latency falls 18–21%, but total CPU increases 10–12%.
This prototype is external and must not be nested inside the existing three-
worker training queue.

The native owner-only follow-up uses `tools/probe_algo07v3_native_gradients.py
--request REQUEST --output FRESH_ROOT` with the same three-CPU limit and explicit
external substitution. It matches complete science and all PNGs on DS26-0002,
but its seven eligible fits regress 4.445 → 5.392 s and CPU rises 72.7%. They
cover only 1.52% of baseline wall time. Keep this policy external/rejected;
the whole-run 291.515 → 229.841 s difference occurs in unchanged stages and
does not support its integration. The report archives the measured verifier
and an exact post-run correction for explicit-empty source-change declarations.
An empty declaration requires no changes; an omitted declaration retains the
historical default. Do not bypass the source comparison to handle this case.
The coarser numerical-replay follow-up is now integrated with exact ordered
receipt reconciliation. `tools/probe_algo07v3_numerical_arms.py --request REQUEST
--output FRESH_ROOT --repeats 3` alternates complete serial/paired inclusion
fits in a fresh native execution, with three CPUs, one BLAS thread and a
1,200-second supervisor. Its repeated-work outer clock is not pipeline speed.
Each trial copies the incoming policy; compare complete fits and the resulting
receipt, and verify final native science/eight PNGs. The frozen serial oracle
is external measurement code, never a runtime dependency. The original probe
bytes are archived because it was subsequently adapted to that frozen oracle.

Three DS26-0002 pairs average 22.665 → 13.746 s, with CPU increasing 9.6%.
The fresh candidate-first native pair is exact and improves 171.653 → 169.742 s;
numerical replay itself falls 12.438 → 7.208 s. The 716-test suite covers ordered
receipt merging, unknown-policy serial fallback, failure cleanup and both
application forwarding boundaries. This is one-scan development qualification.
Annotation replay and selection callbacks remain serial; only independent
paired inclusion fits use reconciled policies. Do not generalize this mapper
to arbitrary mutable contexts or threaded execution.

Recovery catalogue preparation now shares the initial validated-text parser,
then releases it before inference. `tools/probe_algo07v3_catalogue_cache.py
--request REQUEST --output FRESH_ROOT --repeats 3` alternates complete native
preparation plus recovery-catalogue construction, starting with a fresh parser
for every trial. Pin one CPU and one BLAS thread and use an external
`timeout -k 2 360`. Compare complete preparation/catalogue fingerprints, keep
parser timings nested, and retain hit/miss/eviction counters. The current helper
uses the new explicit parser port; its earlier measured source is archived.
Every snapshot still passes the archive read/digest checks, causal selection
runs every time, and fresh SGP4 objects must never be shared through the cache.

Twelve trials on DS26-0002/0066 are exact. Catalogue means fall 5.513 → 2.040 s
and 8.819 → 3.994 s, with complete-preparation CPU also lower. The fresh full
DS26-0002 pair preserves science, both arms and eight PNGs: 280.056 → 245.043 s.
Only 4.558 s of its difference is in the targeted catalogue stage; unchanged
later stages vary, so do not credit all 35.013 s to the change. The 722-test
suite includes cache release before fitting, corrupted text, read failures and
causal filtering on hits. Full DS26 and original-ALGO07 cumulative qualification
remain outstanding. Next profile live evidence encoding or repeated likelihood
work before selecting another change; decoded saved evidence may alias arrays
that were separate in memory, so it cannot establish live encoding-cache gains.

The external `tools/probe_algo07v3_codec_headers.py --request REQUEST --output
FRESH_ROOT` profiles complete archive encoding on live evidence after fresh
native inference. Pin three CPUs and one BLAS thread; its process-group bound
is 1,200 seconds. It runs a scoped original profile and three alternating full
archive pairs, requiring byte equality throughout, then publishes the original
bytes. Compare final science/eight PNGs using the unchanged-source parity helper.
The outer clock includes eight encodings and is not normal pipeline latency.
Fourteen focused tests pass. Header reuse is rejected: DS26-0002 means regress
3.569 → 3.734 s, while NumPy save consumes only 0.025 s. The 2.916-second
unclassified remainder needs further attribution; do not call all of it
traversal. Predictive fitting (39.785 s), initial search (21.225 s) and residual
screening (14.210 s) remain much larger targets. The encoding report retains
fresh stage clocks, exact publication and all failed timing evidence.

For exact repeated-likelihood work, run
`tools/profile_algo07v3_likelihood_repeats.py --request REQUEST --output FRESH_ROOT`
with three CPUs and one BLAS thread; its supervisor bounds the fresh pipeline
at 1,200 seconds. It executes every original call, fingerprints complete inputs
including array layouts/defaults, checks repeated results, and resets observation
tables in children. The per-process call times overlap: never sum them as wall
latency. DS26-0002 has 6,784 calls and 507 repeats (12.664 accumulated seconds),
but keying costs 9.703 seconds. Predictive repeats cost only 1.999 seconds against
4.200 seconds of keying. General hashing caches are therefore lower priority.
Verify full normal-CLI science and eight PNGs with the unchanged-source helper.

`tools/probe_algo07v3_cholesky.py --capture CAPTURE --output FRESH_ROOT` compares
complete likelihoods on the bound hardest input. The direct LAPACK Cholesky
path is integrated after eight exact full DS26-0066 training fits and a fresh
native DS26-0002 pair. To repeat prepared training, use
`tools/benchmark_algo07v3_cholesky_training.py --request REQUEST --output FRESH_ROOT`
on one CPU/BLAS thread with an external `timeout -k 2 900`. It alternates two
pairs per arm with fresh contexts, five phase rounds and 48 optimizer iterations.
The tools retain the explicit frozen original oracle; measured pre-adaptation
tool bytes are archived. No runtime code imports the oracle.

Controlled training means improve 1.59%/1.05%; 772 tests pass. The full native
pair is 184.748 → 158.609 seconds, but unchanged rendering and system CPU vary
substantially. Preserve this distinction and the one-scan native scope. The
likelihood-repeats report supplies a one-module private-overlay runner, strict
source checks and renderer. Next profile residual-screen propagation, phase
nomination and finalist fitting before attempting bounded concurrency; preserve
ordering, callbacks, all rows and the existing scientific gates.

For residual-screen attribution, use `tools/profile_algo07v3_screen_parts.py
--request REQUEST --output FRESH_ROOT` on one CPU/BLAS thread with an external
`timeout -k 2 240`. It loads public owned prepared evidence, executes the complete
screen and validates every output/callback against that evidence. Scoped
non-forking cProfile accounting must pass before interpreting function rankings.
DS26-0002/0066 show coarse phase geometry at 83–87% of profiled screen time.

Nomination now projects the union of the original at-most-16 points per fold.
Full-data finalist fits, original fold selections and all gates remain intact.
`tools/probe_algo07v3_nomination_points.py --request REQUEST --output FRESH_ROOT`
alternates three complete screens per side, including propagation. Pin one CPU
and one BLAS thread with an external `timeout -k 2 360`. The helper uses an
explicit frozen pre-change oracle; measured pre-adaptation bytes are archived.
`tools/check_algo07v3_nomination_geometry.py --request REQUEST --output FRESH_ROOT`
with a 240-second bound additionally checks all reduced projections against
the corresponding full-grid columns before verifying the complete screen.

All twelve complete screens and 99 hard-scan phase grids are exact. Prepared
means improve 15.487 → 11.844 s and 17.781 → 13.535 s. Retain the slower first
DS26-0002 baseline; later pairs improve 12.72–15.35%. The native DS26-0002 pair
is 165.230 → 158.773 s, but the changed stage saves 2.035 s and total CPU 2.080 s;
do not credit all 6.456 wall seconds to the change. 796 tests pass. The final
source has whitespace-only cleanup plus a separate fresh exact publication
replay, retained with source/AST bindings by `verify_formatted.py`. The report's
one-module private-overlay runner and renderer retain both comparisons.
Production and whole-cohort qualification remain unchanged. Next re-profile
the reduced geometry path before considering scoped bank-validation reuse.

The post-nomination profiles are now in
`reports/2026_11_05_algo07v3_runtime_priorities/README.md`. Complete screens on
DS26-0002/0066 remain exact, with valid non-forking profiler accounting. Coarse
geometry still takes 80–83% of each profiled screen. DS26-0002's 99 empty-request
bank validations cost 3.376 cumulative seconds; investigate once-per-screen
validation of a locally immutable bank and scalar-phase index reuse separately.
At that stage neither proposal was implemented; later integrations are below.
The report also retains the 158.773/265.044 s
same-numerics native observations: CPU changes too, and the variation's cause is
unestablished. Preserve both, rather than advertising a stable native speed.

For immutable-bank validation reuse, run
`tools/probe_algo07v3_bank_validation.py --request REQUEST --output FRESH_ROOT`
on one CPU/BLAS thread with a 360-second external timeout. It alternates complete
screens, includes snapshot copying, and checks saved science, callbacks and input
preservation. Explicit frozen screen/phase oracles keep the old implementation
external. Read `reports/2026_11_05_algo07v3_bank_validation/README.md` before
changing the snapshot: read-only arrays still permit shape mutation, so the
qualified representation retains immutable bytes and shape tuples. Mutable-bank
callers and all per-call phase/time checks continue to validate normally.
Use the report's two-module native runner and exact publication comparator.
Its first candidate-first pair regresses 186.553 → 277.921 s; an opposite-order
pair improves 161.808 → 153.847 s, with screening 10.542 → 9.205 s. Both pairs and
cross-pair same-side science/eight PNGs match. `verify_repeats.py` declares an
explicit empty source-change set for those same-side comparisons. Retain both
timing outcomes; twelve final component trials and 845 tests support the narrow
development integration, not a stable complete-pipeline speed guarantee. Next
test shared scalar-phase indices, preserving per-satellite phase and empty-bank
behavior and every original numerical operation.

The scalar-phase experiment is now integrated. Use
`tools/probe_algo07v3_scalar_phase.py --request REQUEST --output FRESH_ROOT`
with one CPU/BLAS thread and a 360-second external bound. Both control and
candidate bodies compile against the owned immutable-bank class; using the
oracle's separate class would incorrectly revalidate control banks. The fresh
post-bank profile confirms one bank validation and 77% coarse-geometry share.
Twelve full screen trials improve 6.36%/5.00%; 99 real coarse states, layouts and
complete outputs match, and 975 tests pass. Native DS26-0002 is 165.924 →
154.351 s, but screening saves 0.532 s; do not attribute the whole difference to
that stage. The report's `prove_states.py`, one-module native runner and renderer
retain all bindings and exact publication checks. See
`reports/2026_11_05_algo07v3_scalar_phase/README.md`. Next test reuse of the exact
lower interpolation endpoint, currently gathered twice per state array, before
claiming any additional saving or changing runtime.

Endpoint reuse is now integrated. Run
`tools/probe_algo07v3_endpoint_reuse.py --request REQUEST --output FRESH_ROOT`
on one CPU/BLAS thread with a 360-second external timeout. Both implementations
use the same owned immutable-bank class; the frozen source is an external oracle.
It compares complete screens and callbacks and preserves input bindings. Twelve
trials improve mean time by 13.38%/8.74%; all 99 real coarse-state comparisons and
1,132 tests pass. Native DS26-0002 is 161.006 → 153.129 s, with screening
9.176 → 8.032 s and exact science/eight PNGs. Retain the slightly slower predictive
stage and other host variation; attribute only scoped evidence to the change.
The report's one-module pair, proof and renderer also export every native stage.
See `reports/2026_11_05_algo07v3_endpoint_reuse/README.md`. Next investigate
discarded azimuth calculation in screening, preserving elevation/rate arithmetic,
and predictive fitting's measured posterior cost. General likelihood hashing and
variance-buffer reuse have prior negative evidence; do not repeat them blindly.

The screen-azimuth optimization is integrated. Use
`tools/probe_algo07v3_screen_azimuth.py --request REQUEST --output FRESH_ROOT`
on one CPU/BLAS thread with an external 360-second bound. It omits discarded
azimuth calculations while preserving the original elevation/rate expressions.
Twelve complete screens improve 12.39%/12.70%; 99 real projections and 1,162 tests
are exact. Native DS26-0066 is 469.957 → 404.752 s, with residual screening
10.537 → 8.903 s. Unchanged fitting explains most of the full-run variation.
The report's `verify_history.py` also compares the earlier qualified DS26-0066
science/eight PNGs with ten explicitly declared intervening module changes.
See `reports/2026_11_05_algo07v3_screen_azimuth/README.md` for the one-module
native runner, exact proof, full stage profile and all receipts. Initial search
and predictive fitting account for 66.9% of the hard candidate's time. Next test
a bounded queue across the three initial branches and both arms, retaining
ordered results/callbacks and the existing three-worker maximum. This is a new
proposal, distinct from earlier discovery-seed and gradient experiments.

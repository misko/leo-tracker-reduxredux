# ALGO07 cumulative runtime scorecard

Latest incremental [recovery-arm iteration](../../reports/2026_11_05_algo07v3_recovery_arms/README.md):
fresh DS26-0002 runs take **229.888 → 202.201 s (12.04% lower)**. Predictive
recovery takes **69.319 → 45.570 s**; reported total CPU is **261.39 s on both
sides**. All scientific values, both arms, eight PNGs and publication match
exactly; 882 tests pass. Unchanged initial fitting also improves, so not all of
the wall difference is attributable to the change. This is a one-scan incremental
observation, not a new cumulative or population qualification. The new
[profiling skill](../../.agents/skills/profile-algo07v3/SKILL.md) records separate
parent/child profiles and recovery substages. Production remains unchanged.

Updated 2026-11-05. **Fresh cumulative same-scan observations are now available:**
original ALGO07 **642.886 s**, standalone v3 **440.510 s before** and **226.531 s
after** the reference, observed ratios **1.459× / 2.838×**. Both v3 executions
match all public values, both calibration arms, eight PNGs and all 17 scientific
audit mappings exactly. The shared host changed substantially: v3 records
15,722 major page faults before and six after. These observations do not
establish a stable population-wide ratio or the tenfold target.

The [cumulative report](../../reports/2026_11_05_algo07v3_cumulative_repeat/README.md)
retains all three executions. It also separates original worker time
**522.619 s**, publication **63.576 s** and other in-interval work **56.690 s**;
the last category includes research verification and orchestration. The new
metadata verifier checks 21 excluded fields across five initial policies, with
19 tests passing. Later metadata, full DS26 and production admission remain open.
No deployment occurred. Capture, GLRT extraction and queue delay are excluded.

Latest [family concurrency integration](../../reports/2026_11_05_algo07v3_family_integration/README.md)
passes 843 component tests and a fresh isolated complete-path comparison.
Observed time is **245.714 → 228.848 s (6.86% lower)** and total process CPU is
**272.02 → 259.99 s**. Both arms, all science, eight PNG bytes, grid/path and
publication match exactly. Family-stage time is **17.675 → 11.301 s**;
unchanged initial fitting also improves **26.495 → 22.482 s**, so not all of the
total difference is attributable to family scheduling. This single shared-host
pair is not a cumulative legacy-to-v3 or population-wide speedup. Production is
unchanged. Earlier entries below preserve their historical status and limitations.

Latest [development integration](../../reports/2026_11_05_algo07v3_variance_integration/README.md):
bounded variance batching is enabled in the owned CLI. Its module bytes match
the prototype with exact complete outputs on DS26-0002 and DS26-0066; 833
component tests pass. A fresh direct isolated CLI verification passes exactly
in **243.059 s** against a reused reference; this is not another matched speed pair.
The modest CPU-accounted timing gain and the earlier regression below are both
retained. This is not a deployment, population or cumulative speed qualification.

Latest [family-arm concurrency probe](../../reports/2026_11_05_algo07v3_parallel_family/README.md)
matches the full native scientific snapshot and all eight PNGs. Family-stage
wall time is **28.147 → 18.560 s (34.06% lower)**, with parent/child CPU
**28.142 → 29.955 s (6.44% higher)**. This trades extra CPU for stage latency;
it is not a complete-path speedup. The 489.988 s diagnostic runs both methods.
Three focused tests pass. Full CLI/publication and broader-case checks remain
before integration; production is unchanged.

Latest [CPU-accounted variance repeat](../../reports/2026_11_05_algo07v3_native_canary/variance-cpu-pair/README.md)
is exact and observes **244.383 → 234.399 s (4.09% lower)**, with total process
CPU **271.20 → 259.14 s (4.45% lower)**. Maximum reported RSS rises 3.24%.
This supports further qualification of a modest gain; the slower first pair
below remains part of the evidence. DS26-0066 also matches exactly. Development
integration is recorded above; no deployment or cumulative speed claim.

Latest complete-path [variance-batching pair](../../reports/2026_11_05_algo07v3_native_canary/variance-pair/README.md)
is exact but slower: **270.732 → 388.845 s (+43.63%)**. Unchanged stages also slow
down, so this observation cannot identify the cause. The optimization remains
external; the reverse-order repeat is recorded above. Nine new boundary tests
pass. This first pair supplies no speed gain or promotion evidence.

Latest exact-call result: [bounded variance batching](../../reports/2026_11_05_algo07v3_native_canary/README.md)
matches all 6,772 native calls and the full scientific/PNG snapshot. Alternating
kernel time decreases **124.650 → 110.722 s (11.17%)**. The 420.642 s diagnostic
duplicates kernel work and is not normal runtime. The prototype remains external;
DS26-0066's integrated-solver comparison is complete and exact. No cumulative gain is claimed.

Current [larger native canary](../../reports/2026_11_05_algo07v3_native_canary/README.md):
DS26-0066's pre-optimization baseline completes in **900.763 s**, including
422.640 s predictive recovery and 163.899 s initial search. It selects guarded
reassociation and retains 2,770 points in both arms. The integrated candidate
completes in **761.514 s**, with exact science, both arms, all eight PNGs and
publication fields. The observed reduction is **15.46%**; a short baseline
sampling profile and differing preparation timings prevent controlled attribution.
An external bounded variance-batching prototype passes 24 exact synthetic tests;
its completed native probe is recorded above. It is not enabled in the CLI.
Production is unchanged.

Latest development [solver integration](../../reports/2026_11_05_algo07v3_solver_integration/README.md):
upper-root solves and removal of overwritten Gaussian calculations are now in
the owned CLI. A fresh isolated execution takes **264.356 s** and exactly
matches all science, both c arms, eight PNGs and published artifacts. This is
a correctness run, not a new matched speed pair. The Gaussian change separately
saves 7.640 s across 1,692 exactly compared calls; do not add component savings
to older complete-path timings. The broad suite passes **820 tests**. A fresh
DS26-0066 baseline/integrated comparison is now exact as recorded above. No deployment; population,
ordinary admission and the cumulative speed metric remain unqualified.

Latest [upper-root complete-path pair](../../reports/2026_11_05_algo07v3_factor_reuse/upper-root.md):
baseline **266.242 s**, candidate **252.572 s**, an observed **5.13% reduction**
(1.054×) from native GLRT ready through all artifacts and atomic publication.
All science, both calibration arms, eight PNGs and grid/path artifacts match.
The independent alternating exact-call measurement saves 11.63% in the kernel.
One shared-host pair on DS26-0002 supports this prototype, not a cumulative or
dataset-wide speed claim. It remains external; 14 focused tests pass. A second
prototype removes overwritten Gaussian solves and has 12 passing focused tests;
its complete native probe is running. Production is unchanged.

Completed [factor-reuse pair and 17-section audit](../../reports/2026_11_05_algo07v3_factor_reuse/README.md):
both isolated native-to-publication runs are exact, including all PNGs. Times
are **380.865 / 264.616 s**, but baseline CPU pressure was much higher; the
observed 1.439× ratio is **not attributable to the optimization**. Factor reuse
remains external, with only a 2.33% interleaved component saving established.
All 17 mapped scientific audit sections match on DS26-0002; original worker
context construction counters are independently traced and explicitly mapped.
Operational metadata, broader branches, full DS26 and production admission stay
open. The broad suite has 777 passing tests; eight tests cover a separate new
upper-root prototype whose subsequently completed evidence is linked above.
No deployment.

Latest [factorization-reuse experiment](../../reports/2026_11_05_algo07v3_factor_reuse/README.md):
all 6,772 native likelihood calls and the complete scientific/PNG snapshot are
exact. Interleaved component time is **163.053 → 159.250 s (2.33% less)**.
The 536.354 s diagnostic executes both kernels and is not normal runtime.
A separate complete isolated pair is underway; no total gain or runtime
integration is claimed. Historical audit coverage increased to 16/17. Broad
and follow-up tests cover 750 distinct cases. Production remains unchanged.

Latest [reverse-order repeat and historical audits](../../reports/2026_11_05_algo07v3_repeat_audits/README.md):
standalone serial folds **284.846 s**, concurrent folds **258.638 s** (**9.20% less;
1.1013× observed**) with exact science, both arms and all PNG bytes. Concurrent
ran first, on the same three CPUs/BLAS settings; the host remained shared.
This is one native-GLRT-to-publication pair, not a cumulative legacy-to-v3 or
dataset-wide speedup. The first slower, load-confounded pair below remains valid
evidence. Historical audit coverage is now 15/17, with no differences in checked
values; 725 tests pass. Remaining audit/metadata, population and admission gates
are open. Production is unchanged.

Latest development integration:
[concurrent predictive folds](../../reports/2026_11_05_algo07v3_predictive_parallel/README.md).
The fresh standalone pair preserves all owned scientific outputs and artifacts
exactly. Its observed complete times are **293.750 → 444.458 s**, with sharply
increased production load during the candidate; this is **not evidence of a
total speedup**. Unchanged stages also slow. Three independent frozen-context
annotation comparisons preserve every proposal record and take 17.420 → 6.261 s,
16.930 → 6.131 s and 46.320 → 26.958 s. Their summed CPU time increases about
4.6%; these are multicore component-latency gains, not a pipeline throughput
claim. There are 703 passing focused tests and five additional comparator tests.
Infrastructure startup failures now abort instead of becoming scientific
rejections. No deployment occurred. Controlled total-runtime repeats, full DS26
and production admission remain open; all earlier observations are retained.

Latest owned integration:
[concurrent initial fits through publication](../../reports/2026_11_05_algo07v3_owned_parallel/README.md).
The fresh serial/current CLI pair preserves all owned scientific and published
outputs exactly. Initial search takes **39.453 → 26.903 s**, while the complete
supervised native-to-publication process takes **287.835 → 286.322 s (0.53% less;
1.0053× observed)**. Saving/publication took longer in the second run. This is a
single shared-host pair, not dataset-qualified end-to-end improvement. The
runtime port is now enabled in the development CLI, with 691 passing focused
tests including actual worker failure/cancellation cleanup. Production is
unchanged. Predictive recovery remains the largest stage at about 95 s.

Latest concurrency experiment:
[independent initial c arms](../../reports/2026_11_05_algo07v3_parallel_initial/README.md).
Four ABBA runs give **38.928 → 27.731 s (28.76% less)** for the full initial-search
stage, using two performance cores rather than one. Both arms and all branch
callbacks are exact. A subsequent complete native-to-PNG run preserves the
entire established scientific snapshot, 179 grid points and eight PNG bytes.
Its 279.527 s through rendering excludes publication and has no paired baseline.
This is an external prototype, not enabled in the owned CLI. Two new tool tests
pass. Owned concurrency/cancellation integration and population coverage remain
next steps; no complete-pipeline speedup or deployment claim follows.

Latest integration: [standalone scatter kernel](../../reports/2026_11_05_algo07v3_integrated/README.md).
Two fresh previous-kernel/current-kernel comparisons have exact owned science,
both arms, 179 grid points and all eight PNGs. Observed process times are
753.412 / 392.368 / 670.025 s (baseline / optimized / repeated baseline), pinned
to efficiency core 23. Both baselines experienced different host load; these
ratios are **not a qualified speedup**. The earlier 5.80% interleaved component
saving remains the better kernel evidence. The kernel is enabled in development,
with 670 passing focused tests and 12/17 historical audit mappings. DS26 retains
159 fast members, 158 available native inputs and one missing native run.
Full-cohort, accepted-branch, metadata and production-budget gates remain open.
No deployment occurred. Earlier entries below describe their historical states.

Latest exact numerical experiment:
[full-scan assembly probe](../../reports/2026_11_05_algo07v3_assembly/README.md).
All 6,772 paired likelihood calls and the complete native scientific/figure
snapshot match exactly. Summed component time is 192.753 → 181.576 s (5.80%
less), **not a complete-path speedup**. The prototype remains outside the runtime.
The fresh reference comparison now covers 11 of 17 audit sections; six mappings,
metadata semantics and population/production-budget gates remain open. There are
642 passing focused tests. A separate exact factorization-reuse microbenchmark
shows small variable timings, including one slowdown; it is also experimental.

Latest fresh reference/native pair:
[DS26-0002 sequential observations](../../reports/2026_11_05_algo07v3_pair/README.md).
The frozen ALGO07 chain takes **675.455 s** and native v3 **504.041 s** including
startup, with exact public outputs, all eight PNGs and 179 grid points. Eight
direct scientific audit sections also match; nine mappings and metadata-link
qualification remain open. The observed ratio is 1.340× (25.38% less time), **not
a fully qualified speedup**. Host load changed and reference export overlapped
early candidate work. One complete pair now has exact public outputs; fully
audited complete-path matched scans remain zero. The earlier 373.342 s candidate
observation is retained and is not substituted into this pair. There are 622
passing focused tests. An exact scatter-assembly prototype remains experimental.

Latest standalone CLI milestone:
[fresh run and input-free publication recovery](../../reports/2026_11_05_algo07v3_cli/README.md).
The explicit all-work validation CLI completes DS26-0002 native-to-publication
in **371.153 s**, or **373.342 s** including process startup, with exact science,
all 179 grid locations and eight PNGs. Saved-result publication with native/TLE
inputs hidden takes 9.718 s (12.160 s including startup). There are 611 passing
tests, including timeout, descendant cleanup and recovery checks. These are new
shared-host observations, **not** a controlled speedup over 477.365 s or the
older ALGO07 chain. Full-population and ordinary-clock admission gates remain open.
A combined-right-hand-side solve prototype failed exactness on all eight captured
calls and showed no component timing benefit; it is not enabled.

Latest persistence/publication milestone:
[isolated native input through the public manifest](../../reports/2026_11_05_algo07v3_publication/README.md).
The first complete v3 candidate observation is **477.365 s**, including owned
scientific storage and all eight published PNGs plus both sidecars. Reloaded
science and PNGs match exactly; the current HTTP routes serve them. This is an
unpaired observation using the initial archive encoding, with no complete
baseline/current speed ratio. It excludes acquisition, native GLRT extraction
and queue delay. Complete-path matched scans remain zero.

The scalar-encoding follow-up reduces encode/decode ABBA means from **18.501 to
7.400 s (2.50×)** and archive size from **211.518 to 79.902 MB**, with every field
and PNG exact. The optimized persistence/publication-only replay takes 19.780 s
including filesystem work; it performs no inference. Do not subtract component
timings to fabricate a new full-path runtime. The current focused suite passes
588 tests. Production execution controls/population gates remain open; no deployment.

Latest native-engine milestone: [native GLRT through eight figures](../../reports/2026_11_05_algo07v3_native_engine/README.md).
The owned application entry point completes DS26-0002 native preparation,
all numerical policies, 179 grid locations and eight PNGs in **311.064 s**.
The entire comparison output matches the prior connected run. This includes
native preparation but excludes qualification serialization, atomic publication,
capture and native GLRT extraction. There is no matched complete-path baseline
and no speed ratio. Predictive recovery accounts for 106.894 s, initial fitting
46.639 s and conservative fitting 27.820 s; grid evidence and rendering account
for 19.404 and 5.586 s. The report verifies a separate isolated native run with
older installations/results hidden and network access unavailable. There are
543 passing focused tests. Publication and production execution control remain
unfinished; complete-path matched scans remain zero, and no deployment occurred.
The subsequent exact-output observational probe finds 6,772 hierarchical calls
and 5,933 distinct input digests. A hypothetical 128-entry LRU covers only
14.465 s of 177.020 s measured likelihood compute; 2,048 entries cover 24.081 s,
before real cache costs and layout checks. Simple result caching is therefore a
limited opportunity, not the 10× route. No cache is enabled. See the native-engine
report for the complete measurements and two additional probe tests.

Latest connected presentation milestone: [fresh numerical state through eight figures](../../reports/2026_11_05_algo07v3_connected_presentation/README.md).
DS26-0002 completes prepared-input inference, an owned recorded path, all 179
grid locations and eight PNGs in **484.617 s** under shared-host load. Every
earlier numerical output is unchanged; both arms retain 2,783/4,211 points.
This excludes native preparation and atomic WebUI publication and has no matched
full reference, so it establishes no speedup. The separate DS26-0084 comparison
remains byte-exact with the owned path enabled. There are 515 passing focused
tests. Complete-path matched scans remain zero; no deployment occurred.
The separate cProfile run has identical outputs and identifies predictive
recovery (115.184 s) and the cross-stage hierarchical likelihood (163.129 s
inclusive) as major costs. These overlap and must not be summed. Qualified-run
timing also includes fingerprint/JSON overhead; 25.918 s is attributed to JSON
writing in the instrumented run. Missing profiler wrapper frames leave partial
stage attribution. No profiled/unprofiled ratio is a speedup measurement.

Latest presentation milestone: [owned selected-fit plot preparation](../../reports/2026_11_05_algo07v3_presentation/README.md).
On DS26-0084, all plot data, 179/179 grid locations and eight PNG bytes match the
frozen renderer exactly. Reference/candidate fixture-to-PNG observations are
**32.426 / 29.300 s** under concurrent shared-host load; preparation portions are
23.504 / 20.234 s. These include external fixture reconstruction and are not a
controlled speed ratio. The actual fresh numerical path is not yet connected
through publication. Final fitting now retains the winning likelihood for
presentation, eliminating a future need to reconstruct it from older exports.

Latest v3 milestone: [complete final numerical reassociation](../../reports/2026_11_05_algo07v3_reassociation_final/README.md).
The owned final numerical worker and all eight matched fits reproduce the frozen
DS26-0066 research canary exactly. The connected DS26-0002 prepared-input path
now completes final numerical recovery in **273.407 s**, with earlier outputs
unchanged. This excludes input preparation and all WebUI artifact publication;
it is not a complete-path speedup. The final-worker comparison uses fixture
reconstruction differently on the two sides and runs concurrently, so its
elapsed times must not be converted into a performance ratio. Complete-path
matched scans remain zero.

## Primary metrics

| Metric | Starting baseline | Current / candidate | Paired speedup |
|---|---:|---:|---:|
| Native GLRT ready → all standard web artifacts published, excluding queue waits | 675.455 s fresh reference, 300 s grid budget | 504.041 s fresh v3 process; exact public artifacts, eight direct science mappings | Observed 1.340×; unqualified pending remaining audit mappings and controlled repeats |
| Recorded IQ ready → all standard web artifacts published, including unchanged detector and excluding queue waits | Not measured as one complete matched run | Not measured as one complete matched run | Unavailable |
| Capture start → all standard web artifacts published, including acquisition and queue waits | No matched baseline/current cohort | No matched baseline/current cohort | Unavailable |
| ALGO07* versus its frozen ALGO07 reference, GLRT-ready through publication | 912.576 s observed; grid incomplete | 887.264 s observed; full grid | Unqualified: unequal completed grid work |

The current verification CLI begins at preserved native GLRT evidence. Its
runtime cannot establish raw-IQ-to-publication speedup. Parallel cohort runs
test parity; their contention, checkpoints and reused references prevent a
controlled timing claim. An unchanged final position alone is insufficient:
both calibration arms, associations, intermediate decisions and artifacts must
pass their declared comparisons.

The [fresh GLRT-ready timing trial](../../reports/2026_11_04_algo07_star_glrt_ready_timing/README.md)
retains an incomplete first reference: 562.161 seconds through ALGO06, then a safe
checkpoint before ALGO07. This is not a complete-path baseline. A revised,
predeclared trial advances verified checkpoints within one monotonic timer and
30-minute research bound. Its reference completes inference and eight-artifact
publication in an observed **912.576 s (15.21 min)**, but evaluates only 91/179
diagnostic grid locations and fails the strict completeness gate. The candidate
finishes in an observed **887.264 s (14.79 min)** with 179/179 grid locations.
These are unqualified private GLRT-ready latency observations, not a speedup.
Inference alone takes **817.550 → 821.556 s**; the final ALGO07 invocation takes
**136.173 → 106.075 s**. Upstream timing variation offsets the final-stage saving.
The shared host's load falls during the candidate run. Strict scientific parity
passes, but original publication parity fails. A separate matched 300-second
real-grid-budget replay produces exact 179-location grids and all eight PNGs;
it cannot retroactively qualify the original unequal-work timings.

The next architecture is specified in [the ALGO07v3 plan](algo07v3-plan.md): one
standalone engine without earlier ALGO runtime dependencies. Its 10× complete
processing target remains unachieved.

The [first v3 implementation](../../reports/2026_11_04_algo07v3_start/README.md)
provides standalone track/orbit components and exact phase-geometry reuse.
On a real-bank, deliberately repeated three-query workload, original trials take
7.836 and 5.637 s; cached trials take 2.017 and 2.066 s including setup. This is
a primitive-only experiment with a 1 GiB cache allowance, not a complete engine
speedup or a measured production hit rate. The full v3 processing path is not yet
implemented and its timing remains unavailable.

The [standalone preparation iteration](../../reports/2026_11_04_algo07v3_preparation/README.md)
adds causal catalogue/history, noise and phase-prior preparation. A DS26-0084
ABBA comparison reduces native-input-to-saved-preparation subprocess time from
22.263 to 13.946 s (1.596×), with exact scientific outputs on all four runs.
This excludes localization, recovery and publication. Preparation matches three
DS26 replay cases; track-only outputs match all 158 available members out of 159.

The [position-component iteration](../../reports/2026_11_04_algo07v3_position/README.md)
reproduces joint likelihoods, exercised descent histories and fresh discovery.
A same-CPU, sequential ABBA test of one declared hypothesis and a reduced
one-round/four-iteration budget measures 36.329 → 34.417 s (1.056×), with exact
outputs in all four trials. This is not complete regional search or full ALGO07.

The [initial-search extraction](../../reports/2026_11_04_algo07v3_initial_search/README.md)
now matches the full production-budget regional search on DS26-0084, including
acceptance and frozen-calibration extension. Its observed 123.472 → 88.268 s
elapsed times overlap on a shared host and are **not a qualified speedup**;
another bounded pair is slower on v3. Later recovery and publication remain
unimplemented, so the primary complete-path speed metric remains unavailable.

The [conservative-recovery extraction](../../reports/2026_11_04_algo07v3_conservative/README.md)
extends exact full-budget comparisons through paired rejection/refit and salvage
on DS26-0002, DS26-0084 and DS26-0102. Observed reference/v3 times are 77.462/77.610,
68.636/65.281 and 186.178/184.773 seconds respectively, under concurrent shared-host
load. These are completion observations, not controlled speed measurements.
The later policies and complete publication path are still unfinished.

The [family/history extraction](../../reports/2026_11_04_algo07v3_history/README.md)
extends exact comparisons through family weighting, causal phase priors and
predictive-linear acceptance/fallback on the same three cases. All persisted
scientific values also match archived production. Observed reference/v3 durations
are 101.906/102.593, 205.985/228.501 and 216.759/219.935 seconds under concurrent
shared-host load; no speedup is qualified. Those comparisons exclude signed-prior/
cavity selection, later recovery and publication.

The [signed-prior extraction](../../reports/2026_11_04_algo07v3_signed/README.md)
extends exact comparisons through historical signed-mean qualification and
both-arm RF refitting. All three contexts and archived incumbents match.
Observed reference/v3 durations are 144.529/187.646, 128.169/220.619 and
272.787/366.337 seconds. The candidate is slower in this uncontrolled shared-host
batch; no optimization or controlled regression ratio is established. Cavity
selection and the remaining recovery/publication path are still incomplete.

The [family-cavity extraction](../../reports/2026_11_05_algo07v3_cavity/README.md)
extends exact fresh and archived comparisons through full-catalogue family
nomination and paired replacement selection on the same three scans. Observed
reference/v3 durations are 113.085/114.265, 164.741/164.528 and 232.013/231.927
seconds. Both sides use the numerical in-memory harness under concurrent load;
these are not production worker timings or a qualified speedup. Recovery
inventory was the next missing stage at that milestone.

The [recovery-inventory extraction](../../reports/2026_11_05_algo07v3_inventory/README.md)
now reproduces the frozen ALGO03 inventory on all three scans, including exact
owners, publication support, point counts and production target order. The
candidate runs freshly through the entire implemented prefix; the reference
inventory starts from a saved cavity decision, so their durations have different
scopes and are not a speed comparison. Later predictive recovery, subsequent
policies and publication remain before complete-path qualification.

The [predictive-annotation extraction](../../reports/2026_11_05_algo07v3_annotation/README.md)
reproduces complete annotation of the largest remaining target in each of these
three scans. This includes every proposal, held prediction and both c arms, with
one supported identity and two rejected cases. Candidate timings include the
entire implemented prefix; the external reference starts from an archived cavity
decision. These remain unequal-scope timings, not a speedup measurement.
Shared/new-family position inclusion was the next missing stage at that milestone.

The [predictive-inclusion extraction](../../reports/2026_11_05_algo07v3_inclusion/README.md)
now exactly reproduces DS26-0002's shared-family rejection and new-family
acceptance after matched Powell retry, including every fit/audit and unchanged
earlier results. Fresh candidate durations are 132.204 and 186.780 seconds;
external reference replay plus annotation/inclusion takes 30.111 and 83.127
seconds. These scopes differ, so no speed ratio is valid. The multi-target/joint
controller, remaining recovery policies and publication still precede any
complete-path speed qualification.

The [ordered/joint recovery extraction](../../reports/2026_11_05_algo07v3_joint/README.md)
adds exact two-family covariance, all six initial fits/audits and all six matched
Powell retries on an explicit numerical fixture. Initial reference/v3 durations
are 66.013/63.933 seconds; Powell durations are 131.868/133.712 seconds. These
are comparable component scopes under shared-host load, not a controlled speedup
or complete-path measurement. The fresh DS26-0002 controller loop separately
matches the qualified individual references; fresh joint target selection,
deadline policy and later recovery/publication qualification remain open.

## Measured improvements within the pipeline

The [checkpoint/residual-screen iteration](../../reports/2026_11_05_algo07v3_residual_screen/README.md)
adds the adopted raw-likelihood handoff and the 72-hour / 30-second causal screen.
Eight target screens match exactly, including three passes; no new associations
are credited before position acceptance. Catalogue reference/candidate observations
are 6.747/6.037 s; isolated screens are 16.311/16.449 s and 24.869/24.326 s.
These are overlapping shared-host observations, not controlled speedups. The fresh
DS26-0002 implemented fitting prefix through screening takes 243.577 s and preserves
the prior scientific prefix exactly. It excludes preparation, later position trials,
final reassociation and publication. Complete-path matched scans remain zero; no
complete-path ratio is available.

The [selected-likelihood/preflight iteration](../../reports/2026_11_05_algo07v3_selected_incumbent/README.md)
matches four frozen-context branches on three scans, including both-arm selected
likelihoods, nearby-position probes, native residual ranking and corrected target
arrays. The owned application runs with old installations hidden. Component
reference/candidate observations are baseline 3.965/3.304 s, single-family
5.098/4.255 s, joint-family 4.711/3.920 s and conditional-gap 4.041/3.323 s.
These concurrent shared-host observations are not controlled speedups. No new
position fitting or association is performed by this stage. Full-path matched
scans remain zero; the complete processing metric is unchanged and unavailable.

The [owned gap-controller iteration](../../reports/2026_11_05_algo07v3_gap_controller/README.md)
matches the complete frozen-context DS26-0012 controller proof, all four stages
and numerical receipts. Observed reference/candidate durations are 41.064/34.766 s,
not a controlled benchmark. The fresh DS26-0002 implemented fitting prefix through
gap recovery takes 375.066 s, preserves the previously qualified numerical prefix
exactly and retains all 2,783 owners per arm. It finds no proper fragment to add.
This excludes native preparation, ALGO06/07 and publication, so no complete-path
ratio is available. The first integrated run caught eager concrete-adapter imports;
lazy public exports and deferred preparation adapters fixed the boundary without
weakening the dependency guard. Complete-path matched scans remain zero.

The [conditional gap components](../../reports/2026_11_05_algo07v3_gap/README.md)
match fresh DS26-0012 preparation/annotation and conditional fits/exact audits,
including numerical receipts. Both arms recover the same 95 points with fixed
receiver coefficients; the default six joint fits/audits remain exact. Observed
reference/candidate annotation times are 49.039/33.064 s and fit/audit times are
33.171/26.544 s. These concurrent component runs are not a benchmark or a
complete-path speedup. That component check did not qualify controller integration,
later recovery, full DS26 or final publication; complete-path matched scans remain zero.

The [conditional replay extraction](../../reports/2026_11_05_algo07v3_replay/README.md)
matches DS26-0044's complete annotation replay and DS26-0002's conditional
selection/receipts, preserving the previously qualified predictive prefix.
Annotation reference/candidate component durations are 76.949/66.798 seconds.
The fresh candidate fitting prefix through numerical recovery takes 399.779
seconds; the independent reference's 71.292 seconds covers only annotation and
numerical inclusion. Those scopes cannot be used for a speedup. Five stages are
reused and two recomputed in the numerical pass; all 2,783 scoped owners survive
in both arms. Complete-path timing, full DS26, timeout policy and UI publication
remain incomplete.

The [numerical-policy extraction](../../reports/2026_11_05_algo07v3_numerical/README.md)
matches all six frozen ALGO04 component fits/audits, including every orbital
posterior coefficient and numerical receipt. Original predictive policy
reference/v3 durations are 65.473/64.782 seconds; numerical-policy durations are
196.220/118.357 seconds. These overlapping shared-host runs are not a controlled
speed benchmark and cannot establish an end-to-end ratio. The numerical policy
performs 740 physical objective evaluations across 30 rounds (maximum 45 per
round, cap 240). Conditional replay, later policies, full DS26 and publication
remain incomplete. A first strict comparison failed on stage-specific contraction
order; preserving the frozen orders fixed it without relaxing equivalence.

The [owned additional-family position stage](../../reports/2026_11_05_algo07v3_additional_position/README.md)
matches the complete DS26-0086 control and candidate exactly in both arms, adding
the same 26 points to its 3,285 incumbent owners. Reference/candidate observations
are **295.876/283.929 seconds**; these overlapping shared-host runs are not a
controlled speed benchmark. A fresh connected DS26-0002 prefix takes **260.781
seconds**, preserves all earlier science, and correctly skips an already
represented family. It excludes native preparation, final guarded reassociation
and all artifact publication. Complete-path matched scans remain zero and no
end-to-end ratio is available. The focused suite passes 397 tests.

The [final-stage handoff and RF trigger](../../reports/2026_11_05_algo07v3_reassociation_context/README.md)
match the frozen final ALGO07 engine on DS26-0086, preserving 3,311 owners per arm
and all 26 family-influence rankings. The component observations are
**304.143/284.512 seconds** for reference/v3; this is an overlapping shared-host
comparison, not a controlled speedup. A fresh connected DS26-0002 prefix through
the trigger takes **381.182 seconds**, preserving every previously validated
field and 2,783 owners per arm. Remaining final-stage nomination/validation/fits,
native preparation and artifact publication are excluded. The selector matches
six decision checks and the focused suite passes 424 tests. Whole-path matched
scans and the end-to-end speedup remain zero/unavailable respectively.

The [final causal screen and receiver-shared admission](../../reports/2026_11_05_algo07v3_reassociation_screen/README.md)
match the frozen DS26-0066 component exactly, admitting 62025 → 68047 on the same
140 native points. The observed reference/controller durations are **19.072 /
19.975 seconds**, with overlapping shared-host execution and one extra catalogue
preparation in the candidate oracle solely for bank fingerprinting. They are not
a production speed comparison. The fresh connected DS26-0002 prefix through
this stage takes **307.896 seconds**, preserves all earlier scientific output
and admits no replacement. The focused suite passes 449 tests. No complete-path
baseline/current pair or end-to-end ratio exists yet; remaining replacement fits,
native preparation and artifact publication are outside this measurement.

| Scope / experiment | Reference | Candidate | Ratio | Qualification / limitation |
|---|---:|---:|---:|---|
| Final ALGO07 numerical worker, two-family case, iteration 002 | 779.063 s | 420.000 s | 1.855× | Full worker; exact scientific comparison; profiled overlapping runs on shared host |
| Upstream ALGO03 recovery, single-family case, iteration 009 | 557 s | 314 s | 1.77× | Stage only; rounded report values; qualified numerical contract |
| Upstream ALGO03 recovery, joint-family case, iteration 009 | 929 s | 560 s | 1.66× | Stage only; rounded report values; qualified numerical contract |
| ALGO07* terminal-result validation/read, DS26-0170 ABBA means | 10.111 s | 1.618 s | 6.250× | Exact returned result; 8.493 s saved per measured read; experimental |
| Standalone v3 preparation, DS26-0084 ABBA means | 22.263 s | 13.946 s | 1.596× | Exact science; native-input-to-saved-preparation only; excludes position/recovery/publication |
| V3 bounded position component, DS26-0084 same-CPU ABBA means | 36.329 s | 34.417 s | 1.056× | Exact outputs; one hypothesis, both arms, one phase round × four iterations; excludes full search/recovery/UI |
| Native GLRT tiling, 16 paired-window DS27 fixture | 25.454 s | 16.643 s | 1.529× | Detector-only alternating trial; prototype, not deployed by that report |

These are separate experiments, not one cumulative baseline/current pair.
Do not multiply their ratios or add their savings to claim pipeline speedup.
Stage benefits vary with scan workload. The November 4 profile separately
observed 319.57 s across ALGO02–07 workers and a fresh 454.17 s native replay;
those different executions must not be summed into an end-to-end measurement.

Sources:

- [Final-worker measurement](../../reports/2026_11_03_algo07_runtime_iteration002/README.md)
- [Recovery qualification and deployed release](../../reports/2026_11_03_algo07_runtime_iteration009/README.md)
- [ALGO07* ABBA timings](../../reports/2026_11_04_algo07_star_optimized_smoke/terminal-read-timings.json)
- [Native detector prototype](../../reports/2026_11_03_algo07_runtime_iteration005/README.md)
- [November 4 production/profile inventory](../../reports/2026_11_04_algo07_pipeline_profile/README.md)

## Required update on every optimization iteration

Lead each runtime report with complete-path baseline seconds, candidate seconds,
seconds saved, ratio, matched scan count and parity status. Use **unavailable**
when the complete-path measurement is missing; never replace it with a kernel
ratio. Preserve this original-baseline comparison as well as the immediately
previous-version comparison, so cumulative progress stays visible.

For a qualifying measurement, bind input, causal catalogue, runtime revisions,
hardware, worker/thread counts, cache conditions and budgets. Time baseline and
candidate sequentially in alternating order, with the same raw input through
successful publication of every required artifact. Retain host-load evidence,
failures, timeouts and incomplete outputs. Record acquisition, queue/handoff
waits, native GLRT, position processing and publication separately without
double-counting overlapping intervals. Record the outer monotonic wall timer
even when individual stage instrumentation is unavailable.

Report paired per-scan ratios and baseline/current median and p90 durations
across the same declared workload cohort; include completion and exact-parity
counts. Capture-to-publication latency and processing speed are separate
metrics: queue reductions can improve the former without changing computation.
Historical stage timings do not reconstruct the missing starting full-path
baseline; obtain it by replaying the pinned original implementation.

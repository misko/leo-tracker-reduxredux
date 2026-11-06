# ALGO07 cumulative runtime scorecard

November 6 [common native prefix recovery diagnostic](../../reports/2026_11_06_algo07v3_native_recovery_queue/README.md):
one complete recovery pair improves **180.483→138.434 s**, preserving all stage
outputs, selected state and the prior native audit. This is a stage-only,
instrumented baseline-first pair, with changing task CPU/off-CPU costs. It does
not override the two complete native regressions below or establish a new
cumulative speedup. No runtime/production changes; 19 tool tests pass.

November 6 [cross-target training queue](../../reports/2026_11_06_algo07v3_cross_target_queue/README.md):
**candidate rejected and default restored**. Prepared DS26-0066 annotation
improves 14–22%, but complete native comparisons regress 399.664→485.562 s and
400.526→549.862 s. Both retain exact science, both arms and eight PNGs. The
restored default passes 1,959 tests. No new cumulative speedup or production
change. Compare recovery from the same native prefix checkpoint next; explain
the prepared/native discrepancy before another integration attempt.

November 6 [training reuse census and covariance experiments](../../reports/2026_11_06_algo07v3_covariance_reuse/README.md):
no runtime or production change. Six DS26-0002 fold masks are all distinct;
DS26-0066 has 23 distinct masks among 24 folds, with its slow fold unique.
Symmetric BLAS covariance fails exactness. Output-buffer reuse preserves the
captured likelihood and complete difficult training signatures, but individual
timing pairs vary, including a slower reverse c=0 pair. Keep it external until
convincing complete-scan evidence. No new cumulative speedup. Next profile the
recovery timeline across targets to assess idle-slot filling under the same
three-worker limit and canonical admission/selection semantics.

November 6 [compiled assembly and convergence analysis](../../reports/2026_11_06_algo07v3_ordered_assembly/README.md):
**candidate rejected; default numerical implementation restored**. Although
captured-call mean improves 4.00% and hard fitted-c training improves 2.61%,
both complete DS26-0002 pairs regress: **148.203→169.946 s** and reverse-order
**233.069→258.349 s**. Both retain exact science and eight PNGs. Candidate tests:
1,492 passing. Shared-host variation does not justify discarding the regressions.
No new overall speedup or production change. Native binary provenance is retained
as an independent verification improvement.

The [new convergence profile](../../reports/2026_11_06_algo07v3_ordered_assembly/convergence.md)
localizes the hard fold's cost to its first phase: 269 calls per arm, 220 reaching
the 256-iteration ceiling. Later rounds generally take 10 iterations per call.
All six fits are exact. Investigate the first-round trajectory and exact reuse,
keeping the original initialization, stopping rule, data and budgets.

November 6 [exact reference recovery and cumulative comparison](../../reports/2026_11_06_algo07v3_reference_recovery/README.md):
original ALGO07 **886.905 s**, bracketed by current v3 **193.899 / 152.529 s**
on DS26-0002, with exact public outputs, both arms, eight PNGs and 17 scientific
audit sections. Observed ratios **4.57–5.81×** reuse one reference; they are not
independent pairs or a population guarantee. Original worker-plus-publication
subtotal is 811.989 s (ratios **4.19–5.32×**), explicitly excluding orchestration
gaps. Native GLRT extraction, capture and queue waits are outside these clocks.
All 72,405 original runtime and 2,149 presentation manifest entries verify
unchanged after twelve exact private overlays, including seven reconstructed
bytecode files matching their original SHA-256 hashes. The failed attempts below
remain recorded. Later metadata, full DS26 and production admission remain open.

The [predictive queue profile](../../reports/2026_11_06_algo07v3_training_queue/README.md)
finds two 45.5–47.0 s tasks versus four 2.3–2.5 s tasks on DS26-0066 target 1.
Training takes 47.815 s at 71.1% three-slot occupancy; prescient reordering offers
only 0.755 s in simulation, not a measured speedup. Both full annotations and
saved decisions match exactly; nine tool tests pass. No numerical changes.
Next measure precision convergence by fold and test ordered assembly; bigger
caches and task reordering have negligible measured opportunity here.

November 6 [cumulative refresh and cache census](../../reports/2026_11_06_algo07v3_cumulative_current/README.md):
fresh current v3 completes DS26-0002 in **161.431 s** with exact unchanged
science/eight PNGs. The original reference fails its frozen-runtime check before
the first scientific worker: two source and seven generated-bytecode entries
drifted. **No new original-ALGO07 speedup ratio is available.** The earlier
213.191 s execution used the same v3 code, so that difference is run variation.
An observation-only hard DS26-0066 cache census passes both full fit signatures
and ten tool tests. Larger per-problem caches would avoid just **0.0783 s** across
both arms; capacity remains eight. No runtime or production changes. Repair and
preflight reference packaging, then refresh cumulative timing; measure predictive
queue utilization before the next scheduling change.

The [inverse-workspace iteration](../../reports/2026_11_05_algo07v3_lapack_workspace/README.md)
is integrated in development with **1,332 passing tests**. All four complete
DS26-0066 training pairs improve exactly: fitted-c mean 46.417 → 45.588 s (1.79%);
c=0 mean 53.199 → 48.912 s, but its reverse pair improves only 0.72%. The
51.437-second native difference (**264.628 → 213.191 s**, observed 1.241×) is not
an isolated optimization gain: unchanged screening, rendering and publication
also get substantially faster. CPU is 404.400 → 328.920 s; all science, both
arms, ownership, public grid/path and eight PNG bytes match. LU-only, combined
workspace and layout-only alternatives remain external. The posterior profiler
supports the new solve boundary and retains old-boundary tests. Next prioritize
a fresh matched original-ALGO07/current-v3 cumulative comparison; do not combine
this pair with the preceding 151.305-second observation. Production and full
DS26 admission remain open.

The [initial-queue iteration](../../reports/2026_11_05_algo07v3_initial_queue/README.md)
is integrated in development with **1,203 passing tests**. Ten complete prepared
searches preserve all results/callbacks; initial-search means improve 7.6% on
DS26-0002 and 8.0% on DS26-0066, with slightly higher CPU. A fresh native
DS26-0002 pair is **152.602 → 151.305 s (0.85%, observed 1.009×)**. Initial search
is **20.744 → 18.877 s**, and full science, both arms, ownership, grid/path and
eight PNG bytes match. CPU is **224.770 → 227.200 s**; unchanged stages vary in
both directions. This is a modest incremental gain, not a cumulative ratio.
Eight further trials reject fitted-c-first priority: both scan means regress.
A fresh exact posterior profile confirms inverse solves/factorization/covariance
work as the next larger target. Production, full DS26 and matched original-
ALGO07/current-v3 qualification remain open.

The [screen-azimuth iteration](../../reports/2026_11_05_algo07v3_screen_azimuth/README.md)
is integrated in development with **1,162 passing tests**. Twelve exact complete
screens improve 12.39%/12.70% on DS26-0002/0066; 99 real coarse projections match
every output bit and layout. Fresh native **DS26-0066 is 469.957 → 404.752 s**,
saving 65.205 s (observed 1.161×), with exact science/eight PNGs. Residual screening
saves **1.633 s** (10.537 → 8.903 s); reassociation admission also improves, but
most whole-run variation is in unchanged fitting stages. This is not a stable
65-second attributable gain. The current result also matches earlier qualified
DS26-0066 science/eight PNGs across ten explicitly declared module changes.
Predictive fitting plus initial search account for 66.9% of this candidate's
time. Next test bounded scheduling across initial branch/arm fits. Production,
full DS26 and original-ALGO07 cumulative qualification are unchanged. The skill
now keeps detailed historical recipes in a linked reference.

The [endpoint-reuse iteration](../../reports/2026_11_05_algo07v3_endpoint_reuse/README.md)
is integrated in development with **1,132 passing tests**. Twelve exact complete
screens improve by 13.38%/8.74% on DS26-0002/0066; all 99 real coarse-state
comparisons match. Native DS26-0002 is **161.006 → 153.129 s**, saving 7.877 s
(observed 1.051×), with exact science/eight PNGs. Screening saves **1.144 s**
(9.176 → 8.032 s); other stages vary and predictive recovery slightly regresses.
The complete difference is not all attributable to this change. The report
includes every stage, CPU/RSS and the next measured targets. Production,
whole-cohort and original-ALGO07 cumulative qualification are unchanged.

The [scalar-phase iteration](../../reports/2026_11_05_algo07v3_scalar_phase/README.md)
is integrated with **975 passing tests**, twelve exact complete screens and
99 exact real coarse-state comparisons. Screen means improve 6.36% and 5.00%
on DS26-0002/0066. Native DS26-0002 is **165.924 → 154.351 s**, with screening
**9.394 → 8.862 s** and exact science/eight PNGs. Do not credit the entire
11.573-second native difference to the measured 0.532-second screen improvement;
initial-search and system-time variation remain. Production, whole-cohort and
original-ALGO07 cumulative qualification remain unchanged.

The [immutable-bank iteration](../../reports/2026_11_05_algo07v3_bank_validation/README.md)
is integrated in development with **845 passing tests**. Twelve final complete
screen trials are exact: mean elapsed decreases 4.25% on DS26-0002 and 12.80%
on DS26-0066, with similar CPU reductions. Complete native timing is mixed:
candidate-first **186.553 → 277.921 s**, then baseline-first **161.808 → 153.847 s**.
The second pair's screen falls **10.542 → 9.205 s**; do not attribute its entire
7.961-second complete difference to that 1.337-second stage saving. Both pairs
and repeated same-side science/eight PNGs are exact. Preserve the first regression;
this does not establish a stable whole-pipeline speedup. Production, full-cohort
and cumulative original-ALGO07 qualification are unchanged.

See [current runtime priorities](../../reports/2026_11_05_algo07v3_runtime_priorities/README.md)
for all native stages, exact post-change screen profiles on DS26-0002/0066 and
the slower same-numerics confirmation. Predictive fits take 23–25% of those
native timings; coarse geometry takes 80–83% of residual screening in those
historical profiles. Scoped bank validation and scalar-phase index reuse have
since been integrated, as recorded above.
Production and full-cohort qualification are unchanged.

The [nomination-point iteration](../../reports/2026_11_05_algo07v3_nomination_points/README.md)
is integrated in development. Twelve complete screen trials are exact; means
improve **15.487 → 11.844 s** on DS26-0002 and **17.781 → 13.535 s** on DS26-0066,
with matching CPU reductions. All 99 hard-scan coarse phase grids also preserve
every selected frequency/elevation value exactly. The fresh native pair is
**165.230 → 158.773 s (observed 1.041×)**, with exact science, both arms, ownership,
public grid/path and eight PNGs. Only **2.035 s** of the 6.456-second difference
is in the changed screen stage; total CPU falls **2.080 s**. **796 tests pass**.
A separate final-format replay verifies the committed source exactly. Production,
full DS26 and cumulative original-ALGO07 speed qualification remain unchanged.

The [likelihood/Cholesky iteration](../../reports/2026_11_05_algo07v3_likelihood_repeats/README.md)
is integrated in development. Eight complete DS26-0066 training fits are exact:
means improve **47.506 → 46.751 s** for c=0 and **46.200 → 45.715 s** for fitted c
(1.59% and 1.05%, with comparable CPU reductions). The fresh native DS26-0002
pair preserves both arms, every scientific audit, ownership, public grid/path
and eight PNG bytes: **184.748 → 158.609 s**, observed 1.165×. Unchanged rendering
and other stages vary, so do not attribute the whole 26.138-second difference to
the small kernel change. **772 tests pass**. General likelihood caching is lower
priority: predictive repeat-call cost is below its fingerprinting overhead in
the new observation profile. Production, full DS26 and cumulative original-
ALGO07 timing qualification remain unchanged.

The [live encoding profile](../../reports/2026_11_05_algo07v3_encoding_profile/README.md)
rejects header caching: three complete archive pairs average **3.569 → 3.734 s**,
4.62% slower, despite exact bytes. Fourteen tests and complete normal-CLI
science/both-arm/eight-PNG parity pass. Fresh stage clocks identify predictive
recovery **39.785 s**, initial search **21.225 s** and residual screening
**14.210 s** as the main targets. The 187.850-second supervised clock includes
eight encodings; it is not a normal-run speed result. Runtime, production and
cumulative qualification remain unchanged.

The [recovery catalogue cache iteration](../../reports/2026_11_05_algo07v3_catalogue_cache/README.md)
is integrated in development. Twelve complete preparation trials on DS26-0002
and DS26-0066 are exact: catalogue means improve **5.513 → 2.040 s** and
**8.819 → 3.994 s**, with lower complete-preparation CPU. Fresh DS26-0002 native
time is **280.056 → 245.043 s (observed 1.143×)**, with exact science, both arms,
ownership, public grid/path and eight PNGs. The targeted catalogue stage saves
**4.558 s**; unchanged later stages explain most of the 35.013-second overall
difference. **722 tests pass**. The cache is released before fitting. Full DS26,
production and original-ALGO07 cumulative speed qualification are unchanged.

The [paired numerical-replay iteration](../../reports/2026_11_05_algo07v3_numerical_arms/README.md)
is integrated in development. Fresh DS26-0002 native time is **171.653 →
169.742 s (1.011×)**, saving 1.911 s, with exact science, both arms, ordered
numerical receipts, public grid/path and all eight PNGs. The replay stage falls
**12.438 → 7.208 s**. Three alternating complete-fit pairs average **22.665 →
13.746 s**, with CPU increasing 9.6%; full-run CPU rises 3.5% in the native pair.
Unchanged stages offset part of the stage saving. **716 tests pass**. Full DS26,
production admission and original-ALGO07 cumulative timing remain outstanding.

The [native gradient scheduling trial](../../reports/2026_11_05_algo07v3_native_gradients/README.md)
is **rejected for integration**. Complete DS26-0002 science and eight PNGs match,
but its seven targeted fits regress **4.445 → 5.392 s**, with CPU **4.441 →
7.669 s**. They cover only 1.52% of baseline wall time. The full observed pair
**291.515 → 229.841 s** improves in unchanged stages and does not establish
prototype benefit. Eleven tests pass, including the explicit-empty source
declaration verifier correction; original checker bytes and corrected recheck
are preserved. Runtime, production and original-ALGO07 speed claims are unchanged.

The [hard-scan follow-up](../../reports/2026_11_05_algo07v3_grid_hard_case/README.md)
qualifies grid batching exactly on DS26-0066 and matches the earlier complete
scientific output and eight PNGs across the intervening changes. The candidate-
first full pair **regresses 564.831 → 585.201 s**; the plot-evidence stage improves
**10.222 → 9.005 s**, with large variation in unchanged stages. Retain this
regression. An external two-axis gradient prototype preserves four complete
prepared training fits: **46.923 → 36.865 s** for c=0 and **45.185 → 37.024 s**
for fitted c, with CPU increasing 10–12%. Four new tests pass. The gradient
prototype is not integrated, and full DS26/original-ALGO07 timing qualification
and production remain unchanged.

The [diagnostic-grid batching iteration](../../reports/2026_11_05_algo07v3_grid_batches/README.md)
is integrated in development. A fresh DS26-0002 pair is exact through both arms,
every scientific audit, public grid/path and all eight PNG bytes: **230.877 →
174.353 s**. Unchanged stages also improve substantially, so the full difference
is not attributable to batching. Three alternating isolated grid pairs average
**13.778 → 6.404 s (2.151×)**; grid CPU increases **13.774 → 15.063 s (9.36%)**.
The native plot-evidence stage drops **14.144 → 6.494 s**. **707 distinct tests
pass**. This is one-scan complete-grid qualification; partial-grid timing,
full DS26, production and cumulative/original qualification remain outstanding.

The [fresh complete v3 profile](../../reports/2026_11_05_algo07v3_full_runtime_profile/README.md)
records **175.426 s unprofiled** and **215.765 s instrumented** on DS26-0002,
with complete science, both arms and all eight PNG bytes exact. Predictive
recovery (38.048 s), initial search (21.476 s) and diagnostic grid preparation
(14.048 s) lead the unprofiled stages. Eleven tests pass. Independent stage
wall/CPU counters are valid; inconsistent global parent cProfile accounting is
explicitly rejected. This is unchanged-runtime profiling, not a new speedup
or full-cohort qualification. No fresh original-ALGO07 pair was run.

The [current posterior profile and buffer trials](../../reports/2026_11_05_algo07v3_posterior_buffers/README.md)
identify 49.633 of 50.998 profiled training seconds inside the hierarchical
likelihood; 220/350 calls reach its unchanged 256-iteration ceiling. Eight full
training fits are exact, but scratch-buffer timing is flat for c=0
(62.323 → 62.341 s) and regresses for fitted c (56.711 → 62.005 s).
Keep these experiments external. Two solver shortcuts fail exactness and are
also rejected. This iteration adds profiling/qualification evidence, not a
runtime change or a new cumulative speedup; 94 focused tests pass.

The external [scoped initial-cache experiment](../../reports/2026_11_05_algo07v3_initial_cache/README.md)
preserves all six prepared initial searches and a fresh complete DS26-0002 run,
including both arms and all eight PNG bytes. Prepared search averages
**28.792 → 27.950 s**, with CPU **42.795 → 40.529 s**. The complete native pair
nevertheless regresses **244.609 → 301.029 s** (candidate first); unchanged later
stages also slow down. Keep the cache external pending stronger timing evidence.
No production change or cumulative speedup is claimed.

The [covariance-index iteration](../../reports/2026_11_05_algo07v3_posterior_followup/README.md)
is integrated in development. Eight complete slow DS26-0066 training fits are
exact: `c=0` averages **49.519 → 47.269 s (4.54% lower)** and fitted `c`
**63.691 → 59.875 s (5.99% lower)**, with comparable CPU savings. A fresh full
DS26-0002 pair is exact through all science, both arms, eight PNGs and public
grid/path: **312.944 → 232.515 s**. Host variation prevents attributing the full
25.70% reduction to the change. **727 tests pass**. An ordered-assembly candidate
was exact but slightly slower and remains external. Production, full DS26 and
stable cumulative original-ALGO07 qualification remain unchanged.

The external [initial branch-queue experiment](../../reports/2026_11_05_algo07v3_branch_queue/README.md)
preserves six complete DS26-0002 initial-search results. Mean elapsed time is
**26.781 → 25.195 s**, but mean CPU is **38.633 → 41.907 s** and one pair
regresses. It remains external; these are prepared-stage measurements.

The [bounded annotation-training queue](../../reports/2026_11_05_algo07v3_annotation_training/README.md)
is integrated in development and passes a fresh complete DS26-0002 comparison:
both arms, every scientific audit, eight PNG bytes and public grid/path are exact.
Observed native-input-to-publication time is **270.401 → 195.246 s**, with CPU
**374.490 → 255.370 s**. Predictive recovery is **63.668 → 45.856 s**. Unchanged
preparation and initial search also improve, so the overall 27.79% reduction is
not attributable solely to scheduling. The component suite passes 672 tests.
DS26-0066's reversed-order pair also passes exactly: **691.997 → 441.193 s**,
with predictive recovery **304.289 → 164.762 s**. Unchanged downstream stages
also improve; the observed 36.24% reduction is not an isolated scheduling gain.
Production and cumulative/original ALGO07 qualification are unchanged; this is
two-scan development evidence.

The [DS26-0066 predictive profile](../../reports/2026_11_05_algo07v3_predictive_0066_profile/README.md)
matches all scientific audits, both arms and eight PNGs against the unchanged
owned result. Annotation consumes **264.864 of 327.726 profiled predictive
seconds**; one fold dominates. An external paired-training prototype preserves
all six complete fold outputs across three alternating pairs and averages
**99.051 → 51.607 s (47.90% less elapsed)**, with CPU **99.035 → 100.827 s**.
This is one prepared fold, not a complete-pipeline benchmark or deployed change.
Integration must keep at most three active training workers across fold/arm
tasks and pass fresh native comparisons. Complete candidate and cumulative
speedups remain unmeasured for this experiment; the prior unprofiled complete
DS26-0066 result remains 602.497 s.

The [geometry follow-up](../../reports/2026_11_05_algo07v3_geometry_followup/README.md)
passes the complete DS26-0066 comparison, including accepted reassociation,
both arms and all eight PNGs. Total observed time is **667.114 → 602.497 s**,
CPU **977.300 → 830.270 s**. Initial search nevertheless regresses
**120.382 → 204.640 s**; retain that evidence and the changing-host limitations.
The numerical geometry source is unchanged from `7f52d1248`.

An external discovery-scheduling prototype matches all six complete initial
searches on DS26-0002. Three alternating pairs average **20.303 → 18.655 s**
for the entire stage, with CPU **29.855 → 32.304 s**. It remains external:
1.649 seconds saved at an additional 2.449 CPU seconds is not yet a compelling
full-pipeline/queue-throughput improvement. Predictive recovery is the next
profiling target. Production is unchanged.

Latest [fixed-phase position geometry](../../reports/2026_11_05_algo07v3_position_geometry/README.md)
is integrated in development after an exact native DS26-0002 comparison.
Observed full-path time is **258.526 → 188.557 s** and process CPU
**364.570 → 252.550 s**. Both arms, all scientific audits, eight PNG bytes and
publication grid/path match. Unchanged preparation and catalogue loading also
speed up, so the observed 27.06% reduction is not wholly attributable to the edit.
The candidate passes 636 broad tests and 14 overlapping focused tests.
Twelve alternating complete five-round position fits are exact: `c=0` averages
**2.073090 → 1.866552 s (9.96% lower)** and fitted `c`
**2.048970 → 1.856914 s (9.37% lower)**, with comparable CPU reductions.
Those are prepared-fit gains, excluding discovery, recovery and publication.
Production is unchanged; broader branch coverage and stable cumulative timing
remain open. The report separates geometry-only from complete-fit measurements.

The [gate follow-up](../../reports/2026_11_05_algo07v3_gate_followup/README.md)
adds an exact reversed DS26-0002 pair. Full ABBA order is now **281.351 / 315.061 /
229.958 / 316.503 s**. Cross-pair aggregation and the second-scan DS26-0066
comparison pass: all six runs preserve each scan's scientific outputs, both arms
and all eight PNGs. DS26-0066 takes **607.804 → 597.093 s** (10.711 s shorter),
an observation rather than an attributable or dataset-wide speedup.
The 85.103-second variation between
candidate executions precludes attributing the complete difference to gate reuse.
An external, unintegrated fixed-phase geometry probe averages **0.250763 →
0.167064 s per 50 evaluations (33.38% lower)**, with 600 exact component evaluations
and five passing focused tests. This is not a full-fit or pipeline speedup.

Latest [fixed-audit gate reuse](../../reports/2026_11_05_algo07v3_family_gate_reuse/README.md)
reduces the sum of four complete audit means **7.718 → 2.386 s (69.09% lower)**,
with CPU **7.715 → 2.385 s**, across 24 exact alternating executions. Final
scientific audits, both arms and all eight PNGs also match the ordinary candidate.
The fresh full DS26-0002 pair is **281.351 → 315.061 s**, however: **33.710 s
longer**, ratio **0.893×**. Unchanged initial search rises **24.869 → 41.078 s**;
no complete-pipeline speedup is established. The report retains host evidence,
the failed first benchmark's receipt-mutation diagnosis and the corrected rerun.
Production is unchanged; the reversed full pair and second branch case are
reported in the completed follow-up above.

Latest [conservative-arm concurrency](../../reports/2026_11_05_algo07v3_conservative_arms/README.md)
measures **73.595 → 46.980 s (36.16% lower)** for complete prepared conservative
recovery on DS26-0066, across three alternating exact pairs. Parent-plus-child
CPU is **73.507 → 75.042 s**, so this improves latency at a small CPU cost.
The report retains four fresh complete DS26-0002 executions in ABBA order,
with per-stage costs and host evidence; unchanged stages vary materially under
shared-host load. The 940-test suite passes. Production remains unchanged.

The exact ABBA run order is **199.368 / 192.892 / 191.880 / 320.444 s**.
Both candidates are about 192 s; the final baseline slows in unchanged stages.
The first pair saves 6.476 s, but the pooled **259.906 → 192.386 s** average
does not qualify a 25.98% code speedup. All four science/PNG outputs also match
across pairs. Keep these complete-path observations separate from component gains.

Latest [alternating reassociation benchmark](../../reports/2026_11_05_algo07v3_reassociation_benchmark/README.md)
resolves the component timing question: DS26-0066 complete screens average
**16.253 → 11.407 s (29.81% lower)** over three alternating pairs, with CPU
**16.251 → 11.406 s**. All 12 screens and final both-arm science/eight PNGs
are exact. This is about 4.85 seconds of component savings, not a new complete-path
ratio. The previous full-run regression below remains valid evidence. Conservative
profiling identifies 42.765 of 55.625 seconds in paired rejection/refitting;
independent-arm concurrency is the next measured opportunity. Production unchanged.

Latest [reassociation interpolation iteration](../../reports/2026_11_05_algo07v3_reassociation_geometry/README.md)
extends shared orbital interpolation to the two cavity-position arms. Its report
retains a fresh complete DS26-0066 pair, exact comparison, stage costs and host
receipts. This accepted-reassociation case broadens coverage beyond DS26-0002;
926 component tests pass. A single shared-host pair does not establish an
attributable or population speedup. Production remains unchanged.

This pair is **549.558 → 653.906 s (104.348 s longer; 0.840× ratio)** despite
exact outputs. Unchanged predictive and residual-screen stages also slow down
as host CPU pressure rises. No speedup is established for this iteration;
retain the regression and require controlled repeats before a performance claim.

Latest [residual-screen interpolation reuse](../../reports/2026_11_05_algo07v3_screen_geometry/README.md):
three alternating native prepared-screen pairs average **17.997 → 12.203 s
(32.19% lower)**, with exact results throughout. A fresh complete DS26-0002 pair
also preserves both arms, all science, eight PNGs and publication exactly.
Its **250.094 → 210.621 s** observation is confounded by changes in unchanged
stages and host load; it is not an attributable 15.78% pipeline improvement.
918 component tests and three benchmark-tool tests pass. One phase's states
are shared across arms without a persistent cache. Production is unchanged.

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

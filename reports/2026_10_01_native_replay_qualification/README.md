# Reusable native replay qualification

## Latest physical ARM evidence

**The first three-distinct-recording trial fails.** Despite the successful
four-repeat baseline below, the denser `b34e` capture rejects 3/2,218 dwells at
queue capacity 32, losing 25 passing candidates; processed science matches.
The overlapping first downstream chain takes 303.446 seconds. A bounded
queue-48 retry completed all 6,649 dwells without loss, but fails the unchanged
limits: maximum latency 5.479 seconds, loaded downstream times 304.410 and
310.180 seconds. Independent raw-IQ native controls also expose track identities
that change with fit-summary roundoff, altering positioning partitions/results.
See the [mixed-recording report](../2026_10_01_arm_three_scan_sequence/README.md).

**The four-scan queue-32 trial passes its predeclared recorded-load gates.**
All 8,860 dwells and 64,764 positive observations are accounted for, with zero
rejections or failures and matching scientific controls. Three loaded downstream
chains take 297.086, 297.852 and 297.688 seconds and finish before the next scan
is ready. Maximum dwell latency is 2.913 seconds, peak queue usage 21/32, and
peak IQ allocation 22/34 buffers. Sampled aggregate RSS peaks at 242,476 KiB.
The minimum observed downstream margin is only 2.148 seconds. See
[`cadence-four-queue32-v1/`](cadence-four-queue32-v1/README.md) for receipts and plots.
The requested three-distinct-recording extension is complete; its results
and independent server comparisons belong to
[`../2026_10_01_arm_three_scan_sequence/`](../2026_10_01_arm_three_scan_sequence/README.md).
Neither test qualifies simultaneous live RF acquisition.

### Earlier failed and partial qualifications

The optimized queue-16 candidate (`cadence-four-threshold-pgo-v1/`) completes
its first full downstream chain in **297.447 seconds**, with all scientific
controls passing, but rejects **7/2,215 dwells** during scan 1 at 101–125 seconds.
The run fails lossless qualification. Its observer termination and recovered
partial products are retained, without a fabricated successful execution receipt.
Measured-service replay estimates a peak queue of 23–25 during that burst.
`cadence-four-queue32-v1/` tests an explicit bounded 32-dwell queue, keeping the
same science and scheduling. It requires zero drops, at most 5 seconds dwell
latency, and three loaded downstream intervals under the original 300-second
cadence. All 108 benchmark tests pass; the completed physical result is above.

**The first successive-scan test failed.** In `cadence-three-v1/`, the first
scan recovers all 16,191 observations, but the second rejects 13 dwells while
positioning runs. The controller stops explicitly. All processed science is
exact; positioning is cancelled after 396/400 exact points. This supersedes any
inference of sustained throughput from the successful single-interval trial.
`cadence-three-observer-v2/` subsequently completes three fixed-cadence scans
with **48,573 exact positive observations and zero dropped dwells**, and all
downstream controls match. Reduced monitoring overhead is the only execution
change. Loaded downstream jobs take 302.261 and 300.643 seconds; waiting grows
from 2.364 to 2.777 seconds. The finite test passes, but stable longer-run
backlog remains unproven. The final 257.454-second downstream job is an unloaded
drain, not evidence of loaded throughput. The later four-scan test supersedes
that throughput result; distinct-recording qualification is still pending.

Earlier single-interval trial: `fullchain-index-pgo-overlap-v1/` completes downstream
seed generation, tracking, conversion, orbit propagation, 400-point search and
associations in **297.978 s**, while paced GLRT recovers all **16,191** positives
without drops. All checkpoints and downstream controls match; independent
host search tolerance passes. Queue peak is 11/16. The optional catalogue index
and GLRT PGO build are combined in this trial. The 2.022-second margin is narrow:
successive fixed-cadence operation and scan-boundary behavior remain unqualified.
See the successive-scan report for current concurrent timings; the table below retains earlier
isolated measurements.

### Follow-up profiling and tracker builds

`preparation-profile-v1/` measures the public input/selection/location-track
ports without changing production behavior. Three physical ARM runs reproduce
every serialized host location-track value. Mean stage CPU is 0.602 seconds
for observations, 0.293 for support, 0.368 for track parsing, 0.285 for exclusive
selection and 0.647 for location-track construction: about 2.194 seconds total.
Whole-process CPU including diagnostic serialization is 2.422–2.433 seconds.
This bounds the potential gain from optimizing those stages alone.

`curvature-pgo-v1/` trains on source groups from the first 150 seconds and
evaluates disjoint remaining groups, then the full scan. Strict GCC profile-use
checks pass. In control/PGO/PGO/control comparisons, held-out CPU falls from
1.486 to 1.441 seconds; full-scan CPU falls from 3.857 to 3.746 seconds (2.87%).
All track output bytes match the frozen controls, and the PGO core passes its
unit test on ARM. The 0.111-second saving is an isolated result, not a new
cadence qualification.

`seed-current-v1/` rebuilds seed generation against the current tracking core.
All seed outputs remain exact, but matched ARM CPU changes from 3.573 to 3.589
seconds. This does not demonstrate an improvement and is not adopted as one.

`seed-pgo-v1/` then profiles the same seed implementation on the disjoint
training groups used above. Strict profile-use builds pass without suppressing
profile errors. Held-out control/PGO/PGO/control CPU means are 1.281 and 1.189
seconds; full-scan means are 3.601 and 3.307 seconds (8.15% saving). Every seed
output matches the frozen reference exactly. Source snapshots, compiler commands,
profiles, executable hashes, per-run output and timing receipts are retained.
The seed and curvature PGO savings total about 0.404 CPU seconds in isolated
runs; they have not been combined in a new cadence trial and do not establish
sufficient sustained margin. Five preparation/build-recipe tests pass.

`prepared-threshold-v1/` moves vector-bound threshold preparation outside the
satellite loop and refreshes it whenever the incumbent improves. The rejection
formula and final scoring are unchanged. Host and physical ARM component tests
pass; all 400 host search points remain exact. A matched ordinary-build
16-site ARM comparison saves 1.85% CPU (10.973 to 10.769 seconds), with identical
output. Fresh PGO and full ARM/cadence qualification are required before adopting
this change in the paced pipeline.

`prepared-threshold-pgo-v1/` confirms a 1.674% CPU saving on disjoint held-out
sites with fresh PGO and identical output. `prepared-threshold-full-v1/` then
completes the entire in-memory ARM position pipeline in **245.188 wall /
245.159 CPU seconds**, peak RSS 151,676 KiB. All 400 ARM search points are exact,
the direct host tolerance comparison passes, and final associations match host
bytes. This isolated result still needs loaded qualification. The four-scan
candidate in `cadence-four-threshold-pgo-v1/` combines this scorer with seed and
curvature PGO; its acceptance criteria explicitly exclude the unloaded drain
from throughput evidence.

The recorded local-IQ → GLRT → observations/support → tracks → regional
position selection → full associations chain has run on PLUTO+. The goal
remains incomplete: **continuous combined cadence has not been demonstrated**,
and native tracking is not identical to server tracking.

| Stage | Wall seconds | CPU seconds | Evidence |
|---|---:|---:|---|
| Paced recorded detection/projection with IQ reuse and batch support cache | 300.851 | 279.316 | `recorded-batch-support-v1/` |
| Coarse seed + tracking | 7.420 | 7.417 | `fresh-graph-tracking-v1/` |
| Native orbit authority | 5.287 | 5.275 | `native-orbit-authority/` |
| Exclusive-track location input | 5.400 | 3.440 | `fresh-graph-location-v1/` |
| Full 400-point regional search, optional vector bound | 142.217 | 270.442 | `regional-arm-vector-pair-v1/` |
| Full associations at selected site, vector build | 2.356 | 3.595 | `regional-arm-vector-pair-v1/` |

These are separate runs, not a concurrent pipeline benchmark. Their CPU sum
is about 569.5 seconds per scan, leaving about 30.5 CPU seconds beneath
the theoretical 600 available on two cores in 300 seconds. This is not a
usable demonstrated concurrency reserve. Short newer research benchmarks are
reported below and do not replace the full-run measurements in this table.
The report's earlier sections retain development history and narrower scopes.

The optional vector pair-bound build saves 9.05% search CPU versus the preceding
scalar PGO build (297.359 CPU / 158.116 wall seconds), with full 400-point ARM
JSON and final associations unchanged. The independent host comparison passes
the predeclared 1e-9 Hz tolerance, and selected host association JSON is exact.
Search RSS grows from 79,748 to 120,772 KiB. This is an explicit research option;
scalar remains the build default. See `vector-pair-pgo-v1/README.md` for training,
tests, hashes and limitations. The full search still exhausts its 400-point
budget, which does not demonstrate global convergence.

The subsequent `overlap-vector-pair-v1/` concurrent trial still fails: 14/2,215
dwells are rejected, with 16,068 positive observations. Every processed result
and emitted observation/support row remains exact. Search takes 301.591 wall /
289.167 CPU seconds; detection takes 301.076 wall / 293.784 CPU seconds.
The full search remains exact against isolated ARM and passes host tolerance.
Auxiliary stages are excluded, so this is not sustained full-chain qualification.

`overlap-vector-single-v1/` changes the vector search to one worker. It rejects
5/2,215 dwells (16,156 positives), retaining exact processed science, but search
takes 317.171 wall / 303.787 CPU seconds. This also fails. Per-context endpoint
caches mean the worker-count change reduces aggregate cache capacity; it does
not isolate scheduling from cache effects. The checkpoint comparator now
explicitly reports missing IDs and fails incomplete lossless comparisons.

The matched ordinary single-worker cache experiment (`vector-bank-capacity-v1/`)
saves 8.647% CPU on 16 held-out sites with a 128 MiB endpoint-bank limit versus
64 MiB, retaining exact scores and the full host trace. Fresh single-worker PGO
then yields `overlap-vector-bank128-v1/`: search completes in 283.411 wall /
270.163 CPU seconds, with 120,624 KiB peak RSS. Detector rejects 3/2,215 dwells,
emits 16,161 positives, and consumes 288.127 CPU seconds. All processed science
and the full ARM search are exact; host tolerance passes. This is improved
search cadence but still not lossless, and excludes auxiliary stages. Next
evaluate bounded burst buffering before a full-chain sustained replay.

**Lossless single-scan overlap:** `overlap-vector-queue16-v1/` increases only the
detector queue limit to 16. All 2,215 dwells and 16,191 positive observations
match, with zero drops and a queue peak of 9. Maximum arrival-to-finish latency
is 1.353 seconds. Search takes 283.611 wall / 270.290 CPU seconds; detection
takes 300.885 wall / 289.205 CPU seconds. Peak RSS is 120,624 / 50,436 KiB
respectively. The full search matches ARM and passes host tolerance. This is
the first lossless overlap in this experiment series, but still excludes
auxiliary stages and successive scans; the full sustained gate remains open.

Two integrations now prepare that full-chain test. `search-associate-v1/`
reuses the scorer for full selected-site associations and preserves all ARM
search and association results exactly: 245.042 wall / 245.017 CPU seconds
in isolation, including 1.367 wall seconds for final associations. This uses
one worker and is not the earlier two-worker timing shown in the stage table.
`direct-orbit-authority-v1/` generates LOC1 authority directly from TLEs on ARM
(5.407 wall / 5.335 CPU seconds), then converts the measured tracks locally
(3.746 wall / 3.429 CPU seconds). Orbit states and track evidence remain exact;
the authority deliberately contains one diagnostic site instead of two.
No host-side packaging is needed for this connection. These isolated results
do not yet include auxiliary work in the successful concurrent queue16 test.

**Full-chain overlap now measured:** `fullchain-overlap-v1/` regenerates seeds,
tracks, orbit authority, converted input, search and full associations alongside
paced GLRT. All downstream results match the qualified controls, but the chain
takes 304.103 seconds and detection rejects 13/2,215 dwells (16,087 positives,
queue peak 16, maximum latency 2.640 s). Thus adding auxiliary stages breaks the
previous lossless result. Early queue buildup motivates native memory ports
that remove intermediate orbit/LOC1 I/O; the current evidence does not isolate
disk, memory and scheduling effects. The sustained full-chain gate remains open.

`memory-session-v2/` establishes the typed borrowed orbit/track search boundary.
The CLI delegates to the same file-free session, preserving both complete host
traces and final associations exactly. DS9 integration, sanitizer checks and
physical ARM component tests pass. Direct orbit/track-conversion composition
and a new full-chain ARM timing are still pending; no throughput improvement
is claimed for this boundary alone.

`fullchain-memory-overlap-v1/` now connects the ports and removes orbit/LOC1
intermediate files. All 16,191 observations are exact with zero drops, queue
peak 14/16 and maximum latency 1.975 s; tracks, search and associations remain
exact against their controls. The full downstream chain takes **302.385 s**,
still **2.385 s over cadence**, so sustained operation remains unqualified.
Positioning peak RSS is 151,584 KiB, including the retained orbit context.
See `in-memory-position-v1/` for the component interfaces and host checks.

**Concurrent scheduling result:** `overlap-fair-v1/` ran the qualified paced
detector with the preceding location build (before prevalidated stencils).
The latest-build repeat is recorded below as `overlap-prevalidated-v1/`.
The original trial ran the
detector and two-worker regional search simultaneously at equal nice priority.
It rejected 430 of 2,215 dwells (19.4%) when the eight-entry queue filled.
All processed candidates and emitted observation/support rows matched their
controls, but only 12,861 positive observations were emitted. This fails the
lossless requirement. Search still reproduced its isolated ARM JSON exactly
and passed the independent host tolerance comparison for all 400 points.

Search took 270.259967 wall / 318.738530 CPU seconds (79,940 KiB peak RSS);
detector took 300.824033 wall / 233.183261 CPU seconds (47,956 KiB peak RSS),
with exit code 3 explicitly reporting rejected work. Detector arrival-to-finish
latency reached 2.179 seconds. Its lower CPU time reflects dropped work and
must not be reported as an optimization. These are per-process RSS values,
not a sampled aggregate memory peak.

This experiment uses a prior qualified scan's location input while processing
the recorded IQ; it excludes tracking, orbit generation, conversion and final
associations, and is not a sustained end-to-end test. The next scheduling
experiment should retain detector priority and lower search priority, measuring
both lost work and positioning backlog. `tools/run_arm_overlap.py REPORT`
reproduces the two pinned workloads from the report's predeclared protocol;
use a new report and unique device output paths for each trial. Nine harness
tests cover protocol bounds and concurrent launch with independent outcomes.

`overlap-priority-v1/` then kept detector nice 0 and lowered search to nice 10,
with identical pinned binaries and inputs. Rejections fell to 44/2,215 (2.0%),
but the eight-entry queue still filled. It emitted 15,794 positive observations;
all processed candidates and emitted observation/support rows remained exact.
Maximum arrival-to-finish latency was 1.464 seconds. Detector took 301.757545
wall / 286.149398 CPU seconds with 50,236 KiB peak RSS. Search took 313.766930
wall / 320.703287 CPU seconds with 79,940 KiB peak RSS, retaining exactly the
isolated ARM 400-point result and passing the independent host comparison.
Thus priority alone fails lossless pacing and search already exceeds one scan
interval, before auxiliary stages. Neither overlap trial qualifies deployment
as a sustained real-time pipeline.

`overlap-prevalidated-v1/` repeats the nice-0 detector / nice-10 search test
with the newly qualified prevalidated-stencil location binary. It still
rejects 46/2,215 dwells (10, 26, 10, 0 by quarter), emitting 15,830 positive
observations. Every processed candidate and emitted projection row remains
exact, as does the full search result; the independent host comparison passes.
Search takes 312.566576 wall / 317.385044 CPU seconds (79,728 KiB peak RSS),
and detector 301.583533 wall / 287.152842 CPU seconds (50,244 KiB peak RSS).
Maximum arrival-to-finish latency is 1.477 seconds. This confirms that the
small isolated saving has not supplied useful lossless scheduling margin.
The diagnostic harness now supports explicit two-core CPU masks independently
of nice priority, with 13 tests; this run did not select an affinity mask.

`overlap-nice19-v1/` lowers search to nice 19 with affinity unchanged. Losses
fall to 4/2,215 dwells, leaving 16,157 of 16,191 observations. All processed
candidates and emitted observation/support rows remain exact. Search equals
the isolated ARM JSON and passes the independent host comparison (maximum
intermediate difference 5.684e-13 Hz). Detector takes 301.265813 wall /
289.631358 CPU seconds; search takes 314.504978 wall / 317.366716 CPU seconds.
Maximum detector arrival-to-finish latency is 1.391 seconds. This still fails
both lossless detection and the 300-second search interval, before auxiliary
stages. Priority helps protect detection but does not supply compute capacity.

`overlap-affinity-v2/` pins the detector process (reader and worker threads)
to CPU 0, keeping search nice 19 and free to use both CPUs. It rejects
47/2,215 dwells, emitting 15,793 observations; every processed candidate and
emitted observation/support row remains exact. Detector takes 301.572440 wall /
284.581337 CPU seconds, with maximum arrival-to-finish latency 1.436 seconds.
Search takes 312.688250 wall / 320.211639 CPU seconds and preserves the isolated
ARM result exactly, passing the independent host tolerance comparison.
This affinity setting is rejected: it does not improve lossless cadence and
the shorter search time accompanies more dropped detector work. These single
trials establish failures, not statistically precise scheduling speedups.

The first affinity attempt (`overlap-affinity-v1/`) could not start detection
because this firmware lacks `taskset`; its search was explicitly terminated.
It is excluded from timing comparisons. `tools/native_affinity.c` supplies a
narrow launcher that verifies the requested CPU mask before exec. The harness
now requires its hash in the protocol and preflights it before measured jobs
start. Fifteen host tests pass, and a physical ARM probe confirms CPU 0.
The corrected trial retains the launcher binary, source and build receipt.

| Concurrent trial | Dropped dwells / 2,215 | Positive observations / 16,191 | Search wall seconds |
|---|---:|---:|---:|
| Earlier search build, equal priority | 430 | 12,861 | 270.260 |
| Earlier search build, search nice 10 | 44 | 15,794 | 313.767 |
| Current search build, search nice 10 | 46 | 15,830 | 312.567 |
| Current search build, search nice 19 | 4 | 16,157 | 314.505 |
| Current search build, search nice 19, detector CPU 0 | 47 | 15,793 | 312.688 |

All rows exclude tracking, orbit generation, location-input conversion and
final associations. No row qualifies sustained end-to-end operation. Reduce
compute cost before attempting the complete successive-scan qualification;
neither priority nor this affinity experiment has supplied enough capacity.

`pair-multiply-v1/`, `pair-reciprocal-v1/` and `pair-prepared-v1/` compare three
small bound-arithmetic variants against matched ordinary builds. Multiplying
the guarded threshold costs 0.70% more CPU and is rejected. A conservative
reciprocal reused only across time offsets saves 0.22%; preparing it once per
track outside the satellite loop saves 0.82%. All evaluated scores remain exact.
The last variant preserves both complete host search traces and passes host,
physical ARM and sanitizer checks of the changed bound helper, including
200,000 randomized conservative-rejection cases. The reciprocal is rounded
inward by a 2^-48 relative allowance; full scoring remains unchanged.

`pair-prepared-pgo-v1/` retrains the changed scorer on four sites, then measures
the same sixteen disjoint evaluation sites in control/new/new/control order.
All scores match, with mean CPU 12.237275 → 12.188854 seconds (0.40% reduction).
Core, stencil and immutable-session tests pass on physical ARM. Full isolated ARM
qualification in `regional-arm-pair-prepared-v1/` preserves all 400 ARM search
evaluations and full selected-site associations exactly. The independent host
search comparison passes its 1e-9 Hz policy; full associations equal host.
Search takes 158.115778 wall / 297.358715 CPU seconds; associations take
2.154077 wall / 3.264946 CPU seconds. Peak RSS is 79,748 / 72,936 KiB.
This is only a 0.922 CPU-second search saving relative to the prior isolated
run. It does not clear the concurrent failures or establish sustained cadence.

`glrt-sampling-v1/` profiles the unchanged qualified detector over 32 evenly
spaced recorded dwells repeated eight times. All 256 scientific outputs match
their saved references; 5,275 samples are collected without loss. A debug build
has byte-identical machine code and matching text-section addresses, allowing
source attribution of those samples. Repetition is for profiling only.

Three subsequent bounded experiments are rejected: integer-square input energy
saves less than 1% in its microbenchmark, a local running-prefix variable costs
about 6% more, and a measured 5,000-point FFT plan costs about 40% more while
changing FFT values slightly. Evidence is in `ci16-energy-v1/`,
`ci16-prefix-register-v1/` and `fine-fft-plan-v1/`. The original input-preparation
header is restored byte for byte; new component-owned CI16 conversion/prefix
tests remain and pass. No detector deployment or FFT policy changed.
Source-level sampling identifies repeated received-energy accumulation in
conditioned scoring as the next target: 234 samples fall there, versus 28 in
fine-FFT received energy. Investigate reuse of the already-computed CI16 energy
prefix under an explicit provenance contract, preserving exact values and
falling back for other inputs. A gain has not yet been demonstrated.

`ci16-window-energy-v1/` and `ci16-window-energy-v2/` then test that hypothesis.
The integer-energy proof is verified on host and ARM, including offset slices
and prefixes near its 2^22-source-sample limit. Both variants preserve every
tested scientific field against the saved DS9 reference. However, ordinary
matched ARM control/new/new/control measurements show no useful detector gain:
the first variant costs 0.16% more call CPU; separating the fast loop saves only
0.072%. Both are rejected and production sources restored. The next substantial
target is the repeated Doppler-bound computation in regional search, rather
than further input-loop micro-optimization. Continuous qualification stays open.

Build-receipt inspection identified the next compute experiment: the qualified
ungated GLRT archive in `../2026_10_01_arm_glrt_missing_diagnosis/build.json`
uses `-O3` but no `-fprofile-use` on any compiled translation unit. Test PGO
training for this ungated source while preserving its detector policy and
holding out evaluation recordings/visits. The older gated PGO archive is not
a substitute; its scientific mismatch is preserved in `iq-reuse-arm-v1/`.

`ungated-glrt-pgo-v2/` now records this experiment: 16 training visits and 32
disjoint heldout visits from the scan's sole template context, with
control/PGO/PGO/control evaluation. All scientific candidates remained exact.
Mean call CPU improved only 0.98% (101.363 to 100.373 ms). The initial launcher
incorrectly assumed two contexts; that failed attempt and corrected clean
profile collection are preserved. The PGO archive is retained for full-scan
qualification, but this short benchmark does not establish a deployment gain
or solve the demonstrated concurrent scheduling failure.

`horizon-mask-v1/` records a subsequently rejected location optimization:
packing short horizon histories into one 64-bit mask preserved both complete
host traces and all tested ARM scores, but cost 1.30% more CPU than its matched
ordinary control (and 3.71% more than the best PGO scorer). The qualified prefix
implementation was restored to its original source hash. Expanded boundary
tests remain; the unsuccessful prototype and measurements are preserved.

`location-sampling-v3/` documents subsequent bounded CPU sampling. The original
single-worker PGO executable yielded 11,860 samples with none lost; a separate
debug build yielded 11,862 for source-level attribution. Completed partial
search traces remained exact. Bound evaluation, stencil interpolation and
repeated finite checks dominate, directing the next experiment toward reusable
validation within the explicit immutable orbit session. These deliberately
60-second partial profiles are not throughput measurements or complete runs.

## Bounded IQ-buffer reuse experiment

`iq-reuse-arm-v2/` records four original-cadence 64-dwell ARM trials in
fresh/reuse/reuse/fresh order, using the same qualified ungated detector archive.
Mean whole-process CPU time fell from 8.733 to 8.219 seconds (5.9%); wall time
stayed about 8.98 seconds because arrivals were paced. Reuse needed two IQ
allocations instead of 64. Every candidate, observation and support graph matched
the qualified control exactly, with no failed or rejected dwell. This short
experiment alone does not establish full-scan savings or sustained throughput.

The pool is bounded by queue capacity plus the producer and worker buffers.
It recycles each buffer only after the detector's const borrow finishes; full-IQ
reads overwrite the entire buffer, while prefix reads retain a zeroed unused
tail. Component tests cover both modes, overloaded queues and execution flags.
`iq-reuse-arm-v1/` preserves a rejected initial build accidentally linked to the
older gated archive; its failed scientific comparison disqualifies that run.

`recorded-reuse-v1/` subsequently qualified the full 2,215-dwell original-cadence
replay on PLUTO+ at 192.168.1.15. Every raw candidate matched the frozen ungated
ARM control, and all 16,191 observations and their support graph matched the
previous qualified checkpoint byte for byte. No dwell failed or was rejected.
Whole-process CPU fell from 306.134691 to 288.356006 seconds (5.807%); paced
wall time was 300.871800 seconds. This full-scan comparison uses the earlier
qualified run as its control; the short experiment above provides same-build
alternating controls. Peak RSS was 40,924 KiB. Six buffers served all dwells,
with peak queue depth five of eight; mean queue delay by scan quarter was
25.26, 164.69, 15.30 and 4.94 ms, recovering after the busy second quarter.
Maximum arrival-to-finish latency was 766.79 ms. These results exclude
concurrent tracking and positioning and do not establish sustained throughput.

Measured thread CPU was 267.799 seconds inside the detector, 8.902 seconds
inside projection, and 6.193 seconds inside input reads/allocation. These
scopes exclude some setup, serialization and teardown, so they do not sum to
whole-process CPU. The separate-stage total is still about 610 CPU seconds
per scan; further savings and a shared-budget replay remain necessary.

## Single-worker regional scheduling experiment

`regional-arm-single-worker-v1/` pins the same immutable-session PGO binary,
fresh native 80-track input and 400-point search policy, changing only worker
count from two to one. The complete search JSON and full selected-site
association JSON are exactly equal to the qualified two-worker ARM control.
The independent host comparison also passes the predeclared 1e-9 Hz tolerance
(maximum intermediate score difference 5.684341886080801e-13 Hz, selected score
exact). Search still exhausts its 400-point budget; this is not convergence.

| Workers | Search wall seconds | Search CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Two | 160.054509 | 302.045997 | 79720 |
| One | 316.645895 | 316.626390 | 61968 |

One-worker final full associations took 2.755863 wall / 2.755350 CPU seconds.
The current one-worker configuration exceeds a scan period for search alone,
so it is not adopted for combined replay. Worker count also changes total
endpoint-cache capacity (32 MiB per context); this experiment does not isolate
threading overhead from cache effects. It establishes deterministic results
across the supported worker counts on this fixture, not concurrent throughput.

## Support geometry hoisting

`support-geometry-hoist-v1/` preserves before/after runtime sources and an ARM
control/optimized/optimized/control benchmark using all 16,191 passing DS9
integer epochs. Symbol boundaries are now computed once per support derivation
instead of once per frame. Retained-center order, rounding and binary64 moment
accumulation remain unchanged. All emitted support rows are byte-identical.
Mean support-CLI CPU fell from 12.2092195 to 9.136119 seconds (25.17%). This
includes CLI parsing/formatting and is not the projection stage measurement;
do not subtract this saving from the full-pipeline table without replaying it.
Component tests include an independent closed-form single-frame check and
Python geometry comparisons at 0.75, 2.5 and 10 MS/s, including probe-end cases.

`recorded-support-hoist-v1/` subsequently measured the optimization in the full
original-cadence ARM replay. All 2,215 raw candidate inventories matched the
qualified ungated control; all 16,191 observations and support graph records
were byte-identical to `recorded-reuse-v1/`. No failures or rejections occurred.
Wall time was 300.843785 seconds, whole-process CPU 283.617863 seconds, and peak
RSS 36,268 KiB. Four IQ buffers sufficed, with peak queue depth three of eight.
Mean queue delays by quarter were 16.28, 57.36, 10.02 and 3.41 ms; maximum
arrival-to-finish latency was 521.09 ms.

Projection thread CPU fell from 8.901776 to 6.554485 seconds. The larger
4.738143-second whole-process reduction also includes variation in detector
and input-read timings; it must not all be attributed to geometry hoisting.
The updated separate-stage CPU sum is about 605 seconds, still above the
theoretical two-core scan budget, without concurrency overhead or reserve.
76 replay/protocol/runtime component checks passed before this run. This
remains single-scan recorded replay, not sustained combined qualification.

## Batch-owned support cache

`ProjectionBatch` memoizes at most 16 geometries, keyed by rate, integer epoch
and exact fractional-offset bits. Each direct detector projection owns a fresh
batch. It validates every source/candidate and regenerates identities, UTC
mapping and measurements even on cache hits. Workers do not share a cache;
capacity overflow only recomputes geometry. Published persisted contracts and
the existing uncached projection function are unchanged.

`recorded-batch-support-v1/` pins the compiled sources and binary and records a
full original-cadence PLUTO+ replay. All 2,215 dwells completed without failure
or rejection; raw candidates matched the qualified ungated archive exactly,
and all 16,191 observations and support records remained byte-identical.
Whole-process CPU was 279.315809 seconds, wall 300.850548 seconds, peak RSS
36,432 KiB. Projection thread CPU fell from 6.554485 to 2.437494 seconds;
detector CPU was nearly unchanged at 265.634696 seconds. Peak queue depth was
three of eight, using four IQ buffers. Mean queue delay by quarter was 17.76,
17.77, 6.74 and 2.47 ms; maximum arrival-to-finish latency was 554.68 ms.

85 host checks passed. ASan/UBSan runtime and direct-projection checks passed,
including cache-hit validation, changed source identities, rate/epoch/offset
keys, eviction, independent owners, and dual-RX identity/CFO preservation.
The separate-stage CPU sum is now about 601 seconds. This provides no reserve
and is not sustained qualification; the next benchmark must exercise the
combined workload and measure actual contention and scan backlog.

## Initial reusable tracker qualification

The new host runner executes the five frozen native tracker implementations
through explicit recipes and immutable detection checkpoints. It contains no
imports from report directories or legacy reference repositories.

Three repetitions of each tracker reproduced its frozen track output exactly;
coarse seed output also matched exactly. The independent evaluator reproduced:

| Method | Strict represented /62 | One-to-one /62 | Output hypotheses |
|---|---:|---:|---:|
| Rolling | 43 | 43 | 542 |
| Kalman v2 | 24 | 23 | 128 |
| Linking v2 | 44 | 40 | 128 |
| Coarse-seeded | 55 | 45 | 80 |
| Rolling-backfill | 50 | 50 | 542 |

Duration buckets and unsupported-output counts also matched the prior comparison.
Reference #10 is explicitly excluded; the published reference fixtures are not
modified. Exclusion occurs before one-to-one assignment in the reusable evaluator.
The evaluator retains all-reference support as a separately labeled diagnostic.

Portable contract tests cover changed input hashes, forward dependencies,
unsupported execution settings, failing commands, malformed/nonfinite output,
timeouts, accidental input mutation, expected-output mismatch, invalid IQ byte
geometry, preserved raw CFO, alias consistency, and the distinction between
coverage and purity. Run `PYTHONPATH=src python -m pytest -q
tests/native_adaptive/replay`.

`release/` records the qualified runs, explicit plans, binary and input hashes,
per-stage process and algorithm timing, independent evaluations, and summary.
Root-level and `final/` runs are retained as initial development evidence. This is host-side
replay qualification, not a new physical ARM performance measurement.

The GLRT and location CLI recipes are boundary adapters with portable recipe
tests; a full new IQ-to-position replay through these adapters is not qualified
by this tracker comparison. See `../../docs/native-pipeline-replay.md` for the
delivered scope and remaining integration gates.

## Integer observation projection

`projection-qualified/` contains the source-owned projector's replay of all 2,215
saved detector dwell results. Both `observations.tsv` (16,191 candidates) and
`candidate-map.tsv` are byte-for-byte equal to the frozen full-scan products;
`frozen-comparison.json` records both checks. `support.json` adds original sample
counter ranges and factorial support moments for subsequent positioning adapters.
No source fixture was changed. Receipt hashes identify projector and adapter code.

The component test suite now has 24 passing tests, including large-counter time
translation, exact acceptance threshold/rank behavior, source identity stability,
invalid and incomplete candidates, support truncation, capture authority mismatch,
and distinguishing missing receiver results from a valid empty detection.

Reproduce with:

```sh
PYTHONPATH=src python tools/project_native_glrt_archive.py \
  reports/2026_10_01_arm_ungated_full_scan/arm /tmp/new-projection \
  --capture-digest sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015
```

This verifies saved GLRT-result projection, not a fresh IQ-to-position replay.

## Chained replay and physical native track port

`projection-chain-qualified/` runs archive projection, coarse seed generation,
and coarse-seeded reconstruction as one runner plan. Both projection products,
seed output, and final tracks match frozen hashes. The runner tests now total
27 passing cases, including multi-output dependencies, absent outputs and path
escape rejection. The earlier `projection-chain/` retains the failed attempt
that exposed virtualenv symlink resolution; the runner now preserves executable
path spelling while checking its content digest.

`modular-track-port-v1/receipt.json` qualifies the native supplied-track parser
against all five complete DS9 outputs on host and physical PLUTO+ 192.168.1.15.
Host and device report identical track/used-candidate counts (542/5775,
128/2629, 128/4359, 80/5254, 542/6896). Native unit tests pass on host, under
ASan/UBSan, and on the physical ARM. Build logs and source hashes are retained.
The diagnostics live under `/mnt/glrtbench/modular-track-port-v1`; no RF was
collected and the production scanner was not changed.

This proves the supplied-membership boundary, not location accuracy or sustained
throughput. The existing location CLI no longer has to rerun its default tracker
when `--tracks` is supplied. Correctly timed orbit authority, hypothesis conflict
handling, full scoring comparisons, and paced ARM execution remain outstanding.

## Capture-specific location authority and scoring

`location-authority/` is a read-only export of the published server location
result for the actual `scan-fw-f363c7f29141d0b1` capture. It pins the capture
digest, origin 1790590660968615222 UTC ns, and TLE snapshot
`sha256:43fd7007b48da10bcc1c6ef0b79e44cda460b27289639557c2d68b0e01abe990`.
The response-independent validity screen retains 11,128 satellites. The exported
orbit bank spans -60 to 360 seconds in 10-second steps. `authority.loc1` contains
zero track memberships; `published-reference.loc1` contains the server's 59
eligible location tracks for a separate control. Those 59 tracks are the published
location pipeline's selection, not the 62-reference frozen tracking benchmark.

At both published selected comparison sites, the native scorer using those
published memberships chooses exactly the same satellite and tau for all 59/59
tracks. Aggregate score differences are +0.00154386 Hz (Sacramento prior) and
+0.00343811 Hz (Reno prior); maximum individual RMS differences are 0.0652 and
0.0818 Hz. These are measured interpolation differences against the independent
published result, not bitwise server parity or a newly estimated location.
`published-location-comparison.json` records every association comparison.

`coarse-location-input/` binds all 80 current coarse-seeded hypotheses to the
capture-specific authority, using the reusable pure support adapter and native
supplied-membership port. Its overlap audit identifies 226 reused detections.
The two raw-hypothesis aggregate scores (416.50 and 406.89 Hz) must therefore
remain diagnostics; no independent-evidence or physical-fix claim is made.

`modular-location-port-v1/` records physical ARM qualification on 192.168.1.15:
the generated LOC1 bytes equal the host output, and all three full-catalogue
fixed-site scoring runs match the host JSON exactly. Two-worker whole-process
times are 28.7174, 28.7112, 28.6950 seconds; median 28.7112 seconds, peak RSS
24,660 KiB. This is two sites, not a 400-point regional search. It excludes orbit
generation, IQ acquisition and concurrent backlog effects. No new RF was collected.

The replay component suite now has 31 passing tests. The new location authority
tests reject cross-capture bindings, wrong epochs, and duplicate support records.
Remaining required gates include conflict resolution, native orbit generation
for this capture, fresh IQ-to-location replay, regional-search comparison, and
paced sustained ARM execution with acquisition-style queues and complete timing.

## Native orbit bank and exclusive candidate policy

`modular-orbit-v1/receipt.json` verifies native host and physical ARM propagation
for all 11,128 selected satellites at 43 epochs against the independently exported
server states. The predeclared tolerances are 1e-6 km in position components and
1e-8 km/s in velocity components. ARM maximum errors are 1.9253e-10 km and
1.9895e-13 km/s. Whole-process runtime is 5.2871 seconds, peak RSS 58,852 KiB.
The initial download needed a local ownership correction; device output hashes
were checked and the original successful propagation was retained. The catalogue
eligibility list still comes from the server's response-independent screen.

`native-orbit-authority/` uses those actual ARM-generated state bytes, retaining
the pinned capture epoch, ordered catalogue and knot grid. The optional native
`exclusive-candidates-longest-v1` policy removes 226 repeated memberships and
three points in insufficient fragments from the raw coarse-seeded hypotheses.
`exclusive-location-input/` contains 80 resulting fragments and 5,251 unique
candidate memberships, with a candidate-level sidecar for audit. Original tracker
artifacts remain unchanged. Distinct candidate IDs can still represent correlated
signals; this policy is not a proof of independent physical tracks.

The two host comparison-site scores are 390.6225 and 381.9999 Hz. Policy changes
also change derived track identities and held-out masks, so the score difference
cannot be attributed solely to duplicate removal. This remains fixed-site
scoring, not a regional search or position fix.

`modular-exclusive-location-v1/receipt.json` qualifies this path on physical
PLUTO+ 192.168.1.15. Location input bytes and candidate membership sidecars match
the host exactly. All three scoring outputs match host JSON exactly; runtimes
are 27.5487, 27.6130 and 27.4613 seconds (median 27.5487), peak RSS 24,660 KiB.
Reproduce after generating the named inputs and building the ARM adapter with:

```sh
PYTHONPATH=src python tools/qualify_native_location_port.py \
  reports/2026_10_01_native_replay_qualification/NEW-DIAGNOSTIC-NAME \
  --exclusive-candidates
```

The destination must be fresh. This command uses the explicitly authorized
device and recorded artifacts only; it performs no RF collection.

The replay tests now total 35 passing cases. Native pipeline host and sanitizer
tests pass, and the ARM cross-build succeeds. Twelve orbit CLI rejection cases
also pass, covering malformed inputs and invalid geometry without publishing a
state file. Regional search, fresh IQ integration and paced sustained execution
remain required qualification gates.

## Full regional search controls

`regional-published-sacramento-v1/` and `regional-published-reno-v1/` run the
complete 400-point native host search from each original regional center and
radius, using the 59 published memberships as an explicit oracle control. Both
visit exactly the same 400 sites in the same order as the independent published
server trace, choose the same grid point, and retain the same deferred-cell count.
Maximum common-site score differences are 0.0183324 Hz and 0.0171284 Hz;
selected-site differences are 0.00154386 Hz and 0.00343811 Hz. This is measured
agreement with the server, not bitwise score equality.

Host elapsed times are 62.10 and 68.25 seconds. The Reno run overlapped a separate
ARM-membership host search, so these are diagnostic elapsed times, not isolated
performance benchmarks. All searches preserve `complete=false` and
`stop_reason=point-budget-reached`; executing the full configured budget is not
global convergence. `tools/qualify_native_regional_search.py` records exact
commands, input hashes and the full evaluation inventory. Component tests verify
use of the prior center, rejection of incomplete evaluation counts, and matching
coordinates before comparing trace scores.

`regional-exclusive-sacramento-v1/` repeats the same 400-point search using the
80 ARM-derived exclusive fragments and the actual ARM-propagated orbit bank.
It selects east=-75 km, north=-75 km instead of the server's (-81.25,-68.75),
an 8.84 km separation in the regional plane. Its score is 382.5362 Hz and its
deferred-cell count is nine higher. Host elapsed time is 107.78 seconds with
the concurrent control noted above. This exposes a real remaining end-to-end
agreement gap: matching the search implementation does not make changed tracker
memberships and their derived partitions reproduce the server position result.
The score difference is descriptive across different evidence sets, not an
accuracy or significance measure. ARM regional runtime remains unqualified.

## Why the ARM tracks select a different point

`position-choice-diagnosis-v1/` scores both unchanged evidence sets at the two
selected Sacramento-region points. Only receiver sites change in these
evaluation-only fixtures; memberships, measurements, training masks, weights and
orbit banks are preserved. The published evidence prefers its original point
(283.8213 versus 285.5568 Hz); ARM evidence prefers its own point (382.5362 versus
390.6225 Hz). Thus the difference is present in the objective, not merely caused
by different search exploration. Neither point is established as physical truth.

Three ARM fragments contribute -5,972.69 of the net -6,251.98 weighted squared-Hz
preference for the ARM point (95.5%, with other fragments partly cancelling).
Their satellite IDs remain unchanged between the two sites:

| ARM fragment index | Satellite | ARM support (s) | Published same-association support (s) |
|---|---:|---|---|
| 15 | 67051 | 46.82–107.23 | 53.57–93.96 |
| 21 | 67042 | 168.95–224.44 | 197.67–228.25 |
| 7 | 59618 | 92.03–163.19 | 88.24–134.85 and 101.33–135.98 |

These are location-input indices, not frozen tracking-reference numbers.
Same satellite association alone does not prove matching detections. Support,
membership and partition differences remain to be separated experimentally;
the comparison does not justify deleting these fragments or treating the server
as ground truth. Full per-track capped-objective contributions and support
summaries are saved alongside the score outputs. Their contributions reconstruct
the aggregate score difference. Reproduce with:

```sh
PYTHONPATH=src python tools/diagnose_native_position_choice.py \
  --binary /var/tmp/leo-modular-location-host/leo-location \
  --qualification reports/2026_10_01_native_replay_qualification \
  reports/2026_10_01_native_replay_qualification/NEW-CHOICE-DIAGNOSTIC
```

Component tests cover fixture-tail preservation, capped contribution accounting,
score dimensions, and site geometry. No reference location enters runtime search.

## Fresh recorded-IQ staging

`iq-staging-export.json` records a read-only export of all 2,215 full dwells
(5,316,000,000 bytes) to `/var/tmp/leo-modular-ds9-iq-v2`. Every visit's event and
raw SHA256 match the independent frozen inventory. Export took 23.03 seconds.
`tools/export_native_replay_iq.py` is corpus evaluation infrastructure, not an ARM
runtime storage dependency. The initial empty v1 directory came from a mistyped
session argument; no recording was modified.

`iq-staging-smoke-v2/` transfers the first two verified dwells to an exclusive
PLUTO+ diagnostic directory, verifies binary/template/IQ hashes, and executes
with local device IQ. Both receivers' scientific detector rows match the frozen
qualified output exactly. Call times are 114.83 and 94.94 ms. The initial v1
comparison incorrectly included row `timings_ms`; the corrected comparison
excludes only that telemetry field, with a component test proving CFO changes
still fail equality. Both raw runs remain available for audit.

This two-dwell smoke check is a staging prerequisite, not full-scan or paced
qualification. The full corpus is on the host; only these two dwells were copied
to PLUTO+. A persistent bounded native replay executor and full local device
staging remain necessary before measuring acquisition-cadence queue behavior.

## Bounded recorded-arrival executor

`native/adaptive/bench/recorded_paced.cpp` uses the existing one-worker bounded
executor with at most two persistent detector contexts. The explicit five-column
manifest carries sequence, relative arrival nanoseconds, exact/control template
paths and local IQ path. It reads each full dwell at its recorded arrival, owns
only queued/running/current IQ buffers, frees consumed or rejected buffers, and
reports storage time, producer lateness, queue/service/finish latency, peak RSS,
rejections and candidate fields needed for projection. It currently retains
bounded per-visit diagnostics (up to 10,000 visits), not an infinite stream.

The build takes an explicit matching detector ABI header and archive; the frozen
ungated archive is not interchangeable with newer expanded result structs.
`build-recorded.sh` cross-builds it successfully. Three component tests exercise
normal pacing, overload with visible rejection, and invalid arrival ordering.

`recorded-paced-smoke-v1/` confirms two real dwells execute on physical ARM and
all recorded candidate fields match the qualified baseline exactly. Both finish,
with no rejection and 17,664 KiB peak RSS. This run overlapped the full-corpus SD
transfer: reads took 971 and 1,229 ms and producer lateness grew to 2,060 ms.
It is therefore explicitly an ABI/executor smoke, not a throughput result. Zero
queue drops alone would conceal this storage bottleneck; producer lateness must
be part of the paced acceptance gate. Repeat after staging completes.

`recorded-paced-full-v1/protocol.json` freezes the full-scan execution inputs
before running: 2,215 original dwell-completion arrival counters, one detector
worker, four queued entries, and a 420-second process limit. Its five-column
manifest references only local device IQ and templates. The full recording is
being staged under `/mnt/glrtbench/modular-ds9-iq-v1`; successful completion of
all 2,215 SHA256 checks is required before running the paced process.

`tools/evaluate_recorded_pacing.py` checks every sequence, reconciles successful,
failed and rejected jobs against the terminal summary, and compares all candidate
checkpoint fields to the frozen archive. It reports producer/IO/queue/service/end
latency separately. Seven executor/accounting tests pass, including explicit
overload and delayed-producer cases. A scientific match does not itself establish
timely processing, and detector-only replay does not qualify downstream stages.

## Native integer support boundary

`integer-support-v1/` qualifies the existing native `fractional_support` with
zero fractional offset against the Python integer-support projector. All 2,648
distinct passing epochs in the 16,191-observation DS9 corpus have identical
support start, center and end. Maximum second/third factorial-moment differences
are 2.3717e-20 and 4.9657e-23 (predeclared absolute tolerances 1e-18 and 1e-20).
The batch adapter was cross-built and executed on physical PLUTO+; its complete
TSV is byte-identical to host output. Four component cases cover geometry,
moments and malformed inputs. This qualifies support derivation, not complete
observation identity/serialization or paced projection integration.

`native/adaptive/runtime/build.sh` now builds `project-integer-support`; it takes
`rate samples epoch` on stdin and emits start/end/center/moment2/moment3 TSV. The
algorithm itself is reused unchanged. The diagnostic run overlapped IQ hash
verification and is correctness evidence only, with no runtime claim.

The combined replay/support/executor/accounting suite now has 53 passing tests.
After device staging succeeds, run the frozen full-scan protocol with:

```sh
PYTHONPATH=src python tools/run_recorded_pacing.py \
  reports/2026_10_01_native_replay_qualification/recorded-paced-full-v1
PYTHONPATH=src python tools/evaluate_recorded_pacing.py \
  --reference reports/2026_10_01_arm_ungated_full_scan/arm \
  --input reports/2026_10_01_native_replay_qualification/recorded-paced-full-v1/output.jsonl \
  --output reports/2026_10_01_native_replay_qualification/recorded-paced-full-v1/evaluation.json
```

The launcher refuses existing output, incomplete IQ verification or changed
binary/manifest/templates. Execution and scientific evaluation receipts are
separate; neither asserts full-pipeline or sustained live qualification.

`src/leo/native_pipeline/paced_projection.py` and
`tools/project_recorded_pacing.py` adapt complete fresh candidate checkpoints to
observations. Run provenance gives new candidate identities; source coordinates
and scientific values are compared separately. Six tests reject dropped/missing
visits and wrong rank/probe/rate, and verify identity changes preserve science.

The initial full-dwell paced run exceeded the original scan duration while
waiting on SD reads. Its eventual timing remains to be evaluated; this already
rules out claiming original-cadence completion for that input path. An explicit
`--probe-prefix` reader is prepared in `recorded-paced-prefix-v1/protocol.json`.
It requires the verified full 2.4-MB dwell file but reads its first 400,000 bytes
(20 ms of dual-RX IQ), leaving the detector ABI's unconsumed tail zero-filled.
The pinned kernel's 120-ms/120-ms mode prepares exactly those first 50,000 sample
times. This mode must still reproduce every full-scan candidate before being
qualified. It models consuming the existing sparse probe, not recording all IQ
to SD at real time. The full-dwell run is retained as a separate storage control.

## Full-dwell paced result and fresh projection

`recorded-paced-full-v1/evaluation.json` accounts for all 2,215 visits: no
rejections, no detector failures, and exact candidate checkpoint agreement with
the frozen archive, including all 16,191 passing detections. It fails original
cadence: elapsed replay time is 375.342 seconds and maximum producer lateness is
75.116 seconds. Mean file-read time is 169.187 ms per dwell, mean detector service
128.621 ms, p95 service 151.376 ms, peak RSS 24,440 KiB. Queue high water is only
one because storage throttles arrivals. Whole-process wrapper time is 375.626
seconds with 326.338 CPU seconds. No-drop accounting is therefore insufficient
to claim real time. The separate probe-prefix comparison is now running.

`fresh-full-projection-v1/` projects that freshly executed ARM output on the host.
All 16,191 source-matched observations agree exactly with the frozen checkpoint
in every field except the deliberately distinct analysis candidate ID. Running
the host coarse-seeded tracker produces 80 tracks with identical per-track sets
of (source group, support center, measured CFO, alias). Some duplicate candidate
ranks selected by the tracker differ when their identifiers change, and its
unique-candidate count is 5,256 versus 5,254; these are not additional scientific
track points. `tracking-identity-audit.json` retains both the rank-level changes
and the empty scientific-membership diff.

The initial fresh projection included execution-output hashes in analysis
identity. The adapter now uses `recorded-integer-glrt-config-v1`: detector binary
and explicit geometry/threshold determine analysis identity, while execution
protocol/output hashes are retained separately as provenance. This prevents
timing telemetry alone from changing IDs between identical detector runs. The
earlier v1 projection remains intact as diagnostic evidence; future projections
record the new identity method explicitly. Projection and tracking here run on
the host; on-device integrated downstream execution remains a separate gate.

## Probe-reader result and native observation checkpoint

`recorded-paced-prefix-v1/evaluation.json` reports 300.254 seconds for the full
schedule. All processed candidate values agree exactly, but visit 158 was
rejected, losing 12 passing detections (16,179 retained). A 683.257-ms file read
at visit 151 delayed arrivals; the subsequent catch-up burst filled the four
pending slots. Mean IO falls from 169.187 to 50.921 ms; mean detector service is
122.840 ms, p95 145.676 ms, maximum completion latency 834.167 ms, peak RSS
27,588 KiB. This run fails the no-loss gate. The eight-entry comparison is running
under `recorded-paced-prefix-q8-v1/`, with the change justified by the measured
burst rather than an unbounded queue.

`native-fresh-projection-v1/` qualifies an additive `leo-project --checkpoint`
mode on the host. It reuses the existing native projector with zero fractional
offset and emits the observation TSV accepted by the trackers. All 35,440 fresh
candidate records yield 16,191 observations matching Python's numeric fields,
identities and times exactly. Coarse-seeded tracking on this native output is
byte-identical to tracking on the Python projection. Two CLI tests cover passing
and nonpassing candidates, legacy output compatibility and unknown-mode rejection.
The ARM binary is built; physical execution waits for paced replay to finish so
the measurement is not disturbed. The candidate-map file in this diagnostic is
evaluation metadata copied from the same fresh run, not an ARM-emitted product.

## Lossless single-scan pacing and physical projection

`recorded-paced-prefix-q8-v1/evaluation.json` accounts for all 2,215 visits with
zero rejections/failures and exact candidate agreement, including all 16,191
passing detections. Replay elapsed time is 300.213 seconds; wrapper elapsed time
is 300.497 seconds and CPU time 292.528 seconds. Mean/p95/max detector service
is 122.742/145.427/190.902 ms. Mean/p95/max due-to-finish latency is
180.318/221.464/331.596 ms. Producer lateness peaks at 75.993 ms, queue high-water
is two, and peak RSS is 22,312 KiB. This is one lossless detector-only scan at the
recorded schedule with bounded drain latency. The earlier 683-ms storage stall
did not recur; this run does not demonstrate that eight entries absorbed that
particular burst or establish multi-scan/full-pipeline sustainability.

`native-fresh-projection-arm-v1/receipt.json` qualifies actual native projection
on PLUTO+. All 16,191 output observations match host/Python scientific fields and
identities exactly. The complete text-port process takes 24.819 seconds,
24.809 CPU seconds and 1,776 KiB peak RSS, including text parsing/serialization.
This is not an in-process projection timing. `tools/qualify_native_observation_port.py`
verifies payload hashes and refuses to overlap a paced detector measurement.
The remaining execution work includes wiring the qualified native projection
directly to detector results, running tracking/positioning under shared CPU
budgets, and demonstrating sustained multi-scan operation.

## Direct native detector-to-projection integration

`runtime/detector_projection.hpp` is a narrow in-memory adapter for the pinned
dual-receiver integer-epoch profile. It validates the receiver/probe inventory,
source authority and passing-candidate completion, canonicalizes receiver order,
and returns owned ranked observations through the existing native projector.
No storage or orbit dependency is introduced. Component tests cover valid
projection, swapped receivers, duplicate/missing rows and incomplete evidence.

The recorded executor now optionally accepts `--authority FILE --observations
FILE`. Authority is parsed once before pacing and checked against every recorded
arrival; per-dwell candidate projection happens directly in the detector worker.
It records detector and projection times separately and refuses an existing
observation output. Five executor tests pass, including the integrated checkpoint
path. The full physical run is active under `recorded-projected-v1/`; source and
binary hashes and the explicit authority are retained. Its result is not yet a
qualification claim. Observation file publication occurs after scan drain;
per-dwell finish metrics describe processing completion, not file durability.

`tools/qualify_fresh_arm_tracking.py` prepares the next on-device boundary: it
requires a successful integrated replay receipt, checks the on-device observation
hash, and runs the pinned seed/tracker binaries against that local file. It
records whole-process stage times and compares memberships with an independent
host invocation. This driver has not yet run on the integrated checkpoint.
The pacing evaluator now reports quarter-scan producer lateness, queue delay,
completion latency and rejection counts; five accounting tests pass, including
a deliberately growing backlog. These summaries supplement the raw per-visit
records and do not substitute for multi-scan qualification.

## Combined ARM detection, projection and tracking

`recorded-projected-v1/` has now completed on PLUTO+: all 2,215 arrivals processed,
no rejection/failure, all 16,191 passing detections identical to the frozen scan.
Native observations match the independent Python projection exactly by source,
including candidate identity, lane, support times, CFO and scores. Source-map
metadata used for that comparison is generated by the evaluator, not emitted
by the device. Replay time is 300.360 seconds; peak RSS 36,228 KiB and queue
high-water six. Mean detector time is 119.733 ms/dwell, direct projection 6.712
ms/dwell, and combined service including diagnostic serialization 128.461 ms.
Maximum processing-completion latency is 955.601 ms. Mean queue delays by scan
quarter are 33.13, 295.75, 19.69 and 6.26 ms: the mid-scan backlog recovers within
this scan, rather than growing through its end.

`fresh-arm-tracking-v1/` runs coarse seeding and curvature tracking directly on
the ARM-emitted observation file, keeping runtime data local. It produces 80
tracks and 5,255 distinct candidate memberships, with byte-identical host/ARM
track output for this configuration identity. Whole-process seed and tracker
times are 3.587 and 3.825 seconds (7.412 seconds combined); peak RSS is 10,660 KiB.
These tracker stages ran after the paced detector/projection scan, so their
combined result does not yet prove overlap with the next scan. Fresh association,
positioning and sustained multi-scan execution remain outstanding.

## Fresh native support graph and downstream composition

`recorded-graph-v1/` adds native support output to the same detector/projection
worker. The graph carries session/capture authority, exact support timestamps
and the projector's moments; Python does not construct the runtime graph.
The replay completed all 2,215 arrivals without rejection or failure, reproducing
all 16,191 passing detections. Replay elapsed time was 300.386 seconds (whole
process 300.822 seconds), peak RSS 40,792 KiB. Mean detector/projection times were
120.188/7.345 ms per dwell, combined service 129.564 ms including diagnostics.
Maximum processing-completion latency was 1.217 seconds. A 638.915-ms read stall
occurred; queue high-water reached its capacity of eight without loss. Quarter
mean queue delays were 187.15, 471.66, 26.10 and 7.29 ms, showing recovery within
this scan. Reaching queue capacity leaves little burst margin and is not proof
of sustained multi-scan throughput.

`graph-projection-reference-v1/` independently projects the measured candidates.
Scientific observation fields match exactly. All 16,191 native graph entries
match reference identities and timestamps; maximum second/third moment errors
are 2.372e-20/4.966e-23, below predeclared 1e-18/1e-20 absolute tolerances.
`tools/compare_native_support_graph.py` records the comparison and rejects
duplicate identities and nonfinite moments. The source map accompanying the
ARM output remains evaluator-generated metadata. The replay/bench suite now
passes 64 tests, including support-graph and invalid graph-option checks.

`fresh-graph-tracking-v1/` consumes the on-device observation checkpoint and
produces 80 tracks with 5,255 distinct candidates. Host/ARM memberships and bytes
are identical. Coarse seeding took 3.581 seconds and tracking 3.839 seconds,
7.420 seconds combined. Independent server comparison preserves the frozen
result: 55/62 represented, 45 one-to-one; short 7/9, medium 23/25, long 25/28.
Reference #10 is the sole exclusion. There are 35 unmatched output hypotheses;
these counts do not establish physical identities or false-positive rates.

`tools/qualify_fresh_arm_location.py` checks and consumes the existing on-device
observations, graph and tracks, builds an exclusive-candidate LOC1 checkpoint,
and compares conversion bytes and two fixed-site scores with a host invocation.
Its scope deliberately excludes regional search and overlap with the next scan.
Configuration changes alter candidate identities and derived train/held-out
partitions, so aggregate scores from different replay binary identities are
not a controlled accuracy comparison even when CFO measurements are identical.

`fresh-graph-location-v1/` passed on physical PLUTO+: converted LOC1, derived
track identities/partitions and member files are byte-identical to host, and
both complete score JSON results match exactly. Conversion took 5.400 seconds
(3.440 CPU seconds, 46,684 KiB RSS); two-site scoring took 27.598 seconds
(48.464 CPU seconds, 24,580 KiB RSS). These stages ran after tracking, without
overlapping the next scan. This closes the fresh local checkpoint chain through
fixed-site association scoring, not regional positioning or continuous operation.

Reproduction commands (use a fresh output directory and new device checkpoint
names for a new hardware run; existing evidence is never overwritten):

```bash
export PYTHONPATH=src
python tools/run_recorded_pacing.py reports/2026_10_01_native_replay_qualification/recorded-graph-v1
python tools/qualify_fresh_arm_tracking.py \
  --replay reports/2026_10_01_native_replay_qualification/recorded-graph-v1 \
  reports/2026_10_01_native_replay_qualification/fresh-graph-tracking-v1
python tools/qualify_fresh_arm_location.py \
  --replay reports/2026_10_01_native_replay_qualification/recorded-graph-v1 \
  --tracking reports/2026_10_01_native_replay_qualification/fresh-graph-tracking-v1 \
  --authority reports/2026_10_01_native_replay_qualification/native-orbit-authority \
  --output reports/2026_10_01_native_replay_qualification/fresh-graph-location-v1
```

## Regional-search cost profile

`score-cost-profile-v1/` measures the fresh 80-track checkpoint at its first
fixed comparison site with one ARM worker. The research harness calls the
unchanged scorer one track at a time and checks all resulting scores against
the qualified full scorer. Host and ARM agree exactly for every satellite ID,
tau, fit/held-out RMS and offset, and for the aggregate score.

The ARM process took 24.158 seconds / 24.156 CPU seconds, with 24,196 KiB RSS.
Summed per-track scoring time was 24.018 seconds. Horizon rejection removed
848,059 satellite–track pairs; 42,181 pairs remained, requiring 31,360,560
interpolated states over all eleven tau values. The ten most expensive tracks
accounted for 30.26% of scoring time, so removing a few long tracks would neither
preserve the requested science nor solve the throughput problem.

A linear extrapolation is about 9,607 CPU seconds for 400 sites. This is **not
a measured regional runtime**: eligibility and cost vary by site. It shows why
another full ARM search is inappropriate until the scorer's work is reduced.
The next research gate is conservative candidate rejection using a cheap
held-out residual lower bound, followed by unchanged full scoring of surviving
candidates. It must demonstrate unchanged winning IDs, tau, scores and search
trace on the published and fresh checkpoints before any default change.
Even a successful micro-optimization does not prove the full throughput gate.

The bounded profiler is reproducible with:

```bash
TMPDIR=/var/tmp bash tests/native_adaptive/location/research/build_track_profile.sh \
  host /var/tmp/leo-modular-location-host /var/tmp/leo-profile-track-host
/var/tmp/leo-profile-track-host \
  reports/2026_10_01_native_replay_qualification/fresh-graph-location-v1/host.loc1
```

Use `arm` with the qualified ARM library directory to build the device harness.
The retained protocol pins binary, source and input hashes; `arm.stderr` contains
the physical 90-second-bounded measurement. Profiling performs no RF collection.

## Opt-in held-out bound experiment

The research scorer uses the first and last held-out residuals to bound any
possible held-out RMS: `abs(a-b)/sqrt(2*N)`, where N is the full held-out count.
It rejects a satellite only when all eleven tau values exceed the incumbent
plus a numerical guard; surviving candidates use the unchanged full scorer.
This preserves the tau grid and catalog. The mathematical inequality is exact,
but the floating-point guard remains a research qualification limitation.
Nonfinite or extreme orbit inputs disable this path. Neither research flag is
enabled by the default build, and no public contract or golden fixture changed.

`heldout-bound-v1/` records ARM control/candidate/candidate/control trials for
the two fresh fixed sites. Controls took 27.521/27.445 seconds; candidates took
7.001/6.987 seconds, about 3.93x faster. Every score JSON matches exactly.
Both fresh and published fixed-site host controls match. The fresh full
400-point host search is JSON-identical, including ordered evaluations and
selection. `regional-bound-published-sacramento-v1/` preserves all 400 server
evaluation sites and its selected point; server numerical deltas remain the
previously qualified interpolation differences (maximum 0.018333 Hz).

The warm-start experiment recomputes the previous site's winning satellite at
the new site before scoring the whole catalog. Version 1 redundantly validated
the entire state bank for every seed and regressed to 12.014/11.995 ARM seconds.
Version 2 validates only the relevant satellite partition. In
`heldout-warm-v2-arm/`, two fixed-site runs take 5.136/5.135 seconds, about 5.35x
faster than the control average, with exactly matching score JSON and roughly
24.6 MiB peak RSS. `heldout-warm-v2/search-receipt.json` proves full 400-point
fresh host search JSON equality; its concurrent-host elapsed time is not an
isolated performance benchmark. Source snapshots and hashes are retained.

Component tests cover the pair bound, ties, nonfinite values, real interpolation
and fallback; the existing location unit suite passes with the research scorer.
The rebuilt default location suite also passes, including interpolation-stencil
tests and twelve orbit CLI rejection cases. Full ARM regional timing, broader
numerical edge qualification and sustained concurrent pipeline execution remain
open. Fixed-site acceleration alone does not establish those gates.

The warm-start published-track Reno control also passes in
`regional-warm-published-reno-v1/`: all 400 ordered search locations, the selected
point and deferred-cell count agree with the server. Maximum common-site score
delta is 0.017129 Hz; selected-score delta is 0.003439 Hz, consistent with the
existing native interpolation comparison. The 400-point budget is exhausted;
this is not proof of global convergence.

Regional deadline instrumentation is opt-in via
`LEO_RESEARCH_SEARCH_PROGRESS`. It records each completed site and its elapsed
time without changing the normal search output. `tools/evaluate_search_progress.py`
requires every ordered point and full result to match the pinned reference
before declaring completion. A timed-out matching prefix is explicitly
incomplete. Its component test covers partial output, missing final output,
score mismatch and invalid ordering. The replay/bench suite passes 65 tests;
the focused bound test also passes address/undefined-behavior sanitizers
(linked orbit-library objects themselves were not sanitizer-instrumented).

`regional-arm-bound-300s-v1/` is a failed throughput gate. The progress-instrumented
warm-bound ARM build completed 169 of 400 points before the 300-second deadline
(exit 142), consuming 571.184 CPU seconds with 24,852 KiB RSS. Completed-point
mean wall time was 1.768 seconds. All completed coordinates agree with the
pinned host trace; point 162 differs in score by 5.684342e-13 Hz. Exact equality
therefore fails and the difference remains visible in `evaluation.json`; no
post-hoc tolerance is used to mark this run qualified. The partial stdout is
empty because the final regional result was never reached.

The two-worker scorer nearly saturates both ARM cores even without GLRT running.
This run disproves that the current optimization can deliver the required
400-point positioning workload per 300-second scan. Next work must reduce
regional scoring work further, investigate the tiny cross-platform discrepancy,
and then repeat the original deadline test with GLRT sharing the CPU budget.
Reducing the search budget is not a substitute for this qualification.

## Search-point 162 numerical diagnosis

`point162-diagnosis-v1/` isolates the 5.684342e-13 Hz difference. The unmodified
ARM scorer and bound scorer produce identical complete per-track/aggregate JSON
at the independently generated ARM site. Supplying the host's exact six site
components to either ARM scorer produces complete JSON identical to host.
Thus the observed difference is reproduced without candidate rejection and is
explained by site construction, not a changed winning association.

For this point, ARM's generated ECEF x differs from host by 4.547474e-13 km and
the corresponding up-vector component by 1.110223e-16. Other site components
agree exactly. This is consistent with platform differences in the trigonometric
site transform; the particular library operation has not been isolated.
The failed exact comparison in the original deadline report remains unchanged.
No fixture, coordinate or score was rounded to force agreement. Future
cross-platform regional qualification should distinguish exact scorer equality
at identical sites from separately declared site-transform numerical tolerances.
The throughput failure remains independent of this numerical diagnosis.

The diagnostic harness accepts a LOC1 input followed by either four
origin-latitude/origin-longitude/east/north values or six explicit ECEF/up
components. It emits the actual site to stderr and ordinary score JSON to stdout.
Build it with `tests/native_adaptive/location/research/build_site_diagnosis.sh`
using `host` or `arm`, the qualified library directory and an output executable.
The report retains inputs, site components, four ARM comparisons and binary/
library hashes. It changes no production scoring or location behavior.

## Stronger subset-bound experiment

`subset-bound-v1/` adds an opt-in eight-observation held-out bound. The minimum
SSE of a subset about its own mean is a lower bound on the complete held-out SSE
about the training-fitted offset. Division remains by the full held-out count,
not the subset count. The endpoint check still runs first. Uncertain candidates
retain full scoring; the experiment does not change the catalog or tau grid.

The fresh fixed-site result and full 400-point host regional JSON remain exactly
equal to control. The location unit suite and focused subset/tie/offset tests
pass; the focused sanitizer executable passes (the linked scorer/orbit archive
was not fully sanitizer-instrumented). `subset-bound-arm-v1/` contains alternating
pair/subset/subset/pair hardware measurements. Subset runs take 4.539 and 4.537
seconds for the same two fixed sites versus approximately 5.14 seconds for the
pair warm-start version, about 12% faster. All complete score JSON results match.
This modest incremental gain does not resolve the previously measured regional
deadline failure; no new full ARM throughput qualification is claimed.

`planned-bound-v1/` reuses per-track subset indexes and the existing interpolation
stencils. Its full 400-point host search remains JSON-identical to control.
`planned-bound-arm-v1/` alternates subset/planned/planned/subset: planned runs
take 4.367/4.358 seconds versus 4.581/4.540 seconds for the subset control.
All score JSON matches. Prepared versus generic bound decisions are tested
over incumbent RMS values 0–100 with real interpolated states; focused sanitizer
tests pass. This is a small improvement, not full throughput qualification.

The next opt-in research mode (`LEO_RESEARCH_CAPPED_SEARCH`) uses the existing
800-Hz objective cap only during regional search. A private incumbent sentinel
at that cap allows bound rejection of candidates whose exact high residual
cannot affect the regional objective. It is never published as a satellite
association; ordinary full `score` mode is unchanged and remains necessary at
the selected site. The fixed-site component test proves equal aggregate loss
and equal winners below the cap. Full regional comparisons are retained under
`capped-search-host-v1/`; ARM throughput is not yet qualified for this mode.

Both fresh-track and published-track 400-point host comparisons have completed:
the full search JSON equals their respective unmodified controls. Source
snapshots and hashes are retained alongside the results. The bounded physical
attempt is `regional-arm-capped-300s-v1/`; evaluate its execution receipt and
progress before making any throughput claim. A successful search alone still
would not establish overlap with acquisition or supply final association output.

`regional-arm-capped-300s-v1/` terminated at its deadline with 206/400 completed
points (exit 142), versus 169 for the earlier pair-bound attempt. Mean completed
point time is 1.454 seconds; whole-process time 300.012 seconds, CPU 575.213
seconds, RSS 24,852 KiB. All coordinates match the reference prefix. Exact score
equality fails at points 162 and 186, with maximum delta 5.684342e-13 Hz. Point
162's site-construction cause is independently diagnosed above; point 186 has
not been separately isolated. This remains a failed throughput qualification,
even before concurrent GLRT work is introduced.

The location CLI now has `score-at FIXTURE ORIGIN_LAT ORIGIN_LON EAST_KM
NORTH_KM [WORKERS]`, which always performs full association scoring at an
explicit regional point. Self-contained synthetic CLI tests verify the known
satellite, one/two-worker equality and malformed/nonfinite coordinate rejection.
They are included in the normal component build. Objective-to-full restoration
tests recover every association field exactly for fresh and published fixtures,
including with warm-start support compiled in. Host scoring at the fresh
search-selected (-75,-75) point matches the full search objective and returns
80 associations (`capped-search-host-v1/selected-associations.json`). This is
full association output, not the private capped-objective sentinel.

`selected-associations-arm-v1/` runs that full association step on PLUTO+ against
the existing local LOC1 checkpoint: complete JSON equals host exactly, taking
2.852 seconds (4.778 CPU seconds, 24,796 KiB RSS). The coordinate was selected
by the completed host search; the ARM search did not finish. This qualifies the
final association boundary independently, not an end-to-end ARM position result.

`tools/run_arm_regional_qualification.py` now provides a reproducible pinned
ARM-local search→selected-site association driver. It validates diagnostic
paths, payload hashes, prior, worker count and a maximum 600-second budget,
preserves execution/progress hashes and failure receipts, and feeds the actual
ARM-selected point to full scoring only after all 400 points complete. Protocol
tests cover path/hash/prior/budget rejection. The original `regional-arm-full-capped-v1/`
attempt requested 750 seconds; the existing measurement wrapper rejected that
unsupported limit before running any search (exit 2, empty output). It remains
as failed evidence. `regional-arm-full-capped-v2/` uses the supported 600-second
limit. This is a correctness attempt and does not relax the separate 300-second
throughput gate. Check its terminal receipt before claiming completion.

```bash
PYTHONPATH=src python tools/run_arm_regional_qualification.py \
  reports/2026_10_01_native_replay_qualification/regional-arm-full-capped-v2
```

The driver refuses to overwrite existing execution evidence; a repeat needs a
fresh report directory with a pinned protocol. IQ and stage inputs stay on ARM.

## Horizon-prefix research

`horizon-prefix-host-v1/` preserves exact fresh fixed-site score JSON and the
entire 400-point regional search JSON. The optimization precomputes the same
cubic horizon-control-point comparisons by satellite and knot interval, then
uses prefix counts for track time-range queries. This removes repeated horizon
arithmetic across tracks without narrowing satellite eligibility. Scratch is
bounded to four MB per context invocation, with fallback to the existing test
on allocation/capacity failure. Tests cover velocity-only eligibility, range
boundaries, satellite partitions and cache replacement when the site changes;
the focused address/undefined sanitizer test passes. Existing location unit
tests also pass. This variant has not yet been timed on ARM: the earlier full
search measurement remains isolated from competing device work.

The strengthened horizon test compares prefix decisions with the original
predicate across 200 deterministic randomized orbit/site fixtures and all tested
five-second interval combinations, including nonfinite state propagation and
oversized-capacity rejection. It passes with address/undefined sanitizers.
`regional-horizon-published-v1/` also preserves the published server's complete
400-point coordinate order, selected point and deferred-cell count; its score
deltas remain the existing native interpolation differences. Host elapsed time
is 6.874 seconds for that control, with no corresponding ARM claim yet.

## Completed full ARM regional result

`regional-arm-full-capped-v2/` completed all 400 evaluations on PLUTO+ in
580.591 seconds (1,113.815 CPU seconds, 24,864 KiB RSS). Every ordered coordinate
matches the host trace and the selected point is exactly (-75,-75), with score
372.99354955191757 Hz. Two per-point scores differ from host by at most
5.684342e-13 Hz; the exact comparator therefore retains `full_search_qualified=false`.
This is a completed result with disclosed numerical differences, not an exact
JSON match or a passed throughput gate.

The driver then used the ARM-selected point for full ARM association scoring:
all association JSON equals host exactly, in 2.849 seconds (4.772 CPU seconds).
This closes the actual ARM regional-selection→association chain for the fresh
locally generated track/support input. Native tracking's difference from server
memberships and the resulting location difference remain the documented
scientific limitation; this does not make server and ARM track sets identical.

`regional-arm-horizon-300s-v1/` is the next isolated physical attempt. Its
protocol predeclares a 1e-9 Hz absolute score tolerance based on the independently
diagnosed site-transform rounding, while requiring exact order, coordinates,
selection, counts and status. `tools/compare_regional_results.py` reports exact
equality separately and does not change previous failed exact comparisons.
The driver refuses to overlap another measured device workload. Component tests
cover that guard and ensure numerical tolerances cannot conceal changed search
coordinates or inventory. Inspect its terminal receipts before claiming speed.

`regional-arm-horizon-300s-v1/` reached 354/400 points before timeout (exit 142),
up from 206 for capped/subset bounds without horizon prefixing. Mean completed
point time is 0.846 seconds; whole-process time 300.012 seconds, CPU 557.447
seconds, RSS 25,856 KiB. All completed coordinates match; only points 162/186
differ in score, by at most 5.684342e-13 Hz. The numeric tolerance does not turn
this incomplete search into a qualified result. The original-cadence gate
remains unmet, particularly once GLRT shares the CPU budget.

`horizon-cost-profile-arm-v1/` profiles the first regional point, separately
after the deadline run. Score equals control exactly. The two satellite
partitions take 0.748/0.876 seconds inside scoring; setup takes 0.115 seconds
each and bounds 0.389/0.506 seconds. The bound rejects 41,908 satellite–track
pairs; only 225 require full scoring. Whole process is 1.011 seconds / 1.744 CPU
seconds; repeated clock calls add overhead. This identifies repeated bound
evaluation as the largest measured phase. Reusing its site-independent orbit
interpolation across sites is the next research target; cache memory, immutable
authority, invalidation and fallback require explicit qualification.

## Bound-state cache experiment: rejected for performance

`bound-cache-host-v1/` preserves complete fixed-site and 400-point search JSON,
but the host search takes 25.261 seconds versus the earlier uncached horizon
run's 8.786 seconds (not a paired host timing). `bound-cache-arm-v1/` provides
the decisive ordered 16-site hardware comparison: uncached 13.531 seconds /
24.927 CPU seconds / 25,528 KiB RSS; cached 16.964 seconds / 30.797 CPU seconds /
201,496 KiB RSS. Both emit exactly the reference scores. This is a regression,
so the direct-mapped cache remains disabled and is not a deployment candidate.

The experiment uses a bounded million-entry state table per context plus an
orbit-authority copy. Tests verify exact hits, collision eviction, invalidation
on generation/grid changes and same-generation state mutations, range changes,
and disabled-capacity fallback; the focused sanitizer test passes. The ARM
compiler required an explicit scorer-context constructor to avoid a GCC 7
aggregate-initialization internal compiler error. This is confined to the
opt-in cache build. The uncached horizon-prefix implementation remains the
best measured candidate. A future reuse design must avoid this random-access
overhead and memory footprint; numerical correctness alone is insufficient.

## Bound-loop integer arithmetic

`bound-counter-host-v1/` preserves the entire 400-point host search JSON
exactly (7.157 seconds, an unpaired host measurement). The bound loop now
increments its stencil index instead of repeatedly dividing 64-bit integers,
and converts each visited time offset through int32 rather than invoking an
ARM software int64-to-double conversion. Its loop counter remains int64 so
incrementing beyond an int32 endpoint cannot overflow. Search sampling,
offset grids, rejection guards and production defaults are unchanged.

`bound-counter-arm-v1/` measures sequential control/counter/counter/control
runs on the same first 16 regional points. All scores equal the host reference
exactly. Mean wall time falls from 13.501669 to 12.504085 seconds (7.39%);
counter CPU times are 23.124790/23.122342 seconds, versus control
24.879888/24.850229 seconds. Peak RSS remains about 25 MiB. This is a short
isolated benchmark, not evidence of full-search or continuous-scan throughput.

Component tests compare generic and planned interpolation with moving orbital
states, negative offsets, a non-unit step and both int32 endpoints. Both
rejection and survival are exercised; the focused ASan/UBSan executable passes
(the linked location archive itself is not sanitizer-instrumented). Six search
progress/protocol/result comparison tests also pass.

`regional-arm-counter-420s-v1/` records the full-search attempt with a pinned
binary/input and a predeclared 1e-9 Hz score tolerance. Its 420-second diagnostic
timeout does not relax the required 300-second scan cadence, and GLRT is not
running concurrently. Consult terminal receipts before claiming completion.

The counter run completed all 400 points in **313.311600 seconds**, consuming
584.158930 CPU seconds and 25,764 KiB peak RSS. The selected point remains
(-75, -75) km, score 372.99354955191757 Hz. Ordered coordinates and result
structure match exactly; only intermediate points 162 and 186 differ, by at
most 5.684342e-13 Hz. The predeclared tolerance comparison passes; the separate
strict equality report correctly remains false. This is completion of the
400-point budget, not proof of global search convergence.

Full association scoring at the ARM-selected point takes 2.158156 seconds
(3.418018 CPU seconds), and its complete JSON equals the host control. The
host counter build also preserves the published-membership 400-point horizon
trace exactly, in an unpaired 5.905-second run.

The cadence gate still fails. Search alone exceeds 300 seconds; adding its
584.16 CPU seconds to the earlier recorded detector/projection's 306.13 CPU
seconds gives about 890 CPU seconds before tracking, orbit generation and
final scoring. This cross-run accounting identifies an insufficient compute
budget; it is not a concurrent end-to-end measurement. Two cores offer at
most 600 CPU seconds per 300-second interval. Larger work reduction is needed
before a sustained combined replay can plausibly pass.

## Direct endpoint-state reuse experiment

`endpoint-bank-host-v1/` preserves both the fresh-track and published-membership
400-point host traces exactly. Its unpaired host times (9.583/7.932 seconds)
are worse than the counter build. The hardware result differs:
`endpoint-bank-arm-v1/` runs counter/bank/bank/counter on the same 16 points,
with exact scores in every run. Counter takes 12.518307/12.489815 seconds;
bank takes 11.644955/11.633671 seconds, about 6.9% faster. Bank CPU time is
21.670437/21.659306 seconds; peak RSS is 115,200/115,272 KiB, versus about
25 MiB for the counter control. This is an explicit speed/memory tradeoff.

The bank uses a dense track/satellite index and lazily populated endpoint
blocks, bounded to 32 MiB per scoring context, plus partition metadata and
authority copies. It compares actual state bytes to detect same-generation
mutations. Tests cover unchanged hits, state/time/mask/grid/generation/partition
changes, site-independent reuse, invalid requests and capacity fallback.
The focused ASan/UBSan test passes; its linked location archive is uninstrumented.
`regional-arm-endpoint-300s-v1/` records a separate full-search attempt with
the original 300-second deadline and no concurrent detector.

The subsequent compact layout reserves only the default eleven offsets per
endpoint block and avoids rewriting cache hits. Wider grids use the original
uncached path. Its source/build/results are distinct from the running first
bank version; do not attribute later changes to earlier timing receipts.

The original bank's full run completed **400/400 points in 283.620201 seconds**,
531.595224 CPU seconds, peak RSS 116,488 KiB. This passes the isolated
300-second search deadline. Selected position and score equal host exactly;
all ordered coordinates match and the same intermediate points 162/186 differ
by at most 5.684342e-13 Hz. The explicit-tolerance comparison passes, while
strict bitwise equality correctly remains false. Full selected-site association
JSON equals host exactly, in 2.425926 seconds / 3.878292 CPU seconds.

This does not pass the combined cadence gate: search plus earlier recorded
detector/projection still totals about 837.73 CPU seconds before other stages,
against at most 600 available. Search and detector were measured separately.
The cache is an opt-in research tradeoff, not a continuous production default.

`endpoint-compact-host-v1/` preserves both full host traces exactly. Its
scorer and bank tests also pass under ASan/UBSan with `score.cpp` instrumented
(orbit/search/vendor objects are uninstrumented). The component bank test
passes on physical ARM. `endpoint-compact-arm-v1/` compares original/compact/
compact/original on 16 sites: compact takes 10.575562/10.576934 seconds versus
original 11.667073/11.634741 seconds, a further 9.2% reduction. All scores
match exactly. Compact peak RSS is 100,920/100,708 KiB versus 115,188 KiB;
CPU is 19.957497/19.954397 seconds. This version has full host and short ARM
evidence only; its complete ARM search still needs a separate qualification.

`regional-arm-compact-300s-v1/` supplies that subsequent full qualification:
**400/400 points in 254.954161 seconds**, 487.850472 CPU seconds, 102,372 KiB
peak RSS. All search coordinates, selection and status match the control;
only the previously diagnosed intermediate score roundoff remains
(maximum 5.684342e-13 Hz), passing the predeclared 1e-9 Hz comparison. Full
association JSON at the selected position equals host exactly, in 2.389408
seconds / 3.811875 CPU seconds. The search budget remains 400 points; this is
not global convergence. Detection/projection plus search still totals about
793.99 CPU seconds before other stages, so combined cadence remains unproven
and exceeds the theoretical two-core budget in separate-run accounting.

The next microbenchmark separates shared-knot horizon reuse from bound-loop
constant hoisting. Shared-knot reuse computes each identical position/velocity
dot product once across adjacent intervals while retaining the original
short-circuit comparisons. Constant hoisting moves the Doppler scale and
pair normalization out of the inner time/observation loops. Both variants
preserve complete host search traces; randomized horizon tests additionally
cover nonfinite shared-knot values, and focused sanitizer tests pass. Hardware
timing, not host timing, determines whether either is retained for performance.

`bound-hoisted-arm-v1/` uses symmetric compact/rolling/hoisted/hoisted/rolling/
compact runs on the same 16 sites. Mean wall times are respectively 10.589348,
10.243389 and 9.822604 seconds: horizon reuse saves 3.3%, combined changes save
7.2%. Every score equals the reference; peak RSS remains about 98.5 MiB.
Mean combined-build CPU time is 18.564732 seconds versus 19.973298 seconds
for control. Both changed component tests pass on physical ARM. The combined
build preserves fresh and published complete host traces exactly; its full
400-point ARM search is the next qualification step. No short-run projection
is substituted for that pending measurement.

`regional-arm-hoisted-300s-v1/` subsequently completes all 400 points in
**235.644445 seconds**, 452.728280 CPU seconds, peak RSS 102,152 KiB. Search
selection, ordered coordinates and status match host; the same two intermediate
roundoff differences pass the predeclared tolerance. Full selected-site
association JSON equals host exactly, in 2.333572 seconds / 3.715578 CPU
seconds. The search workload is unchanged. Combined cadence remains unmet.

`score-pgo-arm-v1/` is a separate scorer-only compiler experiment. Its protocol
pins four training points and a disjoint set of sixteen evaluation points.
Training counters use atomic updates on the physical two-core device; training
time is not a throughput result. The build recipe refuses absent profile data,
source drift and overwriting an existing training build. No numerical compiler
relaxations are enabled, and the ordinary build remains the control.

The profile contains 8,072 bytes from the four-point physical ARM training run;
its hash and instrumented binary hash are recorded separately. Training scores
match reference exactly. The profile-use build reports no missing-profile or
coverage-mismatch warning; core location and interpolation tests pass on ARM.
An explicit negative check also verifies source drift is rejected before
compilation. The compiler is Linaro GCC 7.3.1, recorded in `compiler.txt`.

Held-out control/PGO/PGO/control timing is 9.870012/9.344413/9.361146/9.837329
seconds. Mean time falls from 9.853670 to 9.352779 seconds (5.1%), with every
score exact and approximately unchanged 98 MiB peak RSS. Mean CPU time falls
from 18.357469 to 17.432127 seconds. These points were excluded from training.
This is evidence for retaining PGO as a candidate, not a full-search or
continuous-cadence qualification; the complete PGO ARM run remains pending.

`regional-arm-pgo-300s-v1/` subsequently completes the unchanged 400-point
search in **225.162961 seconds**, 430.662576 CPU seconds, 102,368 KiB peak RSS.
It preserves the ARM control's full search JSON exactly; against host only the
previously diagnosed tiny intermediate score differences remain. Full selected
associations equal host exactly, in 2.292782 seconds / 3.626083 CPU seconds.
The explicit-tolerance result comparison passes; combined cadence still does
not fit the theoretical two-core budget in separate-run CPU accounting.

## Float endpoint interval prefilter: research experiment

The thirteenth recipe argument `float-pair` enables a separate opt-in endpoint
prefilter. It forms position differences in double, evaluates approximate
Doppler in float, and attaches an absolute error allowance. Unsupported ranges
fall back to double. An uncertain endpoint pair restores both original double
residuals before the existing pair/subset bound; final scores are unchanged.
The allowance is intentionally conservative, but remains an engineering bound
under the tested floating-point environment, not a formal all-input proof.

`float-pair-host-v1/` preserves both complete fresh and published host traces
exactly. Differential tests use 100,000 randomized pairs across magnitude
ranges, compare each valid interval with an independent double calculation,
and test rejection near the double decision boundary. Degenerate/nonfinite
cases fall back. Focused sanitizer tests and physical ARM tests pass. These
checks do not alone justify promotion to a production numerical contract.
`float-pair-arm-v1/` records its isolated paired speed comparison; a correct
but slower prefilter must remain disabled.

The paired ARM result rejects this scalar float experiment: double-control
mean is 9.851329 seconds; float mean is 11.768703 seconds, about 19.5% slower.
Both float runs match the reference exactly, but consume 21.916673/21.951316
CPU seconds versus control 18.609655/18.528331. Peak memory is comparable.
Do not enable this flag for deployment. The PGO double scorer remains the best
complete ARM measurement. A different design would need to overcome conversion,
error-accounting and fallback overhead rather than assuming float is faster.

## Explicit immutable orbit sessions

`current-score-profile-arm-v1/` diagnoses the optimized ordinary scorer over
16 points. Its 32 main partition calls total 19.712 seconds, including 4.627
seconds setup and 6.859 seconds bound checks; 1,710 warm-start calls total
0.586 seconds. These overlapping partition wall sums locate costs, not elapsed
pipeline time. The instrumented whole process takes 11.014 seconds / 20.590
CPU seconds, and every score matches reference.

The fourteenth build argument `immutable` opts the CLI's already-owned,
unchanging fixture into a private immutable-orbit session. The owner must keep
arrays alive and unchanged until unbind/rebind or destruction. Initial state
checks are reused; the endpoint bank avoids an authority copy and per-site
byte comparisons. Normal public API calls remain checked. Changed metadata
falls back to the checked path. Ending/rebinding a session invalidates caches,
even when an address or generation is reused. This is an explicit lifetime
contract, not a claim to detect writes that violate the declared lifetime.

`immutable-orbit-host-v1/` preserves both 400-point host traces exactly.
Session/bank tests cover lifetime transitions, metadata and address changes,
restored mutable checking and a new perfect-match authority. The scorer and
session test pass with ASan/UBSan (`score.cpp` instrumented; orbit/search/vendor
objects uninstrumented). Both changed tests pass on physical ARM.
`immutable-orbit-arm-v1/` measures double/immutable/immutable/double:
9.910983/8.485332/8.481249/9.813490 seconds, a 14.0% mean reduction. All scores
match. Immutable CPU is 15.790049/15.806775 seconds versus 18.585621/18.567686;
peak RSS drops from about 98.4 to 76.5 MiB. No PGO is used in this comparison.
Full ARM search qualification of the new session mode remains pending.

`horizon-range-host-v1/` preserves both complete host search traces after moving
the track's inclusive horizon knot range outside the satellite loop. Tests
compare prepared/ordinary queries against the original predicate for all tested
ranges, including nonfinite control points, empty/out-of-range queries and
malformed prepared bounds. Host sanitizer and physical ARM tests pass.
`horizon-range-arm-v1/` measures immutable/range/range/immutable on 16 points:
8.558994/7.062242/7.064391/8.484447 seconds. Mean reduction is 17.1%; all scores
are exact. Prepared-range CPU is 12.957707/12.946235 seconds versus
15.772732/15.787132 seconds. Peak RSS remains about 76.5 MiB. Both variants
use the same explicit immutable session and ordinary compiler optimization.

`score-pgo-immutable-arm-v1/` retrains the changed scorer rather than reusing a
profile from different source/ownership semantics. The PGO recipe now records
and verifies the session mode as well as source hashes. Training and held-out
evaluation point sets retain the earlier disjoint protocol. The complete ARM
search is still required before replacing the current full-run timing table.

The new PGO build passes core, interpolation and immutable-session tests on
physical ARM. Its disjoint held-out ABBA mean is 6.879294 seconds versus
7.134739 seconds for the ordinary prepared-range control; every score matches.
The build recipe rejects a training/use session-mode mismatch before compiling.

`regional-arm-session-pgo-300s-v1/` then completes **all 400 points in
160.054509 seconds**, consuming 302.045997 CPU seconds, peak RSS 79,720 KiB.
Its full search JSON equals the prior ARM result exactly. Against host, all
coordinates, selection and status match; only the previously diagnosed two
intermediate score differences remain, passing the declared 1e-9 Hz tolerance.
Full selected-site association JSON equals host exactly, in 2.288712 seconds /
3.462636 CPU seconds. The workload and regional search policy are unchanged.

This brings separate-run total CPU accounting to about 628 seconds per scan,
still above the 600-second two-core ceiling and without scheduling headroom.
No sustained concurrent pipeline result is claimed. A next measured target is
input-buffer ownership: the recorded reader currently allocates and zeroes a
full 2.4-MB dwell buffer per visit even in 400-kB prefix mode. Its cumulative
read wall time is 111.798 seconds, overlapping 286.984 seconds of worker service
(266.217 detection, 16.270 projection). These wall sums do not isolate CPU
cost; buffer reuse must be measured before claiming a saving.

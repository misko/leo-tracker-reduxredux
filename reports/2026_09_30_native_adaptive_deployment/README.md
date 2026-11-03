# Native ARM implementation and PLUTO+ deployment

This report records implementation and measured qualification boundaries for
the plan in [`plan.md`](../../plan.md). Three delegated SOL agents implemented
detector, tracking/pipeline, orbit/location, firmware and local-device work;
the coordinating agent implemented runtime, projection, policy continuation,
independent pacing and physical deployment checks.

**Status: firmware installed; native components deployed and tested; continuous
server-equivalent IQ-to-location operation is not yet qualified.** The explicitly
authorized live qualification is recorded separately below. Scientific detector
comparisons use saved DS9 IQ; live candidate counts have no recovery ground truth.
The scanner composition currently ends at counter-tagged detector events.
Projection, track construction and location inference are tested replay
components. The new persistent coordinator and bounded application handoff pass
bounded component tests; integration into the live scanner executable
remains open.
This is a development deployment, not a completed continuous location service.
The longest live run completed 585 seconds but dropped four detector jobs;
the current four-entry queue build has a successful 60-second integration check,
not a long-duration lossless qualification.
The candidate scanner is a bounded qualification executable (at most 30 minutes
per run), not an unattended daemon. The continuing policy history is tested
separately; indefinite service lifecycle and online location publication remain
implementation work.

The new experimental deployed-server-wrapper mode passes the
[strict 80-dwell host comparison](ds9/deployed-server-wrapper-strict-comparison.json):
295/295 passing server detections, all 880 complete candidates and all 400
unavailable slots agree by rank within frozen numerical tolerances. Three
[ARM representative cases](ds9/arm-deployed-wrapper-representative-comparison.json)
also pass (8/8 passing detections; 48 total slots), but take
[12.8-23.2 seconds per 120-ms dwell](ds9/arm-deployed-wrapper-performance.json).
This experimental mode is not real-time and has not replaced the installed
fast detector. Its scalar coarse search dominates runtime; optimization is
being evaluated separately from the frozen scientific result.
The [four-CFO register experiment](ds9/arm-deployed-wrapper-register4-performance.json)
preserves every non-timing field on these ARM cases and reduces normal calls to
10.3 seconds and the fallback case to 18.3 seconds, about a 20% improvement.
It remains far above the 120-ms arrival interval.

The recorded application composition now scores all 11 tracks against 11,129
TLEs on PLUTO+ in 29.52 seconds. This test exposed architecture-dependent
support-moment rounding that changed hashed training partitions and the score.
The corrected arithmetic produces byte-identical support records, digests and
masks on host and ARM, with a score difference of 1.3e-10 Hz. The original
failure and corrected results are retained in the
[portability evidence](runtime/fractional-support-determinism.json).
This is a saved-candidate replay at one point, not raw-IQ E2E or real-time search.
The [profiled replay](application/profiled-qualification.json) separates that
fixture cost: 18.62 seconds prepares the saved prefix, 1.61 seconds publishes
tracks, 3.82 seconds builds the full-catalogue orbit cache, and 1.33 seconds
scores the location. Reference-only comparison costs another 2.02 seconds.
The whole-test duration is not steady-state inference latency.
Strict server support authority remains a distinct gap. A
[compatibility prototype](runtime/server-support-compatibility-feasibility.json)
matches all saved moments on x86, but ARM's power function leaves 446 tiny
third-moment bit differences. They pass numerical tolerances and still alter
hashed partitions. The production deterministic arithmetic is unchanged;
host/ARM reproducibility does not imply byte-identical server scores.

## Firmware and installed bytes

The consolidated development release is
`91df0781fb158853e047`, installed at
`/mnt/glrtbench/native-adaptive/releases/91df0781fb158853e047` with
`/mnt/glrtbench/native-adaptive/current` pointing to it. The
[release receipt](release.json) binds every binary/library hash and records
the on-device scanner fake-source, local fake-driver, runtime, tracking,
location, capability and continuous-policy checks. The scanner's no-argument
execution passed and reported `capture:false`. No boot service was enabled.
The scanner loads the exact benchmarked detector shared library through its
local `$ORIGIN` search path. The prior combined research build remains in its
own release directory and [historical receipt](release-6c98b71d1c8eeed5483d.json).

PPU installed `v0.59-plutoplus-spf-dual-rx-counter-fix` on `192.168.1.15`, serial
`104000b29905000e17000800065934759d`. The receipt is
`b94ac3ab-cbab-4f6b-90ad-cb4cd0091392`. The explicit PPU force-flash command is
for blank-serial USB recovery; this device used the qualified PPU LAN update
adapter with the exact requested 0.59 image. The adapter completed all 18
phases, including protected-region/QSPI verification and post-reboot identity,
firmware, TX-safe and capability checks. See [firmware evidence](firmware/README.md).

Executables and libraries are installed in hash-bound version directories
under `/mnt/glrtbench/native-adaptive/` on the existing SD filesystem. Deployment
receipts record SHA-256 hashes and actual commands/results:

- [Runtime/projection](runtime/arm-runtime-current.json)
- [Detector, ordinary and fractional](ds9/arm-detector-deployment.json)
- [Cached fractional detector](ds9/arm-cached-deployment.json)
- [Tracking and local source](component-arm-deployment.json)
- [Final tracking/E2 build](tracking/final-arm-deployment.json)
- [Location scorer](location/arm-component-replay.json)
- [Measured timing and observation ingress](timing-ingest/README.md)
- [Acquisition-thread timing port](scanner-timed-counter-review.json)
- [Recorded application stage timings](application/profiled-qualification.json)
- [Persistent coordinator and scored DS9 prefix](online/scoreproof-review.json)
- [Portable USB adapter qualification](usb/qualification.json)
- [Transport-neutral source-port audit and CPU-only fake ARM receipt](ds9/c10-common-source-port-audit.md)

The SD filesystem was mounted after flashing. Application boot activation and
automatic remount/service configuration are not established by these receipts.
The local capture adapter uses local libiio and firmware ioctls; Ethernet carries
installation bytes and diagnostic results, not that adapter's IQ path.

Native bufferless preparation was also exercised on the board: two profiles,
including profile 0, were compiled/attested and the original 30.72 MS/s source
and capture rates, 18 MHz bandwidth and AGC modes were restored. Preparation
temporarily used 2.5 MS/s, 2.5 MHz bandwidth and paired 40 dB manual gains.
AGC gain readback is observational and changes after restoration; the original
gain-control modes are preserved. The diagnostic creates no IQ buffer and
never activates the firmware scan owner. Both the
[single-profile](radio-prepare-single-fixed-arm.json) and
[two-profile](radio-prepare-two-fixed-arm.json) checks pass on the final build.
The single-profile test exposed a suppressed same-frequency write; the fix
forces an attested distinct ordinary tuning step before returning to the target.
Its regression fake models that driver behavior, and preparation failures now
retain their restoration evidence.

The v0.59 lifecycle is counter-session reservation -> bufferless preparation ->
firmware scan ownership/capture -> firmware release -> full settings restoration
under the reservation -> close. Ordinary IIO writes are blocked while firmware
scan ownership is active, so preparation cannot run inside that phase. During
preparation/restoration, unrelated local or network IIO writers must remain
quiescent; the reservation excludes other counter/tandem sessions only.

## Existing-data and component evidence

| Boundary | Observed result | Qualification limit |
|---|---|---|
| C1 windows | All 80 DS9 dwells match byte hashes/counters at four delivery chunk sizes | Existing recordings are 120 ms visits; longer/gapped visits have synthetic unit coverage |
| C2 ordinary GLRT | 298 candidates, 286 positive candidates, 90 positive RX windows; all ordinary fields match the earlier control-qualified ARM output | Native-control regression, not server equivalence |
| C2 fractional extension | 292 complete, 6 unbracketed; 286 positives; ordinary fields preserved | Different acquisition/retention from deployed server |
| C3 projection | 24,681 candidate records -> 11,747 expected observations on host and ARM; exact candidate/group IDs and UTC support timestamps | Starts from saved fractional candidates |
| E1 recorded bridge | Four raw DS9 visits -> 41 newly computed native candidates -> 14 qualified physical observations; source hashes, identities, CFO and UTC support bounds checked | Uses timing/RF authority only from the saved fixture; no saved candidate answers in inference; not server parity or a complete scan |
| Complete recorded scan | All 2,215 visits/4,430 receiver windows -> 23,477 candidates -> 11,971 observations -> 64 tracks using 3,110 observations -> two point scores and both 400-point regional searches | Host replay; fresh graph identities/masks; scientific server parity remains false |
| C4 tracks | Host rebuilds 64 tracks/3,372 points, exact source membership/support/aliases | Six duplicate-rank ties change candidate/tracklet IDs; full identity parity fails |
| C5–C7 location | Catalogue scorer, TLE orbit implementation; integrated native scorer and scheduler match both frozen ordered 400-point searches and exact incumbents (maximum score delta 3.02e-11 Hz) | Original budgets exhausted with 95/175 deferred cells; global convergence, fresh-input parity and continuous ARM deadlines remain open |
| C8 policy | Original policy regression plus 20,000-visit continuous-history test; host/sanitizer/ARM passes; live deadline defects reproduced and fixed | Measured live timing qualification below; no live scientific recovery truth |
| C9 executor | Bounded queues, worker counts 1/2/4, failures/cancellation/backpressure and independently paced detector arrivals | Default-priority live concurrency exposed drops; revised execution configuration below |
| C10 local adapter | Fake-provider host/sanitizer/ARM tests pass; physical local DMA, recalls, capability ioctl and preparation/restoration exercised | Candidate-only capture; complete online location integration remains open |

The integrated C7 reference-search receipt and complete traces are in
[`location/c7-reference-search-v2/receipt.json`](location/c7-reference-search-v2/receipt.json).
The diagnostic CLI uses schema v2 to report the original point budget, deferred
cells and stop reason explicitly. Host integration tests exercise the actual
scorer and scheduler together with the original 400-point policy.

The C4 duplicate selections differ by at most `1.164e-10 Hz`; tiny numerical
differences still matter because IDs determine later train/held-out partitions.
The E2 adapter derives fresh graph observation IDs, support digests and masks
from recording authority rather than borrowing reference masks. All 58 exact
track identities reproduce their reference digests and masks; six receive new
identities/masks. On host these change the two point scores by -0.227336 and
+0.560436 Hz, preserve all satellite choices and change one tau choice per
point. See [tracking comparison](tracking/comparison.json) and
[E2 integration](tracking/e2-pipeline.json).
The [four-visit E1 receipt](runtime/e1-recorded-four.json) records the
IQ/template hashes and a separate native analysis identity; only timing/RF
authority is read from the saved projection fixture.

The subsequent [complete-scan replay](ds9/complete-scan-e1/README.md) reads and
verifies the entire 15.95 GB decoded recording through the public read-only
store. Its graph authority is recomputed from newly detected observations.
The location input reuses only receiver sites and orbit states, discarding
the reference fixture's track payload. The complete host path through track
construction takes 82.09 seconds, including 41.40 seconds of verified corpus
read/decompression/hash work. The two point scores are 268.344678 and
415.745327 Hz, differing from the server-derived E2 run by +44.509085 and
+4.316737 Hz. Equal 64-track counts do not establish matching physical tracks
or location accuracy. Native analysis identities are intentionally distinct,
so exact tracklet-ID intersection alone is not a physical recovery metric.

Both predeclared regional searches were then executed on those new native
tracks. Each evaluated 400 points in about 79 seconds on the host and returned
`complete=false` because its point budget was exhausted. Sacramento retained
the reference incumbent coordinates. Reno selected an incumbent 460.977 km
from the reference incumbent. These are bounded-search comparisons, not
converged positions or ground-truth accuracy estimates. See the
[regional search evidence](ds9/complete-scan-e1/c7-search/summary.json).

The newly derived native location fixture was also scored on the final ARM
release: both point outputs, including every selected satellite, tau and
residual field, exactly equal the host outputs. This costs 17.79 seconds with
two workers and 24,168 KiB peak RSS. It validates the ARM scorer on the new
native tracks, not a full all-ARM raw-scan replay. See the
[ARM native-track score receipt](location/complete-scan-native-arm.json).

## Recovery against the deployed server

The positive threshold is margin >=0.025. The ordinary control regression's
286/286 recovery is **not** the deployed-server recovery rate.

The richer server comparison uses one-to-one matches with circular integer
epoch distance <=2 samples and **acquired** CFO distance <=10 kHz. Matching on
final tracking CFO can conflate aliases; the earlier preliminary 223/295
estimate is superseded. Under the corrected rule, the additive fractional
mode matches **210 of 295 server-positive candidates (71.2%)**. These are
algorithm-correspondence counts, not independent ground-truth detection rates.

Of the 85 unmatched server positives, the diagnostic attributes 24 to an
absent retained epoch, 38 to a different acquired-CFO hypothesis and 23 to
collapsed hypotheses without a distinct native candidate. The ordinary coarse gate discards 982 of the 1,280
retained peaks before its 298 candidate results. A separately identified
coverage mode is required; changing ordinary candidate inventory would break
the frozen baseline. See [server comparison](ds9/fractional-server-comparison-summary.json).

An isolated full-native coverage mode retains all eight hypotheses and reaches
252/295 positive correspondences (85.4%) on the host panel. It also emits many
additional hypotheses and is not server-equivalent. Both counts use the audited
one-to-one comparator; an earlier detail-report bug duplicated displayed pairs
without changing the summary totals, and the regenerated report now asserts
endpoint uniqueness. Scientific qualification remains false.

The experimental server-reference kernel implements maintained symbolwise
acquisition under supplied search geometry. Its default-geometry panel run
matches only 111/295 server positives (37.6%); the deployed server's per-visit
residual bounds and peer-triggered 22-anchor fallback are not yet carried into
that wrapper. It is a diagnostic implementation, not the scanner default or a
qualified replacement. See [reference-kernel comparison](ds9/server-reference-comparison.json).

Coverage and reference modes are separate research builds. The production
detector excludes them: including their kernels and CLI paths in the same GCC
LTO build caused a measured performance regression. The corrected production
CLI, replay executable and shared library are byte-identical to the earlier
fast cached artifacts. See [build regression closure](ds9/hotfix-arm/summary.json).

## Physical PLUTO+ timings

All times below are measured on the flashed board with no live capture.
Detector rows are one pass over 80 dual-RX saved dwells at 2.5 MS/s. Kernel
call wall time excludes file preload, context setup and JSON serialization.

| Detector mode | Mean | p95 | Maximum | Calls >120 ms |
|---|---:|---:|---:|---:|
| Ordinary | 53.87 ms | 81.78 ms | 109.79 ms | 0/80 |
| Fractional with identical-evaluation cache | 90.29 ms | 177.17 ms | 243.14 ms | 22/80 |

These rows measure the exact installed detector bytes; p95 uses nearest rank. Peak
process RSS was 31,404/31,524 KiB, and the calibrated XADC temperature stayed
between 59.31 and 61.64 C across these runs. CPU frequency was not measured.
See [final release measurements](ds9/qualified-release-arm/summary.json).
The measurements were collected in release `b6722a3a7d8b8eb8b796`; the final
release changes scanner scheduling, telemetry and radio setup/restoration; its receipt verifies identical
detector CLI, replay and shared-library hashes. Those measurements therefore
apply to the installed detector.
The earlier uncached fractional build averaged 106.21 ms, with 33/80 calls over
120 ms; it is retained as optimization evidence rather than the installed default.

Cached and uncached fractional candidate fields are exactly equal across all
80 calls. The optimization avoids duplicate scientific work; it does not
improve server candidate coverage.

The superseded combined research/release build measured 61.98 ms ordinary and
107.14 ms cached fractional means on the same 80-dwell panel. Its native
coverage mode cost 575.69 ms mean, 623.60 ms p95 and 727.69 ms maximum, with
all 80 calls exceeding 120 ms. These are diagnostic costs, not production
scanner performance. The one-dwell ARM reference-kernel smoke check passed;
the full server wrapper remains absent. See [superseded build measurements](ds9/final-arm-summary.json).

Independent paced replay uses eight saved dwells repeated ten times, a
producer clock that never waits for the consumer, one detector worker and
four queue slots. At 120-ms arrivals, cached fractional processing completes
80/80 without rejection, maximum queue delay 36.21 ms, maximum arrival-to-finish
156.29 ms and 20 late results. This small repeated workload demonstrates
bounded queue behavior, not continuous-capture qualification. At deliberately
overloaded 60-ms arrivals, the uncached implementation rejects 24/80 jobs
explicitly; it does not hide loss by slowing the producer.

With a one-worker full-catalogue scorer running concurrently, the cached
detector again completes 80/80 without rejection. Maximum queue delay is
43.37 ms, maximum arrival-to-finish 163.48 ms and 21 results exceed 120 ms.
The scorer takes 35.50 s and reproduces its standalone output exactly. This
tests the proposed one-detector/one-background CPU split using saved data;
it does not exercise local DMA, RF, retunes or capture interrupt load. See
[concurrent replay evidence](runtime/paced-with-location-summary.json).

Full saved-scan track construction costs **78.07 s**, CPU 78.04 s, peak RSS
7,288 KiB on ARM. Incremental track maintenance remains needed for frequent
online updates. Full-catalogue scoring of two points from saved tracks costs
**35.37 s with one worker** and **19.22 s with two**, with exactly equal output
and about 24 MiB peak RSS. These whole-process times include fixture loading,
setup and serialization. They do not meet the provisional five-second location
update goal and do not establish the duration of a complete 400-point search.

## Authorized live qualification

The user explicitly authorized this bounded campaign on `192.168.1.15`.
The [budget ledger](live-qualification/budget.json) conservatively reserves each
requested run plus its external shutdown allowance against a 1,560-second
aggregate cap. Two early failures retain their original reservations but charge
the rounded-up complete host process duration, with SHA-bound completion and
cleanup evidence; only proven unused time is released. A watchdog argument
rejected before `fork` charges zero, backed by archived binary disassembly.
IQ remains on PLUTO+. Corrected runs write diagnostic events to
the SD card during capture and retrieve them afterward; no Ethernet/USB IQ
transport participates in capture or analysis.

The first 15-second smoke completed 53 visits. A requested 120-second baseline
then stopped early after 16.64 seconds with policy `-ETIME`, despite 59 intact
visits and no detector queue drops. These failures are preserved as evidence.
The 120 ms DMA geometry discarded block tails and produced approximately
240 ms visit-start cadence. The original retune calculation also added recall
latency even when recall completed inside the nominal settling budget.

The corrected scanner uses explicit 20 ms blocks (50,000 dual-RX samples),
matches the maintained piecewise recall/settling contract, and skips recall
for consecutive visits to the same profile. Host, ASAN/UBSAN and ARM tests
cover timing, same-profile transitions, all supported dwell lengths and CLI
parsing. An independent review verified the exact v0.59 counter/DMA geometry.
Versioned v2 events add recall counters, energy support, detector queue/runtime,
all scanner counters, stop reasons and cleanup statuses; non-finite values
are valid JSON `null`.

The corrected 15-second smoke completed 86 intact visits, with one incomplete
visit at the requested wall deadline, no missing samples and no queue drops.
Mean visit-start interval was 152.09 ms. All measured same-target revisits were
below three seconds. Cleanup and external radio-state comparison passed.
The CLI currently returns exit 7 / `-ETIMEDOUT` for the deliberate wall deadline;
this is explicitly recorded, not reclassified as process exit success.

The timing contract is selection-to-valid, not an unconditional 20 ms guard
after recall. In the corrected smoke, the last delivered DMA watermark used
for selection lagged recall start by 1.57–38.36 ms. Nominal-budget recalls had
1.38–18.06 ms of post-recall guard; late recalls had the full 20 ms. Every
record matched the maintained formula. A fresh counter snapshot at selection
is a potential future refinement, not part of the measured build.
Likewise, zero missing samples means accepted visits are internally contiguous;
intentional transition gaps remain. The corrected smoke's valid-window duty
was approximately 79.1% across the completed-visit span.

The next 180-second run completed 1,175 intact visits without detector loss,
but contained one real revisit-limit breach: target 2 visits 560 to 580 were
3,020.152 ms apart. Selection predicted arrival exactly at its deadline;
recall completed 0.152 ms beyond that nominal time, and the required late-recall
settling rule added a full 20 ms. Policy commit accepted the late actual start.
This is a failed three-second acceptance criterion, not a rounding tolerance.
The subsequent 180-second run with a 240 ms active ceiling completed 1,173
intact visits with no measured three-second breach. Both runs had only QUIET
complete feedback and actual 120 ms dwells, zero missing samples/queue drops,
and clean deadline shutdown/restoration. They do not exercise live ACTIVE
dwell expansion. Further RF was paused for actual-start deadline enforcement.

Release `32c6f7df4158814778d7` addresses that breach with a fresh coherent
counter snapshot before each selection, separate 40 ms admission/20 ms physical
settling budgets, and actual-start commit revalidation against both the selected
target's deadline and the remaining earliest-deadline schedule. It fails closed
if actual timing makes that schedule infeasible. The exact recorded breach,
remaining-target feasibility, overflow, same-profile behavior and 20,000-visit
history rollover have host/sanitizer tests. The new scanner and policy tests
also passed on PLUTO+, including the exhaustive 256-mask policy test. See
[review and build evidence](scanner-revisitfix-review.json). The first deployment
attempt's 45-second limit was insufficient for that exhaustive ARM CPU-only
test; it passed with a 300-second bound before release promotion.

The first concurrent long attempt on that release failed after 232.47 seconds.
All 1,350 capture visits were intact, but only 1,342 detector jobs completed:
eight were explicitly dropped under queue pressure. The largest observed
committed revisit remained below three seconds (2,960.066 ms); the policy then
stopped with `-ETIME` instead of accepting an infeasible future schedule.
Cleanup succeeded. Default-priority background catalogue scoring therefore
does not pass continuous operation. Mean visit-start cadence increased to
170.58 ms, with a maximum 215.88 ms; the largest inter-visit gap was 95.88 ms.
Scoring uses saved DS9 tracks, not online observations from this capture.

Release `cb6d74431cd0d4afa271` increases the policy admission allowance to
100 ms while retaining 20 ms physical settling, fresh snapshots and fail-closed
actual-start validation. Its qualification configuration pairs a normal
priority scanner with one background scorer worker at `nice 19`. The allowance
covers the measured 95.88 ms maximum, not an arbitrary operating-system delay;
unexpected overload can still stop the scan or drop detector work explicitly.
[Source/build review](scanner-admission100-review.json) includes the recorded
load regression and host, sanitizer and ARM tests. The detector bytes remain
identical to the saved-DS9 scientific benchmark.

That configuration completed the requested **585 seconds** (9 minutes 45
seconds, with a separate 600-second watchdog). It produced **3,468 intact
visits**, zero missing samples and no three-second revisit violation; maximum
revisit was **2,871.832 ms**. Mean start cadence was **168.11 ms**. One final
visit was explicitly incomplete at the wall deadline, and every cleanup phase
and external radio-state comparison passed.

However, the detector's two-entry pending queue dropped **4 of 3,468 complete visits**;
3,464 were analyzed. This is 99.885% processing admission, **not a scientific
recovery rate**, and does not pass lossless continuous analysis. Detector
runtime mean/p95/max was **70.50 / 202.39 / 401.73 ms**, with maximum queue wait
414.63 ms. Peak scanner RSS was **24,040 KiB**; sampled XADC temperature ranged
56.72–60.29 C. All completed feedback remained QUIET with actual 120 ms dwells.
See the [strict telemetry summary](live-qualification/summary.json) and
[counter timing audit](live-qualification/admission100-continuous-timing-audit.json).

All **14** low-priority saved-track scores completed within the observed scanner
lifetime and exactly matched every reference output field. Whole-process score
time was **35.365 s mean**, 34.234–36.404 s range. This verifies contention and
numerical reproducibility, not a live IQ-to-location handoff. See the
[scorer receipt](live-qualification/concurrent-location-nice19/receipt.json).

The final installed release, `91df0781fb158853e047`, increases the pending
detector queue from two to four entries. It retains exactly one detector worker
and five fixed outstanding slots. Including the acquisition copy, maximum IQ
ownership is 14.4 MB at 120 ms or 43.2 MB at 360 ms. Extra capacity absorbs
bursts at the cost of result freshness; a five-job train at the observed maximum
service time approaches two seconds, not a strict 120 ms latency guarantee.
The new deterministic burst test proves five admissions, two explicit overload
drops and queue high-water four. Host/sanitizer/ARM checks passed; unchanged
policy tests and detector scientific evidence are reused by exact byte hash.
See [queue review](scanner-queue4-review.json) and
[saved-IQ four-entry queue evidence](live-qualification/saved-pacing-4slot/README.md).

Its **60-second controlled restart** completed **350 intact visits and all 350
detector jobs**, with zero missing samples/drops and maximum revisit
**2,815.153 ms**. A concurrent nice-19 score matched exactly in 35.420 seconds.
The final partial visit was explicit UNKNOWN at the requested deadline.
Cleanup and external restoration checks passed; the final device check found
no scanner or scorer left running. This short run does not demonstrate long-run
losslessness: its observed queue high-water was only one. See
[restart receipt](live-qualification/queue4-controlled-restart-receipt.json),
[restart timing](live-qualification/queue4-restart-timing-audit.json) and
[final device state](live-qualification/final-device-state.json).

The campaign is closed with a conservative **1,526 seconds charged against
1,560 seconds authorized**. All ledger entries are finished; earlier failures,
no-child rejection and proof-bound reservation adjustments remain visible.
No automatic service or indefinite RF collection was enabled.
The [final qualification receipt](live-qualification/qualification.json) binds
the result artifacts and keeps passed integration checks separate from open
scientific, lossless and online-location gates.

These runs qualify only the candidate-scanner boundary and observed input.
Live candidates have no matched ground truth, so their count is not a recovery
rate. The persistent coordinator, UTC/counter bracket and live application
composition now have separate component and CPU-only device tests. Those tests
do not extend this closed RF campaign into live IQ-to-location qualification;
mixed-edge routing and integrated result freshness retain their own gates.

## Remaining acceptance gates

The opt-in live application is installed at
`/mnt/glrtbench/native-adaptive/live-current/leo-adaptive-live` on 192.168.1.15,
separately from the existing scanner release. Its no-argument path opens no
radio. Host, sanitizer and physical ARM CPU-only tests cover analysis,
late/missing timing, capacity loss, ownership and failure cleanup. The CLI
exposes explicit ten-second (32 one-second knots) and 600-second (96 ten-second
knots) development profiles. The current `d75596931e4598d5` release includes fixed
source-time cadence accounting, publication deferrals, bracket-bounded
snapshot/result ages and snapshot-to-result monotonic duration. It also pins
started searches across newer publications and permits refinement batches to
progress with one-point execution slices. Caller-driven execution tests cover
interleaving, stale evidence and failure cleanup; physical ARM lifecycle and
CLI tests pass. Local capture now uses the common source-port engine. See the
[current deployment receipt](application/fast-bin-deployment.json).
Its successful
installation does not close live IQ-to-location, global interpolation or
full-standard qualification. Capability and summary output use new v3 schema
identifiers; the historical v1/v2 contracts remain unchanged.
See the [application receipt](application/live-qualification.json).

The [tracking cache experiment](tracking/bin-cache-optimization.json) preserves
the complete DS9 output byte for byte while reducing measured ARM full-scan
tracking from 78.07 to 39.50 seconds. The guarded implementation is now included
in the application build; the measured timing belongs to the saved prototype
binary, with final guarded component tests recorded separately.

The separate [persistent prefix experiment](tracking/prefix-cache-causal-qualification.json)
matches all 60 causal host prefixes and both final ARM prefixes exactly. On
PLUTO+, the warm final reconstruction takes 24.045 seconds versus 39.333 cold;
seeding takes 62.850 seconds. It remains disabled because it misses the
five-second target and cannot reuse its bins after rolling-history expiry.

The deployed [guarded bin-index accelerator](tracking/fast-bin-qualification.json)
also helps cold reconstruction without a persistent cache: alternating ARM
runs take 33.52–33.59 seconds versus 39.39–39.62 seconds for the frozen control.
All outputs are byte-identical, and all 60 causal host prefixes match. A physical
phase profile attributes approximately 7.1 seconds to bin calculation, 13.9 to
histogram/peak scanning, and 11.5 to candidate fitting. Real-time qualification
remains open.

The current release also includes [exact refined-fit caching](application/exact-fit-cache-deployment.json).
Its production ARM reconstruction takes 29.76 seconds with the same output
bytes. Host/sanitizer tests, all 60 causal prefixes and physical component tests
pass. Cache-only allocation and capacity failures preserve the uncached result;
the cache remains local to one immutable lane. This is a component improvement,
not a passed continuous five-second application deadline.

The preceding release adds [contiguous selected-point weights](application/chosen-point-deployment.json).
Compiler-matched physical ABBA shows a 2.93% further reduction; the production
ARM reconstruction takes 28.958 seconds with identical output. All 60 causal
prefixes, host/sanitizer/physical component tests, and full host application
replay pass. The full host replay preserves 11,747 observations, 64 tracks and
the exact reference score. Device lifecycle and CLI checks pass. The preceding
full physical application replay belongs to the retained `bc0ce529d530995f`
composition; continuous five-second timing remains unqualified.

The current release adds [peak-cutoff filtering](application/peak-cutoff-deployment.json),
preserving histogram order and peak ties. Matched physical ABBA improves tracking
by another 3.56%; the production ARM executable takes 27.857 seconds. Independent
review, 60 causal prefixes, 30 tie/capacity configurations, component checks and
full host application replay pass. Continuous real-time qualification remains open.

The [full-history orbit cache benchmark](online/full-history-orbit-window.json)
now covers all 11,129 satellites with 96 ten-second knots and two state banks
on PLUTO+. Peak process memory is 114,664 KiB; rebuilding takes 9.9 seconds.
The proposed 950-second cache span permits approximately 320 seconds of reuse
with a 600-second observation history. All 66,774 boundary/midpoint coverage
checks pass, including preservation of actual decimal and Alpha-5 identifiers.
This establishes memory feasibility; full-history paced execution and global
interpolation accuracy remain separate gates.

The [paced Analysis replay](application/paced-analysis-lattice-review.json)
passes on physical ARM with an independent producer at recorded speed: 846
events over ten seconds produce 394 observations and 11 matched tracks against
all 11,129 satellites. Queue high-water is 191 with zero drops; paced/unpaced
and host/ARM scores match exactly. The harness preserves the original recorded
clock authority before inference. It configures 600-second history but does
not exercise a 600-second evidence span, IQ acquisition or the detector. Its
ten-second-knot score differs by 0.004308 Hz RMSE from the one-second profile;
that measured difference is separate from cross-architecture equivalence.

The [full available-span replay](application/full-span-paced-analysis.json)
then paces all 24,681 persisted projected events across 299.802 source seconds.
It is lossless for all 11,747 accepted observations, reconstructs 64 tracks,
and matches the independent host one-point score within `3.7e-13 Hz` RMSE on
physical ARM. It fails the intended five-second continuous freshness gate:
42 of 59 cadence requests are missed, maximum snapshot-to-result duration is
56.72 seconds, and final drain takes 91.36 seconds. This is a measured
fail-closed result, not a 600-second evidence run or an IQ/detector/RF claim.

| Gate | Current status |
|---|---|
| E1 IQ -> physical observations | Complete 2,215-visit host replay executed; integrated server-equivalent gate not passed |
| E2 reference observations -> location | Executed on host and ARM; exact host/ARM output, six server identity ties and resulting partition differences retained |
| E3 complete raw scan -> location | Complete host recording processed through all numerical stages and both 400-point searches; scientific parity not passed; all-ARM full-scan execution remains unrun |
| E4 paced continuous execution | Saved/live capture, overload and background-scoring contention measured; strict 120-ms detector deadlines not met; bounded live results above |

The complete location scan contains 2,215 visits at 7.5 MS/s, approximately
15.95 GB raw IQ. The full host replay now covers every visit; the earlier four
retained location dwells remain a separate subset fixture. Scientific
acceptance still requires acquisition/retention parity, resolution of the regional
search differences, platform-specific identity/tie assessment, continuous local
capture with analysis concurrency, and measured result freshness. The Pi USB
adapter and Pi performance are separate unqualified work.

No automatic service is enabled and no real-time equivalence is claimed.

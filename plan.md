# Native ARM adaptive analysis implementation plan — 2026-09-30

Current requested qualification extension (2026-10-01): finish the bounded
queue-32 test, then process three distinct DS9 raw-IQ scans sequentially on ARM
and compare every stage with server output. The frozen selection, stagewise
comparison protocol, fresh server jobs and prepared inputs are in
`reports/2026_10_01_arm_three_scan_sequence/`. The captures are
`scan-fw-f363c7f29141d0b1`, `scan-fw-b34e380766e24b3b` and
`scan-fw-ee2831131a88440f`; the last adds upper-edge coverage. ARM execution and
all comparisons are complete: queue 48 processes all 6,649 dwells without loss,
but maximum latency is 5.479 seconds and loaded downstream times are 304.410
and 310.180 seconds, failing the original five/300-second limits. Native GLRT
CFOs and passing decisions agree exactly; represented server segments are
55/62, 58/64 and 53/62. A fit-summary-sensitive identity changes held-out
partitions and prevents independent full-chain positioning reproducibility.
Fixing versioned identity semantics and meeting loaded runtime gates remain open.
Native-control parity and standard-server algorithm agreement are separate.

This section records the approved PLUTO+/Pi development plan. The pre-existing
server architecture plan follows unchanged. Native execution is an additive
deployment target; published server contracts and scientific fixtures remain
unchanged. Current task: implement, test on existing DS9 data, deploy to
192.168.1.15, and use PPU to install the exact 0.59 release requested by the user.
Do not infer that a successful install establishes real-time scientific parity.

The [native completion audit](reports/2026_09_30_native_adaptive_deployment/application/native-completion-audit-v1.md)
maps the original acceptance gates to current evidence and remaining work. The
goal remains incomplete: component deployments do not establish strict server
parity, continuous real-time analysis, or physical Pi/USB qualification.

The bounded [recording inventory](reports/2026_09_30_native_adaptive_deployment/application/history-corpus-inventory-v1.md)
found no genuine 600-second fixture among 2,205 readable finalized manifests
in 2,303 recording directories; 98 entries remain unassessed. The longest
source-counter span is 300.1272296 seconds. DS9 supplies 300 seconds of recorded
samples and 299.8017789333333 seconds of retained event evidence. The full-history
gate remains open; concatenating or repeating recordings cannot close it.

The opt-in exact score-cache implementation passes a full host comparison of
800 search-point records and 51,200 track winners across the last three DS9
prefixes. Its first bounded ARM replay failed by kernel OOM: the diagnostic
harness retained cached and independent cold orbit/scorer contexts together,
peaking at 436,292 KiB RSS before exit 137. The corrected sequential-lifetime
harness passes on ARM: one-site warm scoring takes 0.820/1.081 seconds versus
8.231/8.307 seconds cold, with both point results and all 128 track winners exact.
It retains 487,232 bytes of cache payload and peaks at 301,068 KiB process RSS.
This is a deliberately reduced one-root policy, not a 400-point regional ARM
qualification. Both the failed [physical attempt](reports/2026_09_30_native_adaptive_deployment/online/exact-score-cache-v1/physical-arm/rejected-v8/receipt.json)
and corrected [physical receipt](reports/2026_09_30_native_adaptive_deployment/online/exact-score-cache-v1/physical-receipt.json)
are retained; the live application does not enable this cache.

The [saved-event application integration](reports/2026_09_30_native_adaptive_deployment/application/exact-score-cache-integration-v1/README.md)
now exposes an explicit test-only cache budget and owner-published telemetry.
Host, ASan/UBSan and TSAN component checks pass; full host and sanitizer replay
pairs preserve final science, while explicitly failing accelerated freshness.
The [physical ARM pair](reports/2026_09_30_native_adaptive_deployment/application/exact-score-cache-integration-v1/physical-receipt.json)
at original pace preserves all 11,747 observations and 64 tracks, with identical
ARM final scores and zero drops. Cache-off/on whole-process times are
364.280/349.886 seconds; post-producer tails are 33.030/18.713 seconds. Cadence
misses fall from 30 to 23 out of 59, so both explicitly fail five-second freshness
(exit 4). The enabled run records 1,179 hits, 490 misses, zero fallbacks and
404,160 retained cache bytes. ARM component tests pass. This is one serial pair
of fixed-site saved-event replays, not capture-concurrent regional qualification;
the live default remains unchanged.

The [ARM publication stage profile](reports/2026_09_30_native_adaptive_deployment/application/publication-stage-profile-v1/physical-receipt.json)
isolates the remaining cost: full DS9 publication takes 15.333 seconds, with
14.761 seconds (96.3%) in track reconstruction and only 0.572 seconds in all
other publication stages. Its coalesced replay is lossless and reference-score
compatible; an earlier 100-times accelerated attempt dropped two events and is
retained as rejected evidence. This identifies tracking as the next performance
target without changing the continuous acceptance gate.

The isolated [rank-string-copy optimization](reports/2026_09_30_native_adaptive_deployment/tracking/one-per-source-rank-arm-v1/physical-arm/receipt.json)
passes host/sanitizer component checks, exact comparison of all 60 DS9 prefixes,
and physical ARM tests. A single-worker ARM ABBA comparison reduces mean full
reconstruction from 26.210 to 24.368 seconds (7.03%), with all four complete
outputs byte-identical. Only two rank tuples borrow stable candidate-ID strings;
the numerical operations, map and selection order remain unchanged. Production
promotion and the coherent application rebuild are complete. A new normal
reconstruction regression verifies equal numerical ranks select the lexical
candidate-ID winner; host, sanitizer and physical ARM checks pass. This result
does not qualify five-second publication or continuous detector/capture operation.

The subsequent [source-group key view experiment](reports/2026_09_30_native_adaptive_deployment/tracking/source-key-view-research/receipt.json)
eliminates repeated copies of immutable grouping keys. Its physical ARM ABBA
comparison reduces final warm reconstruction from a 17.592-second mean to
16.447 seconds (6.51%), with complete ARM output byte-identical to the control
and host output. All 60 host causal prefixes also match exactly, and focused
collision/lifetime tests pass under sanitizers. The reviewed implementation is
now in production source and the coherent application release has passed its
host science and physical lifecycle gates. These standalone timings do not
close the five-second freshness gate.

The isolated [dense source-group workspace experiment](reports/2026_09_30_native_adaptive_deployment/tracking/dense-source-workspace-research/receipt.json)
removes allocations inside repeated source grouping. All 60 host causal prefixes
and complete ARM tracking output match the source-key-view control exactly.
Physical ARM ABBA lowers mean final warm reconstruction from 16.458 to 15.093
seconds (8.29%), while mean cold reconstruction increases from 23.195 to 23.515
seconds (1.38%). A separate index-sidecar layout removes the larger point
structure. Its own physical ARM ABBA reduces mean warm reconstruction from
15.079 to 14.744 seconds (2.22%) and cold reconstruction from 23.470 to 21.566
seconds (8.11%) against the first dense layout. Full ARM output is byte-identical
to host and control. Full sanitizer reconstruction and actual lane-dispatch
TSAN tests pass. [Production promotion](reports/2026_09_30_native_adaptive_deployment/tracking/sidecar-production-v1/receipt.json)
is complete, including physical ARM grouping, lane-execution and full-output
checks. The coherent application rebuild and physical lifecycle tests pass,
and the release below now includes this optimization. These timings remain well above the
five-second freshness target.

The [current tracker stage profile](reports/2026_09_30_native_adaptive_deployment/tracking/current-stage-profile-v1/receipt.json)
preserves both tested ARM prefixes and attributes 9.850 seconds (69.34% of
14.205 seconds of lane work) to Hough histogram/peak processing. Candidate
segment work takes 4.152 seconds (29.23%). This identifies the next tracking
cost to investigate; it is not evidence that an additional cache will improve
runtime or fit the device memory budget.

Current application release: `bdec8f78923ee41d`, activated on 192.168.1.15
after host, ASan/UBSan, physical ARM unit and fake-device lifecycle tests.
Full portable host DS9 replay remains 11,747 observations, 64 tracks, zero
queue drops and the exact prior score. This release integrates the qualified
rank-string-copy, source-group key-view and dense sidecar optimizations into the application. It retains the
optional neutral support port and the portable CLI profile; the experimental
exact score cache is not enabled. Previous release `f51b826eeeebdb23` is retained.
Earlier release measurements below remain historical evidence, not fresh
timings for this build. No RF collection or autostart was enabled. See the
[current release qualification](reports/2026_09_30_native_adaptive_deployment/application/sidecar-workspace-release-v1/qualification.json)
and [physical activation evidence](reports/2026_09_30_native_adaptive_deployment/application/sidecar-workspace-release-v1/activation.log).

The new release's [physical paced saved-event run](reports/2026_09_30_native_adaptive_deployment/application/sidecar-workspace-release-v1/physical-paced.json)
preserves all 11,747 observations, 64 tracks and the reference score, with zero
drops, history evictions or search failures. At original recording pace with
two analysis workers and score cache disabled, it services 31 of 59 five-second
publication requests and misses 28. Maximum publication compute is 13.057
seconds and maximum result source age is 20.401 seconds. It correctly exits 4:
freshness remains unqualified. Whole-process time is 361.925 seconds, including
30.948 seconds of processing after the 299.805-second producer finishes.
This is saved-event analysis without IQ detection or capture. The serial
[cache-enabled run](reports/2026_09_30_native_adaptive_deployment/application/sidecar-workspace-release-v1/physical-paced-cache.json)
preserves the exact same ARM final science and zero drops, servicing 40/59
requests with 19 misses. Maximum publication computation is 13.089 seconds;
maximum result source age is 14.242 seconds. Whole-process time is 351.740
seconds, with a 20.725-second post-producer tail. It also exits 4 for failed
freshness. The cache records 1,377 hits, 525 misses and 404,160 retained payload
bytes. This single serial pair does not establish a statistical speedup or
capture-concurrent regional qualification. The deployed cache default remains off.

The optional server-compatible companion is separately installed at
`applications/8f8a1fa2b871c97b/leo-adaptive-live-server-compat`. Host and sanitizer
tests pass, and physical ARM fake-provider lifecycle tests pass in 0.115 seconds,
including portable CLI regressions, successful profile derivation, invalid and
unavailable derivation, cleanup, and zero-observation disqualification. Installed
capabilities identify the exact support profile. The package includes its
replaceable support DSO, corresponding source and license. The default
`live-current` remains the portable release above; no RF or autostart was enabled.
This deployment does not qualify strict detector parity or continuous real-time
location search. See the [companion deployment receipt](reports/2026_09_30_native_adaptive_deployment/application/profiled-companion-v1/deployment.json).

## Native objective and architecture

Pi target clarification: the user intends to try RTL-SDR; the dongle variant
and Pi access endpoint are not yet selected. Prioritize a single-receiver path
through the existing USB/source ports. Do not require coherent dual receivers
from RTL-SDR or manufacture a peer stream. The USB core and optional Soapy
provider admit one receiver, and additive single-receiver scanner and GLRT APIs
now pass saved-DS9 and ARM component tests. Live CLI selection, qualified USB
capture timing and physical dongle validation remain separate integration gates.
Keep PLUTO's qualified two-receiver behavior unchanged. Source timing must retain
its actual authority: correct system time does not create hardware sample
counters or identify the exact sampling instant of a buffered USB block.
Saved DS9 channel-isolation tests can qualify software behavior; physical
Pi/RTL-SDR throughput, tuning and timing remain separate hardware gates.
The [single-receiver USB regression](reports/2026_09_30_native_adaptive_deployment/usb/single-rx-ds9-v1/README.md)
now passes host, sanitizer and ARM CPU tests for both DS9 channel views. It
preserves selected sample bytes through uneven source blocks and window
assembly while retaining software-only ordinals and absent device timestamps.
This is source-boundary evidence, not RTL-SDR hardware or detector qualification.
The detector now provides an additive single-receiver API over the existing
ordinary proposal and regional-search engine, using true two-scalar I/Q stride
and preserving its eight-candidate budget. Its DS9 tests compare each
deinterleaved channel against the matching ordinary dual-receiver result, with
receiver-ID mapping and timing/work telemetry distinguished from scientific
fields. The existing dual API and its regression suite remain. The separate two-candidate
presence research engine is not a substitute for this compatibility gate.
The focused fold regression now passes on physical PLUTO+ for 8,000 scalar
and 8,000 NEON cases, comparing both extracted receiver views bitwise with
the dual path, including uneven lag tails and extreme CI16 samples. The
[ARM receipt](reports/2026_09_30_native_adaptive_deployment/usb/single-rx-detector-v1/physical-arm/fold.json)
qualifies that arithmetic boundary only. The subsequent
[ARM detector test](reports/2026_09_30_native_adaptive_deployment/usb/single-rx-detector-v1/physical-arm/api-ds9.json)
passes for both extracted channels of one saved DS9 dwell: dense and sparse
ordinary modes, additive fractional refinement, all candidate scientific
fields and row counters, and lifecycle/error handling. Host and sanitizer
tests pass, and the host dual-receiver 80-case regression is unchanged.
The [full-panel ARM comparison](reports/2026_09_30_native_adaptive_deployment/usb/single-rx-detector-v1/physical-arm/panel.json)
also passes all 80 distinct DS9 dwells in ordinary and fractional sparse modes
for both extracted receivers, retaining contexts across dwells and comparing
scientific fields and deterministic counters exactly. Host and sanitizer panel
tests pass as well. The single-receiver application path remains pending;
these comparisons do not close server-parity or real-time gates.
The USB-to-common-source adapter now passes host, sanitizer and
[physical ARM CPU tests](reports/2026_09_30_native_adaptive_deployment/usb/source-port-v1/physical-arm/unit.json),
including saved DS9 sample preservation, authority mapping, malformed retune
boundaries and release-failure ownership. It requires an explicit provider
guarantee that retuning removes stale delivered data. Current Soapy remains
unsupported at this adapter boundary until that guarantee is qualified.
The [pinned RTL-SDR retune audit](reports/2026_09_30_native_adaptive_deployment/usb/rtl-sdr-retune-audit-v1.md)
establishes callback shutdown and host FIFO cleanup, but finds ignored endpoint
reset errors and no qualified tuner-settling bound. Keep the capability disabled
until the selected dongle and Pi establish a measured sample-discard envelope
and reset failures propagate through the provider. No additional provider
factory is needed before those qualification inputs exist.
The additive single-receiver software-watermark scanner profile now passes
host, sanitizer, thread-sanitizer and physical ARM CPU checks. Its
[ARM contract test](reports/2026_09_30_native_adaptive_deployment/usb/single-rx-scanner-v1/physical-arm/unit.log)
exercises adaptive feedback, stride-2 windows, worker execution, malformed
detector results and source-authority boundaries. The
[ARM saved-DS9 test](reports/2026_09_30_native_adaptive_deployment/usb/single-rx-scanner-v1/physical-arm/ds9.log)
compares scanner output against direct single-receiver detection for both
extracted channels of one positive dwell. UTC/profile-CRC authority remains
absent; the existing live observation binding cannot accept that stream without
a separate, explicit timing and no-CRC contract. This is a CPU-only component
qualification, not physical USB capture or full application qualification.
The [single-receiver timing audit](reports/2026_09_30_native_adaptive_deployment/usb/single-rx-observation-timing-audit-v1.md)
identifies three downstream requirements: a qualified capture-to-enqueue latency
interval, within-window continuity authority independent of a software ordinal,
and preservation or explicit admission limits for observation timing uncertainty
through tracking. The existing online conversion drops the observation's
standard-uncertainty field, so inflating that field alone cannot qualify a
host-timed source. Keep exact-counter timing unchanged; test any additive
host-delivery timing policy against saved DS9 evidence before admission.
The [bounded DS9 timestamp experiment](reports/2026_09_30_native_adaptive_deployment/usb/host-timestamp-sensitivity-v1/README.md)
tests common offsets and deterministic source-group jitter at 1, 10 and 50 ms.
Common offsets preserve all 64 track memberships but reseed timestamp-derived
train/holdout partitions. Jitter preserves 49, 39 and 21 exact memberships,
respectively. The baseline and both 50-ms cases retain the same Sacramento and
Reno grid incumbents under the unchanged 400-point search budgets. These
results separate membership sensitivity from coarse location stability; they
do not establish a universal safe timestamp bound or qualify an RTL source.

One persistent C/C++ application runs on the device. PLUTO+ receives IQ from
local capture/DMA interfaces without Ethernet/USB IQ transfer. Pi uses a USB SDR
adapter. The portable numerical components receive explicit immutable records;
they do not depend on PostgreSQL, HTTP, Python, server storage paths, or reference
repositories at runtime. Correct system UTC and a recent local TLE are assumed;
sample-counter-to-UTC mapping and timing uncertainty still require explicit data.

Data flow: source -> timed windows -> complete fractional GLRT -> physical
observations -> tracks -> location search -> optional reference comparison.
Local TLE -> orbit cache feeds location search. A separate feedback classifier
feeds the adaptive scan controller. Preserve the existing feedback policy first;
switching energy classification to GLRT is a separately tested policy change.

The source interface exposes capability and evidence differences explicitly.
PLUTO's coherent current sample counter, exact gaps, dual-RX alignment and
attested post-retune boundary cannot be replaced by a USB driver's delivered
sample ordinal or frequency readback. The transport-neutral port owns neither
device lifetime nor restoration; the platform application owns those actions.
The source-neutral scanner entry now consumes that port, checks required
capabilities before policy selection, and wraps unchanged scanner-v2 events in
an explicit authority envelope. The legacy local entry points use the same
engine through the local adapter and retain their public ABI. Host, ASan/UBSan,
and physical ARM CPU tests cover exact dual-RX parity, weak software ordinals,
overflow/discontinuity suppression, cancellation, and failed-release cleanup.
This scanner profile still requires coherent simultaneous dual RX at 2.5 MS/s;
the selected USB provider and physical hardware qualification remain open. The
deployed live application now includes this scanner build; its USB/radio capture
path has not been newly qualified by these fake-provider CPU tests. See the
[integration receipt](reports/2026_09_30_native_adaptive_deployment/ds9/c10-scanner-source-integration.json)
and [port audit](reports/2026_09_30_native_adaptive_deployment/ds9/c10-common-source-port-audit.md).

The runtime owns a bounded worker pool. Each numerical context owns mutable FFT
plans, caches and scratch. Shared orbit/track snapshots are immutable. One owner
controls the scan policy, track state and search frontier. Parallel jobs may
cover complete detector dwells or disjoint satellite ranges; deterministic
combination preserves tie-breaking and search order. No nested thread pools.
The deployed worker-enabled application owns independent detector contexts and
tracking execution contexts. FFTW planning/destruction remains guarded; analysis
can execute concurrently across detector contexts. The CLI validates the total
configured compute budget before radio access. PLUTO+ defaults to one detector
plus one analysis lane; Pi layouts can explicitly request two plus two. These
are concurrency caps, not CPU affinity or hardware qualification.

Release `b7b2d5c6e3f95ecd` is installed on 192.168.1.15 with the previous release
retained. Physical lifecycle/CLI tests pass. Saved-candidate host replay with
1/2/4 analysis workers and physical ARM replay with 1/2 preserve 11,747 accepted
observations, 64 tracks, and zero drops. Physical scores agree exactly between
worker counts. At five-times playback speed, publication takes 27.978 seconds
with one analysis worker and 16.003 seconds with two (one measured pair, 1.75x).
Post-producer tails are 53.002/41.019 seconds and peak RSS 167,604/181,560 KiB.
The two-worker replay has no detector lane: it does not establish a concurrent
two-core live budget. The five-second freshness gate remains unmet. See the
[deployment receipt](reports/2026_09_30_native_adaptive_deployment/application/execution-workers-v1/deployment.json).
No new RF or autostart was enabled.

The preceding release, `3f3c1badd6e740ec`, also shares the
analysis pool with deterministic satellite scoring. Full host 1/2/4-worker and
physical 1/2-worker saved-event replays preserve the same 11,747 observations,
64 tracks and scores with zero drops. The physical one/two-worker pair measures
27.995/16.088 seconds publication and 52.898/34.382 seconds post-producer tail;
whole-process times are 144.349/125.691 seconds and peak RSS 167,600/182,368 KiB.
The previous tracking-only two-worker tail was 41.019 seconds. This is measured
improvement, not five-second freshness qualification. Host/sanitizer and physical
application tests pass; defaults remain one detector plus one analysis lane.
See the [shared-scoring deployment receipt](reports/2026_09_30_native_adaptive_deployment/application/scoring-workers-v1/deployment.json).

The earlier tracking-only post-publication tail was 25.024/25.016 seconds in
those two runs because online scoring remained serial. The additive scorer port
above closes that integration gap. The next bounded work is a current
exact-prefix tracking cache benchmark on the final two causal DS9 prefixes.
Neither optimization establishes the five-second gate by itself. Keep cold tracking
as the oracle and report retained cache memory before integrating stateful
tracking. Do not hide missed deadlines by lengthening the requested cadence.

The current exact-prefix cache benchmark is complete on physical ARM. For the
last two causal DS9 prefixes, one-worker cold/warm reconstruction is
27.603/21.700 seconds; two-worker is 15.484/12.519 seconds. Both prefixes and both
worker counts match fresh reconstruction exactly. The cache retains 88,221,442
bytes, with all eight lanes extended and none wholly reused; whole-process peak
RSS is 111,888/125,064 KiB. This isolated benchmark excludes location scoring
and detector contention. Keep the cache out of the live default: its measured
benefit does not close the five-second gate. Next investigate exact histogram
reuse within changing lanes. See the
[physical tail-prefix receipt](reports/2026_09_30_native_adaptive_deployment/application/tracking-tail-prefix-v1/physical-arm/receipt.json).

The isolated scoring-reuse experiment passed host, sanitizer and physical ARM
checks for ordinal prefixes 58 to 59 (11,389 to 11,566 candidates). At one exact
site, 55 of 64 track scores reused with all winners, score and statistics exact.
ARM scoring fell from 15.0202 to 1.5197 seconds; logical cache payload was
351,557 bytes. This single sample excludes reconstruction, orbit build and
cache seeding. Reuse requires unchanged orbit/configuration and complete track
authority, arrays and weight. Nearby sites remain cold. Measure repeated-site
hit rates across actual searches before production integration; this does not
establish continuous real-time operation. See the
[physical scoring-reuse receipt](reports/2026_09_30_native_adaptive_deployment/location/exact-track-score-reuse-research/physical-arm/receipt.json).

The subsequent full search inventory evaluates 400 real points on each of
ordinal prefixes 58, 59 and 60 under the Sacramento C7 policy, with all 11,129
satellites and a fixed orbit generation. Adjacent searches repeat 384 and 385
exact ECEF/up sites. With 55 and 52 unchanged tracks, respectively, this makes
21,120/25,600 (82.5%) and 20,020/25,600 (78.2%) track-score calls eligible for
reuse. The estimated central-authority plus score-entry payload is 1,779,304
bytes, excluding allocator and container overhead. These are eligibility
counts, not cached execution timings; all searches exhaust their 400-point
budget with deferred cells. Implement a bounded opt-in cache and require exact
cold/cached complete-search comparisons before enabling it. See the
[host search inventory](reports/2026_09_30_native_adaptive_deployment/location/exact-site-recurrence-research/host-result.json).

The bounded deeper Hough experiment is complete and rejected. Dense cached
first-peel histograms would add 117,997,568 bytes across eight lanes, and sparse
storage is larger at the measured 75% occupancy. The low-memory top-64 and
exact-mask prototype preserves all 60 causal-prefix results and uses its exact
incremental path for 49 of the final 64 peels, with four guarded mask
divergences. It is nevertheless 22.1% slower on the same host: 19.0246 seconds
stateful total versus 15.5752 seconds for production. Scanning old bin indexes
and maintaining the touched frontier costs more than the work it avoids. Stop
this line without sanitizer or ARM campaigns; production remains unchanged and
the five-second gate remains open. See the
[failed Hough-prefix research receipt](reports/2026_09_30_native_adaptive_deployment/tracking/hough-prefix-research/qualification.json).

The subsequent [inverse-index dirty-cell experiment](reports/2026_09_30_native_adaptive_deployment/tracking/hough-peel-csr-research-v1/README.md)
also preserves all 60 causal prefixes and the full 64-track output, but is
rejected: stateful host time rises from 10.455 to 28.369 seconds. Focused and
sanitizer tests pass; no ARM or production promotion follows. A bounded profile
attributes only about 15% of the candidate warm call to inverse-index creation,
so retaining that index alone would not remove the regression. A separate
dense histogram/dirty-map experiment uses existing forward bins without the
inverse index and is [also rejected](reports/2026_09_30_native_adaptive_deployment/tracking/hough-peel-dense-dirty-research-v1/README.md):
all 60 prefixes remain exact, but stateful host time rises from 10.814 to
23.305 seconds. Direct per-peel accumulation remains the qualified winner;
neither reuse design is deployed or built for ARM.

## Frozen DS9 evidence and gaps

- Detector panel: 80 dual-RX 120-ms dwells, 20 scans, 2.5 MS/s; 160 receiver
  windows, 298 native candidates, 286 positive candidates and 90 positive
  receiver-windows. These are native-control regression counts, not proof of
  equivalence with the deployed fractional detector.
- Location fixture: scan-fw-3cfdaa6d75762cad, 64 tracks, 3,372 observations,
  11,129 eligible satellites, historical TLE snapshot pinned in
  reports/2026_09_30_arm_location_prototype/inputs.json.
- The location scan is absent from the 80-dwell panel. Export matching raw IQ,
  metadata and reference products before claiming an IQ-to-location E2E pass.
- Reference outputs, known coordinates and saved winning identities remain
  outside inference. Oracle-seeded shortlist timing is not discovery evidence.
- DS9 is a development/regression set. Reserve untouched whole sessions for
  broader validation; do not train PGO or tune thresholds on a claimed holdout.
- Read source corpus through read-only ports. Never mutate QNAP or rewrite
  scientific goldens to make tests pass. Missing data fails the relevant lane.

The receiver-authority diagnostic narrows the E3 scientific mismatch. Retained
native observations number 3,071/8,900 for RX0/RX1, versus 6,466/5,281 in the
server projection; the net excess of 224 conceals substantial substitutions.
With unchanged tracking and 400-point searches, replacing only RX0 observation
authority restores the reference Reno incumbent; replacing RX1 does not.
The [RX0 diagnostic output](reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/rx0-reference/reno.json)
still has a different score. This oracle-substitution experiment is diagnostic
only. Next replay a fixed, declared sample of reference-used RX0 visits missing
from native observations through ordinary and server-compatible detectors to
identify the acquisition/retention difference before changing production.
The fixed eight-visit replay reached an explicit domain limit: the original
7.5 MS/s analysis uses residual bounds of -800,000 to +800,000 Hz, while the
current server-compatible wrapper rejects that span before analysis. Its
coarse workspace holds only 12 frequencies; the required regular grid has 21.
Preserve the rejected runs and extend the research path with capacity-checked
grid construction and matching workspace sizing before repeating this exact
sample. Do not narrow the original search geometry to obtain a passing replay.
An isolated 22-slot research build now executes the authoritative 21-bin grid
and passes host/sanitizer grid tests plus unchanged legacy-geometry regression.
Separately, the [production research-setter safety fix](reports/2026_09_30_native_adaptive_deployment/detector/reference-geometry-safety-v1/receipt.json)
rejects spans above 880 kHz before storing geometry, preventing the previously
accepted range from overflowing the twelve-slot grid. Boundary and unchanged-
configuration tests pass on host, under sanitizers and on physical PLUTO+ CPU.
This fix does not promote the wider research detector or change ordinary GLRT.
On the fixed eight visits it restores a matched passing RX0 detection in all
eight source groups: 21 of 23 reference passing candidates match under the
existing epoch/CFO tolerances, with two missing and two additional candidates.
Six of the eight particular reference track-used candidates are recovered.
This selected diagnostic sample is not a full-scan recovery rate. Scalar and
interval modes agree exactly on all four discrepant visits; an actual wideband
visit also passes ASAN/UBSAN. The ordinary production detector remains unchanged
while the remaining acquisition/refinement differences are investigated.
The [completed retention diagnosis](reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/wideband-research/retention-audit-v1/qualification.json)
found that the eight-visit experiment used the
wrong receiver-frequency center: zero instead of the persisted analysis's
-312.5 kHz. Treat its 21/23 count as a diagnostic with incorrect frequency
geometry, not parity under the reference configuration. With the corrected
center, the current server reproduces the compared detector fields on all 43
persisted rows: integer epoch, gate decision and five fractional fields, matched
by rank. Candidate IDs, support timestamps and moments were not compared here.
The native wrapper matches all 64 retained candidates in rank,
epoch, status and nullability, with maximum CFO difference below 3e-9 Hz and
score/margin difference below 1.9e-13. The passing count is now 23/23 under
unchanged gates, with all 43 individual decisions matching (23 pass, 20 fail).
Geometry comes from persisted projection RF/channel/edge metadata and the
maintained pilot-frequency contract. The retained capture manifest binds raw
hashes and counters; the original input manifest is only hash-referenced here.
This closes the fixed-eight discrepancy,
not full-corpus parity or real-time qualification; retain the original run and
its setup-error explanation.

The [corrected replay harness](reports/2026_09_30_native_adaptive_deployment/ds9/corrected-full-replay-v1/qualification.json)
passes a frozen 32-visit slice spanning all four channels and four receiver
outcome classes. Both receivers contribute 512 retained candidates; native and
current-server results agree within the original tolerances, including all
318 complete-candidate gate decisions (88 pass). The other 194 candidates have
unavailable fractional results. DS9 contains lower-edge captures only.
Independent review verifies finite-value rejection, per-rank gates, source
rehashing on resume, explicit failure accounting and process-tree timeout
cleanup. The [full saved-data replay](reports/2026_09_30_native_adaptive_deployment/ds9/corrected-full-replay-v1/full-output/summary.json)
now passes: 2,215 visits, 4,430 receiver windows, 35,440 retained native
candidates, and all 24,681 available gate decisions equal by rank. Native and
persisted results both contain exactly 11,747 passing detections. Maximum CFO
difference is 3.027e-9 Hz and maximum fractional offset difference is 7.105e-12
samples, within the frozen tolerances. Every per-visit receipt has pass status
and the same task digest. The four-worker host replay exits zero after
1,419.47 seconds with no failure receipts. This closes the full DS9 detector
comparison for the isolated corrected research wrapper on the host, not the
ordinary production detector or full-corpus ARM parity.
The [fresh-native downstream comparison](reports/2026_09_30_native_adaptive_deployment/ds9/corrected-full-replay-v1/README.md)
now reconstructs all 64 reference physical track memberships, lanes and support
bounds, including all 3,372 alias indices. Maximum intercept difference is
1.874e-8 Hz. This does not close location equivalence: native analysis identities
and support serialization produce different partition seeds/masks. At the two
registered sites, satellite winners agree on 60/64 tracks each; the bounded
400-point Reno search selects a different incumbent. Both regional searches
report `complete=false`. The separate server-support numerical profile greatly
improves moment spelling agreement but still has distinct native provenance and
partitions. No reference IDs, moments or masks are injected into these products.
The [fresh-native physical ARM tracking replay](reports/2026_09_30_native_adaptive_deployment/tracking/corrected-native-arm-v1/README.md)
now produces byte-identical host/ARM output for all 64 tracks from those 11,747
observations. The cold serial CLI takes 22.023 seconds and 22,980 KiB peak RSS.
Detection/projection remain host-computed inputs in this test; it does not close
full ARM detection-to-location or continuous capture qualification.
The [fresh-native fixed-site ARM score comparison](reports/2026_09_30_native_adaptive_deployment/location/corrected-native-arm-v1/README.md)
also produces byte-identical host/ARM JSON for both registered sites, including
all 64 satellite/time-offset selections per site. Two workers take 16.698
seconds whole-process wall time and 24,300 KiB peak RSS. This fixture supplies
host-computed tracks and saved orbit states; regional search, fresh propagation
and native/server partition equivalence remain outside this test.
The [frozen public standard-scorer isolator](reports/2026_09_30_native_adaptive_deployment/ds9/corrected-full-replay-v1/standard-scorer-validation.json)
now independently evaluates reference and fresh-native artifacts using each
artifact's own inputs. Both sites in both artifacts have exact satellite/time
offset selections and zero per-track score difference from native C++; maximum
aggregate rounding difference is 5.68e-14 Hz. This validates the scoring rule
on identical artifact inputs, not cached-artifact identity, fresh orbit
propagation, regional search or runtime use of the reference repository.

Corrected-profile integration is in progress through a new additive scanner
interface, immutable queued visit geometry, and a separately linked detector
adapter. The [source-derived geometry component](reports/2026_09_30_native_adaptive_deployment/application/corrected-geometry-v1/README.md)
passes host/sanitizer and physical ARM unit tests with identical authority
digests. It derives receiver centers and shared observable residual bounds from
profile/source authority and rejects invalid inputs without committing output.
This is synthetic component evidence; raw DS9 composition remains to be tested.
The [additive scanner profile boundary](reports/2026_09_30_native_adaptive_deployment/scanner/corrected-profile-v1/README.md)
now passes focused host, sanitizer and physical ARM tests, including queued
geometry ownership, manifest mismatch, malformed callback output, source
transition mismatch and honest false-parity propagation. Existing scanner and
single-source regressions also pass on host and sanitizer; those test binaries
ran under sudo because glibc `tmpfile()` encounters the unprivileged `/tmp`
quota. Published scanner and detector headers remain byte-identical to the
deployed release. The [corrected detector adapter](reports/2026_09_30_native_adaptive_deployment/detector/corrected-profile-adapter-v1/README.md)
now passes host, sanitizer, concurrency and physical ARM tests using original
DS9 visit 301. It links the frozen corrected detector separately from the
ordinary detector and validates the public result conversion. The
[recorded source/export component](reports/2026_09_30_native_adaptive_deployment/application/recorded-ds9-composition-v1/README.md)
preserves original visit IDs, counters, calibration and raw-data digests for
visit 301 and the frozen 32-visit panel. The additive recorded-plan runner has
physical ARM component evidence for lossless serialized replay; final authority
preflight changes also pass in the `c635bb61` physical test. The recorded source
provider and strict bundle reader now pass physical ARM component tests, and
the provider traverses the original visit-301 raw data with its hash verified. Complete
raw-IQ-to-Analysis composition remains in progress. Offline serialization does
not establish continuous scanning throughput.

A [corrected wideband physical ARM measurement](reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-arm-v1/README.md)
matches the host wrapper on both receivers of DS9 visit 301: all 16 retained
candidates satisfy the frozen comparator, with 12 matching complete-candidate
gate decisions and seven passes. The 120 ms dwell takes 55.300 seconds inside
the detector call (460.83 times the dwell budget), including 55.264 seconds in
search and 35.1 ms in preparation. This is an isolated research detector,
not the deployed ordinary detector. It demonstrates one-dwell numerical parity
and a severe performance gap, not real-time or full-corpus ARM qualification.
The [existing detector stage timers](reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-stage-profile-v1/README.md)
attribute 46.016 CPU seconds to coarse interval search, 8.659 to integer
acquisition/refinement and 0.492 to fractional refinement. Conditioned CFO
scoring is 6.867 seconds inside the acquisition interval; these nested timings
must not be added twice. The isolated [exact-rounding optimization](reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-nextup-research-v1/README.md)
passes physical ARM comparison with every non-timing row field and numeric
lexeme unchanged. Two control and two candidate measurements give mean call
times of 55.291 and 50.287 seconds, a 9.05% reduction for this single dwell.
The candidate still costs about 419 dwell durations; it is research-only and
has not changed the deployed detector. An additional private interval-bound
memory-layout experiment is undergoing physical qualification.

## Component ownership and independent tests

| ID | Component and contract | Unit tests | DS9 integration gate |
|---|---|---|---|
| C0 | Test kit, input manifests, native fixture encoders and reference comparators | Corrupt/missing inputs, hashes, units, provenance, reference separation | Frozen complete-scan fixture and stage outputs |
| C1 | Blocks/visit metadata -> timed valid windows | Chunk boundaries, layout, gaps, retunes, partial windows, counter extension | Identical windows under varied block delivery |
| C2 | IQ -> acquisition and full fractional GLRT candidates | FFT context isolation, fractional refinement, gates, multiple candidates, peer-RX fallback, incomplete status | Native-control regression plus separate fractional-server comparison |
| C3 | Candidates/metadata -> physical UTC/RF/CFO observations | Support center, RF calibration, CFO sign, invalid support | Compare projected observations against server |
| C4 | Observations -> qualified track snapshots | Aliases, grouping, support, gaps, duplicates, expiration, stable ordering | Rebuild track membership/support/partitions from reference observations |
| C5 | Local TLE/time interval -> shared orbit snapshot | Parsing, failures, interpolation, cache extension, generation change | Catalogue, ECEF state and Doppler agreement |
| C6 | Tracks/orbits/location -> all-track score | Offset, masks, tau selection, visibility, weights, penalties, ties | All selected satellite/tau/offset/residual fields at both reference points |
| C7 | Tracks/orbits/priors -> search result | Frontier ordering, budgets, resume, cancellation, stale state, reference isolation | Both original 400-point regional searches |
| C8 | Visits/feedback -> target/dwell decision | ACTIVE/QUIET/UNKNOWN, stale/duplicate feedback, application boundary, revisit deadlines, rollover | Recorded decision replay and controlled policy simulation |
| C9 | Jobs -> bounded deterministic execution | Queues, lifetime, cancellation, failure, priorities, 1/2/4 workers | Sequential/multicore parity and paced arrival timing |
| C10 | Local PLUTO, USB SDR and replay adapters | Fake driver, configuration, timestamps, overflow, disconnect, exclusive ownership | Common source contract; live capture qualified separately |

Every component has explicit input/output contracts, a component-owned unit
suite, a frozen boundary fixture, and time/memory/work-count measurements.
Reference observations/tracks can isolate downstream components, but E2E must
reconstruct them from IQ. The numerical oracle remains external to production.

## End-to-end gates

1. E1: recorded IQ -> windows -> full GLRT -> physical observations.
2. E2: reference observations -> native tracks/orbits/search -> reference metrics.
3. E3: one complete recorded scan -> every numerical stage -> final result;
   no saved intermediate answers in inference inputs.
4. E4: independently paced replay + policy simulation -> feedback accounting,
   runtime scheduling and scientific outputs. The producer never waits for the
   consumer to hide backlog. Simulated alternative visits are not new RF truth.

Compare missing AND additional candidates, score/CFO/timing errors, track
membership, satellite/tau choices, point inventories and final coordinates.
Predeclare numerical tolerances; threshold/winner changes stay visible.
Online results use only observations available at their publication time.
Compare against a reference with the same prefix/window, not future full-scan
data. Keep deterministic reference search and budgeted streaming search as
explicit modes. Streaming tests cover cold discovery, wrong hypotheses,
reacquisition, expiration and TLE replacement without oracle identities.

## Performance and continuous operation

The complete 299.802-second saved-candidate DS9 replay has now run at real
recorded pace on PLUTO+ using 600-second history and five-second publication
requests. It retained all 11,747 observations without queue drops or capacity
evictions, recovered 64 matched tracks, and agreed with the independent native
one-point full-catalogue reference within 3.7e-13 Hz RMSE. This exercises saved
candidates, not the detector or raw IQ, and does not exercise 600 seconds of
evidence or complete a regional location search.

The same run failed the five-second freshness target: 59 requests produced 17
serviced requests and 42 misses (plus one initial publication without tracks).
All 17 started one-point searches completed. Maximum track publication time was
39.356 seconds; maximum publication-to-result time was 56.724 seconds. Analysis
needed 91.357 seconds after the producer finished. The independent producer
completed in 299.806 seconds, so backlog was not hidden by slowing delivery.
Whole-process time including fixture preparation was 423.696 seconds, CPU time
428.163 seconds, and peak RSS 170,060 KiB. The executable returned qualification
failure, as expected from these measurements. Preserve this failed timing gate;
successful final science does not qualify continuous operation. Evidence:
`reports/2026_09_30_native_adaptive_deployment/application/full-span-paced-analysis.json`.

The deployed exact-fit-cache composition also passes a full physical ARM
saved-candidate replay with one coalesced publication at 5x recorded input
speed: all 11,747 observations retained, 64 tracks matched, no queue drops, and
3.7e-13 Hz RMSE difference from the native reference. Whole-process time is
148.31 seconds including 31.22 seconds of fixture preparation; final analysis
drain is 57.12 seconds. The initial 100x stress run dropped 71 observations and
was correctly rejected even though it still matched 64 tracks. Both results
are preserved in `reports/2026_09_30_native_adaptive_deployment/application/exact-fit-cache-replay-arm/receipt.json`.
This is saved-candidate correctness evidence, not continuous cadence, regional
discovery, raw-IQ parity, or a replacement for the failed real-pace timing gate.

Repeated tracking publication motivated the completed standalone cache
experiment described below. Its bounded persistent slope-bin-index cache is
valid only when each lane's prior ordered
candidates are an exact prefix with unchanged reference, RF and configuration.
Insertion, reordering, expiry/reference shifts and budget exhaustion must fall
back to the existing cold reconstruction. Compare complete track outputs at
every DS9 five-second prefix, including forced invalidation cases, before an
ARM timing comparison. Budget memory across all lanes, not independently per
lane. Preserve floating-point accumulation order; do not introduce histogram
subtraction merely to obtain faster timings. The standalone experimental
reconstructor now passes exact comparison at all 60 causal DS9 prefixes, with
88,570,966 bytes of retained cache accounting on the host. A bounded physical
ARM comparison also preserves both final prefixes exactly: final reconstruction
falls from 39.333 to 24.045 seconds, but seeding costs 62.850 seconds. It is not
enabled in the live application. Growing-prefix reuse does not solve rolling
history expiry, and the measured warm call still fails the five-second target.
See `reports/2026_09_30_native_adaptive_deployment/tracking/prefix-cache-causal-qualification.json`.

The live composition now pins a started search's immutable snapshot while
newer publications arrive. Native refinement batches also progress with a
one-point execution allowance. Tests cover exact bulk/sliced DS9 results with
all 11,129 satellites, publication interleaving, expiry, stream/orbit changes,
cancellation and caller-driven execution. The default coordinator policy still
preserves invalidation for existing callers. This closes the lifecycle gap,
not the continuous timing gate: completing a final search cannot qualify
continuous result delivery.

First profile: dual RX, 2.5 MS/s, first 20 ms at an explicit 120 ms stride;
120/240/360 ms visits produce 1/2/3 probe positions per receiver. Higher rates
are separate qualification profiles: existing ARM results do not meet the
120 ms detector budget at 5/7.5/10 MS/s. Existing 80-dwell evidence covers only
120 ms visits. Synthetic longer visits prove structure, not real-data recovery.

Targets: no unexplained loss/overrun; sustain all scheduled probes without
growing backlog; aim for <=100 ms detector processing per dual-RX probe position
and measure queueing relative to the 120 ms arrival interval. Feedback must meet
the configured application deadline. Memory is bounded after warm-up. Location
has separate acquisition/reacquisition/freshness requirements; a provisional
5-second warm update is a target, not an achieved result. Full-catalogue scoring
of the saved two-point fixture originally cost 35.37 seconds with one worker or
19.22 seconds with two on the flashed ARM device. The bounded production stencil
build measures 31.94 and 16.65 seconds respectively in its latest physical runs;
these isolated measurements exclude capture contention.

Detector concurrency rollout is separate from scanner worker-count selection.
Independent detector contexts with private proposal/search state and FFT plans
now pass exact serial comparison on two distinct positive DS9 dwells on PLUTO+;
the same-context BUSY and mixed-rate isolation checks also pass. Host ordinary
and fractional 80-panel non-timing outputs remain exact. The fully instrumented
detector closure passes ThreadSanitizer (external FFTW/libc are uninstrumented).
Physical memory grows by 8,088 KiB for a second warmed context in either mode.
Evidence: `reports/2026_09_30_native_adaptive_deployment/ds9/context-concurrency/physical-arm/receipt.json`.
The installed application retains the prior detector until scanner integration.
Serialize FFT planning and
destruction; reject overlapping use of one context. Build variants that create
plans during analysis must retain serialization. Per-call CPU telemetry must
exclude unrelated worker CPU; whole-process benchmark CPU remains separately
reported. The research detector retains its own serialization until its mutable
experimental state is removed.

Only after that gate should a versioned scanner execution option admit multiple
detector lanes. Give each executor worker its own preconstructed context and
budget dwell slots as queued plus active jobs. Preserve the current single-lane
entry point. Test reversed completion order, slow/failed jobs, bounded queues,
serialized sink callbacks and source cancellation; compare final DS9 science
after draining, and qualify intermediate publications as consumed prefixes.

The additive scanner execution API now passes physical component tests,
including four-context routing, validation before source operations, bounded
queues and failure/drain behavior. Two recorded positive DS9 dwells produce
exact serial/two-context event sets after timing-field removal. Final physical
unit tests take 6.619 seconds and the real-IQ comparison 0.753 seconds. These
are component tests, not a capture throughput benchmark. The live application
has not yet adopted the new scanner/detector composition. Evidence:
`reports/2026_09_30_native_adaptive_deployment/scanner/context-execution-v1/physical-arm/receipt.json`.
The existing application accepts reordered observations within its declared
history and latency bounds. A synthetic session regression now verifies reverse
completion and two concurrent producers against serial final tracks, support
digests, partition seeds and masks on host, sanitizer and physical ARM (0.420 s).
This alone is not a multi-lane scanner test; evidence is in
`reports/2026_09_30_native_adaptive_deployment/application/session-completion-order.json`.
Measure one versus two lanes with concurrent analysis on PLUTO+ before choosing
a default; reserve capture capacity and avoid nested detector/scorer pools.

Benchmark component kernels, complete replay at maximum speed, independently
paced replay, accelerated overload replay, and capture-concurrent execution.
Record RF/counter time, buffer/window readiness, queue/start/end timestamps,
feedback submission/application/first affected visit, track snapshot and result
publication. Report CPU/wall p50/p95/p99/max, misses, queue depth/oldest age,
RSS/kernel-DMA memory, temperature and frequency. Distinguish RF-to-result from
post-input processing time; whole-visit delivery may release multiple jobs in
a burst. Compare ordinary and PGO builds with frozen training and shuffled order.

Finite duration and visit limits must not silently stop continuous operation.
Test bounded history or explicit generation rollover across the existing
five-minute/visit caps, including counter rollover and late feedback. A reset
cannot manufacture continuity. Repeated recordings preserve session boundaries
and are timing repetitions, not independent scientific samples.

## Device deployment and live qualification

Use PPU to install the exact qualified 0.59 image on 192.168.1.15 as explicitly
requested. Inspect current identity, firmware, PPU command semantics, release
hashes, active capture ownership and recovery evidence before executing the
supported update route. Do not use raw flashing as a substitute for PPU or
bypass tool-enforced safety. If the named force operation applies only to a
different physical route, report that distinction and use an authorized PPU
route where possible. Verify returned device identity/version and image receipt.

Keep the existing FPGA/kernel unless capability or continuous-capture evidence
demonstrates a missing requirement. Reuse the local scan ioctl interfaces via
a supported native adapter. Deploy versioned application bytes separately;
validate saved-IQ replay before enabling capture. No firmware success claim is
a numerical or real-time acceptance claim.

Live RF execution stays within a declared aggregate 30-minute maximum and does
not displace recording work. The user explicitly authorized the bounded
26-minute campaign. Its persisted budget reserves each run plus an external
shutdown allowance; failed attempts remain charged. The original proposed
allocation (baseline, all dwell ceilings, uninterrupted operation and controlled
recovery) is adjusted in response to measured defects without increasing that
cap. IQ remains local. The implemented live boundary is candidate capture and
GLRT; concurrent scoring of saved tracks tests CPU contention, not a completed
online IQ-to-location handoff. Quiet feedback does not qualify ACTIVE dwell
expansion merely because a higher ceiling was configured. Existing-data tests
come first. Hardware/QNAP/PostgreSQL lanes have explicit requirements rather
than silent skips.

## Delivery checklist

- [x] C0 complete-scan provenance and stage fixtures (2,215 visits/4,430 receiver windows verified; native candidates, observations, tracks and score handoffs exported).
- [ ] C1-C3 fractional observation parity and component tests.
- [x] C4 native track reconstruction (64/3,372 source memberships; six duplicate-ID ties remain documented).
- [x] C5-C6 orbit/scorer componentization and DS9 regression (prototype semantics; server tolerances documented).
- [x] C7 host reference search: native scorer and scheduler reproduce both original ordered 400-point traces and exact incumbents within the declared score tolerance; budget exhaustion remains explicit.
- [ ] C7 continuous streaming search qualification on ARM, including capture contention and result-age deadlines.
- [x] C8-C9 policy, bounded execution and concurrency tests (saved/live contention measured; strict detector deadlines remain unmet).
- [x] Exact 0.59 PPU flash and post-return attestation.
- [x] C10 local PLUTO adapter and candidate-stage scanner installed; fake-source, saved-IQ and physical local capture exercised (continuous qualification recorded separately; online location remains open).
- [ ] E1-E4 evidence with explicit coverage gaps.
- [ ] Capture-concurrent qualification before declaring real-time operation.
- [ ] Pi platform qualification (portable USB core, real-compiled optional Soapy backend, fake-provider DS9 parity and PLUTO CPU portability now pass; selected USB hardware remains unqualified).

Keep statuses evidence-based. Finish each implementation slice with tests and
receipts, preserving unrelated work and the server plan below.

Implementation evidence is being collected in
`reports/2026_09_30_native_adaptive_deployment/`. PPU installed and attested
`v0.59-plutoplus-spf-dual-rx-counter-fix` on the requested device. Portable
components and diagnostic binaries are deployed in versioned SD directories.
The full application is not yet qualified: the ordinary 80-dwell regression
passes, while fractional-server recall and fractional processing deadlines
remain explicit acceptance gaps. Projection reproduces 11,747 saved DS9
observations on ARM with exact identities and UTC support timestamps. These
component results do not close the scientific-parity or live-capture gates.
The authorized live campaign is now closed within its 26-minute aggregate cap
(1,526 seconds conservatively charged). The 585-second local candidate scan
completed with no missing samples or revisit breach but four detector queue
drops. The final deployed four-entry queue build passed a 60-second restart
check with 350/350 complete visits analyzed and clean restoration. Long-duration
losslessness on that final build, live ACTIVE long-dwell behavior and the
online observation/track/location coordinator remain open; no automatic RF
service was enabled. Detailed failures, fixes, bounds and receipts are retained
in the deployment report's authorized-live-qualification section.
A complete read-only host replay of all 2,215 location-scan visits now reaches
23,477 native candidates, 11,971 physical observations, 64 tracks and both
registered catalogue point scores. Its fresh graph authority uses no saved
candidate scores or memberships; regional search and scientific parity remain
separate acceptance gates. Both 400-point native regional searches have now
executed on those fresh tracks: the Sacramento incumbent matches the reference
coordinates, while Reno differs by 460.977 km. Both exhaust their point budget
and remain unconverged. The new two-point native-track scores also reproduce
exactly on ARM (17.79 seconds, two workers). E3 execution evidence exists;
scientific equivalence and continuous integrated qualification remain open.

Separately, the frozen reference inputs now pass an integrated native
scorer-plus-scheduler regression for both original 400-point regional searches.
All point coordinates and their order match exactly; maximum score differences
are 2.10e-11 Hz for Sacramento and 3.02e-11 Hz for Reno, below the predeclared
1e-9 Hz tolerance. Both exact incumbents match. These searches truthfully stop
at their original budget with 95 and 175 deferred cells; this proves reference
execution parity, not global convergence or parity of the fresh detector inputs.
Evidence: `reports/2026_09_30_native_adaptive_deployment/location/c7-reference-search-v2/receipt.json`.

Counter/UTC timing and scanner-to-observation ingress now have component-owned
host, sanitizer and ARM tests. The ingress replay preserves all 11,747 retained
observations from 24,681 frozen DS9 candidate records exactly against the native
projector. Timing rejects software delivery ordinals, clock discontinuities,
counter resets and expired calibration; ingress verifies profile/RF authority
and excludes detector queue latency from UTC. These components do not yet close
the persistent application integration or fractional-server parity gates.

The persistent observation coordinator now passes host, sanitizer and ARM
component tests: bounded causal history, immutable publication, search resume,
cancellation, expiry and stream/TLE invalidation. A 10-second fresh-native DS9
prefix yields 492 observations and 11 tracks; all 11 contribute to a bounded
64-satellite score checked independently through the public scorer. The
application composition adds a bounded observation inbox and separates capture
from the analysis owner. The opt-in local live executable is now implemented
and installed at `/mnt/glrtbench/native-adaptive/live-current/leo-adaptive-live`
on 192.168.1.15. Host, sanitizer and physical CPU-only lifecycle tests pass.
The current application is `applications/d75596931e4598d5` (binary SHA-256
`d75596931e4598d51fd9a7029856e74e3e7c299abff0dbc0d57dd0aff405bfa3`).
It explicitly supports 10-second/32-by-1-second-knot and
600-second/96-by-10-second-knot development profiles. Telemetry records fixed
source-time publication requests, serviced/missed/pending counts, measured
source-age bounds and monotonic publication-to-result duration. Physical
CPU-only lifecycle/CLI tests passed in 0.6675/0.0212 seconds. It pins active
search snapshots, coalesces newer pending snapshots, and supports explicit
caller-driven analysis for deterministic execution. Local capture uses the
tested source-neutral scanner engine. Guarded exact bin calculation reduces
measured ARM cold reconstruction to
33.52–33.59 seconds from 39.39–39.62 seconds, with byte-identical outputs and
60/60 exact causal host prefixes. It still misses the five-second target. The
capability and summary contracts use v3; historical v1/v2 output is preserved
with the older binaries. No RF collection or
automatic startup accompanied this update. Qualifying live full-catalogue
cadence and closing E1-E4 remain open.

Exact-fit memoization is now included in the deployed application after
adversarial tests, allocation-failure injection, independent review, sanitizer
checks and 60 exact causal-prefix comparisons. The production ARM binary
reconstructs the complete fixture in 29.76 seconds with byte-identical output;
the preceding guarded-bin build took 33.61 seconds. The lane-local cache holds
at most 8 MiB of retained payload and keys full ordered membership plus bitwise
fit inputs. Optional allocation or capacity failures use the uncached fit.
This still does not establish continuous timing. Evidence:
`reports/2026_09_30_native_adaptive_deployment/application/exact-fit-cache-deployment.json`.

Contiguous selected-point index/weight storage is now qualified and deployed
alongside fit caching. Compiler-matched physical ABBA runs improve the mean
from 29.744 to 28.873 seconds (2.93%); the production binary takes 28.958 seconds.
Outputs and all 60 causal prefixes remain exact. Component tests cover unequal
weights, multiple peels, alternating holes and prefix extension. One buffer is
reused across peels; its payload grows from 8N to 16N bytes. Full host replay
retains all 11,747 observations and 64 tracks with an exact reference score.
The previous full physical application replay remains evidence for its frozen
composition, not a new end-to-end ARM run. Evidence:
`reports/2026_09_30_native_adaptive_deployment/application/chosen-point-deployment.json`.

A subsequent isolated peak-cutoff experiment preserves all 60 causal prefixes
and 30 synthetic tie/capacity configurations. Matched physical ABBA reduces cold
tracking from 28.869 to 27.842 seconds (3.56%) with exact output. Following
independent review it is integrated and deployed; production ARM tracking takes
27.857 seconds. Online/sanitizer tests and full host replay pass with 11,747
observations, 64 tracks, zero drops and the exact reference score. Evidence:
`reports/2026_09_30_native_adaptive_deployment/tracking/peak-threshold-research/receipt.json`.
Deployment: `reports/2026_09_30_native_adaptive_deployment/application/peak-cutoff-deployment.json`.

A separate per-track orbit interpolation stencil experiment precomputes exact
Hermite coefficients after horizon eligibility without changing arithmetic or
iteration order. Full two-site ARM scoring improves from 35.303 to 30.413 seconds
(13.85%), all four ABBA outputs byte-identical. Host, sanitizer and ARM boundary
tests pass, including final-knot cancellation and empty/rejected partitions.
Production integration is underway; the deployed application does not yet
include it. Evidence:
`reports/2026_09_30_native_adaptive_deployment/location/interpolation-stencil-research/physical-arm/receipt.json`.

Independent tracking lanes also show useful explicit parallelism: physical ABBA
means are 27.935 seconds serial and 14.921 seconds with two workers (1.87x), with
identical full output. Peak RSS grows from about 22.2 to 34.9 MiB. All 60 causal
prefixes and full-fixture ASAN/UBSAN/ThreadSanitizer checks pass. This remains an
isolated experiment; production needs a borrowed synchronous execution port so
the application owns the total worker budget and can keep existing callers
serial. Capture contention and five-second updates remain unqualified. Evidence:
`reports/2026_09_30_native_adaptive_deployment/tracking/parallel-lanes-research/receipt.json`.

The tracking execution port is now implemented without component-owned threads.
Legacy calls remain serial; explicit replay `--workers 1..4` uses the existing
bounded executor. Reverse completion, duplicate/missing/out-of-range dispatch,
allocation failure with joined callbacks, and cached-prefix recovery pass on
host/sanitizers/ARM. Full DS9 is exact with 1/2/4 workers; all 60 causal prefixes
and full-fixture ThreadSanitizer/ASAN checks pass. Physical production replay is
27.955 seconds serial versus 14.832 seconds with two workers. The qualified CLI
is installed at `/mnt/glrtbench/native-adaptive/tracking-current/leo-tracking`.
The live application still uses its previous serial composition. Evidence:
`reports/2026_09_30_native_adaptive_deployment/tracking/execution-port/receipt.json`.

The online coordinator now accepts the same borrowed execution port. DS9
serial/two-worker publication produces exact tracks, support digests, seeds,
identities, masks, times and frequencies. Failed dispatch preserves the prior
snapshot and retry generation semantics. Host and ASAN/UBSAN pass; physical
PLUTO+ lifecycle tests take 0.838 seconds and the complete prefix/search
comparison takes 37.043 seconds. The initial comparison test exhausted board
memory by retaining an extra coordinator; releasing it before subsequent search
checks resolves that test-lifetime defect. The passing test peaks at 387,016 KiB
with multiple reference/search instances, not one production coordinator.
Evidence: `reports/2026_09_30_native_adaptive_deployment/online/execution-port/receipt.json`.
This component is qualified; the installed live application remains unchanged.

Production location scoring now reuses exact interpolation stencils within
each score context. Scratch storage is lazy, capped at 16,384 entries
(1,179,648 bytes), and freed before growth; allocation failure or larger tracks
use the original generic interpolation. The 9,000-to-16,000 growth regression
checks the actual retained bound. Physical unit tests pass, and the full saved
64-track, 11,129-satellite, two-location fixture remains byte-identical with one
and two workers. Single-run wall times are 31.935 and 16.646 seconds respectively;
these do not establish concurrent capture performance. Evidence:
`reports/2026_09_30_native_adaptive_deployment/location/interpolation-stencil-production/physical-arm/receipt.json`.

The combined application is installed as release `7dc440a32a8b9b5f` on
192.168.1.15, with the previous release retained. Its host full saved-candidate
replay retains 11,747 observations, matches 64 tracks with zero queue drops, and
reproduces reference MSE 64906.771460780015. Online host/sanitizer and application
sanitizer/physical lifecycle checks pass. Live tracking and detection remain
serial, portable support math remains selected, and capture/autostart remain
off. Deployment receipt:
`reports/2026_09_30_native_adaptive_deployment/application/stencil-deployment.json`.

The production stencil scorer also passes both original 400-point host search
regressions: all 800 ordered coordinates, reference scores within the existing
1e-9 Hz tolerance, incumbents, and explicit budget-exhaustion state match. The
binary is byte-identical to the frozen production v7 host build. Both tests
completed in 137.38 seconds; this remains a recorded scientific boundary test,
not an ARM regional-discovery or capture-concurrent qualification. Evidence:
`reports/2026_09_30_native_adaptive_deployment/location/stencil-c7-regression/receipt.json`.

An isolated server-moment compatibility experiment now reproduces all 24,681
projection-harness output rows byte-for-byte on physical ARM, covering the
11,747 retained observations. It pins the reference server's fused-operation
power calculation explicitly; the production portable math remains unchanged.
The full test took 96.93 seconds versus 37.38 seconds without the compatibility
interposer, after an initial 60-second watchdog timeout. This closes the
experiment's numerical feasibility question, not the production C3 gate:
licensing/provenance, integration, support digest and partition parity, and
runtime cost must remain separately tested before deployment.

The isolated named server compatibility module now passes physical ARM tests:
11,747 retained DS9 supports and their decimal lexemes match exactly across
24,681 input rows (92.132 seconds; 2,237 cache hits, 9,510 misses). All 116,364
adversarial finite binary64 values also reproduce the server formatter exactly
(173.898 seconds). These are whole verification harness times, not isolated
per-observation costs. A subsequent constructor environment preflight passes a
targeted physical unit test; the full numerical evidence remains bound to the
prior binaries. No global pow interposition or live integration is involved.
Evidence: `reports/2026_09_30_native_adaptive_deployment/runtime/server-compat-physical-v1/receipt.json`
and `final-preflight-receipt.json` in the same directory.

A separate physical first-1,024-candidate prefix benchmark excludes parsing
and oracle verification from each timed derive call. Its 842 cache misses cost
9.547 ms mean / 10.119 ms p95; 182 hits cost 4.239 microseconds mean. This is a
measured reason to keep optional compatibility work out of the scanner's
serialized sink critical section, or explicitly qualify its callback latency
before adoption. It does not establish a full-scan latency distribution.
Evidence: `runtime/server-compat-physical-v1/prefix-latency-receipt.json` under the
native deployment report.

A separate recorded application replay now reconstructs 394 observations and
11 tracks, then scores one point against all 11,129 TLEs on PLUTO+ in 29.52
seconds. Cross-architecture testing exposed a support-moment rounding defect
that changed hashed training partitions. Exact integer center geometry with
explicit binary64 arithmetic fixes it: all 150 support records/digests/masks
are byte-identical, and the score differs by 1.3e-10 Hz. Frozen scientific
fixtures remain unchanged. This validates saved-candidate composition, not
full raw-IQ E2E or continuous search cadence.
Stage instrumentation separates the fixture cost from inference: on PLUTO+,
all-row prefix preparation takes 18.62 seconds, selected ingress/drain 0.43
seconds, track publication 1.61 seconds, reference-only comparison 2.02 seconds,
full-catalogue orbit construction 3.82 seconds, and the one-point score 1.33
seconds. These measured stages guide caching and background scheduling; the
29-second whole-test duration is not a steady-state point latency.

Full-history orbit storage now has a separate physical-device feasibility test:
96 ten-second knots over all 11,129 catalogue records, with two state banks,
consume 97.813 MiB of state storage and 111.98 MiB peak process RSS. Two builds
take 9.92 and 9.90 seconds on PLUTO+; all 66,774 catalogue/boundary coverage
checks pass. A 950-second ephemeris span can cover 600 seconds of observations,
tau search and knot guards with approximately 320 seconds of reuse. Integrate
that explicit interpolation profile into paced saved-candidate testing before
claiming full-history cadence. Memory feasibility does not establish global
interpolation accuracy or tracking/search throughput. The shared TLE identifier
parser preserves actual decimal and Alpha-5 catalogue identities.

The isolated interval-screened detector now matches all 295 passing server
candidates in the frozen 80-dwell host panel, and all eight passing candidates
in the three-call physical ARM check. Its normal ARM calls still take 8.68–8.70
seconds and its peer-fallback call 15.24 seconds, versus a 120-ms arrival
interval. These are approximately 72x and 127x the available interval. The
production fast detector remains a different, lower-recovery mode; do not join
its timing numbers to the exact detector's recovery numbers. Further full-grid
work needs a materially different algorithm or compute path, not merely a
second worker. The saved-data scientific checkpoint does not qualify live use.

Tracking now caches the unchanged per-point/per-slope Hough bin index within
each lane, preserving histogram addition and extraction order. The full
11,971-observation ARM prototype takes 39.50 seconds versus the earlier 78.07
seconds, with byte-identical output and 26,064 KiB peak RSS. The promoted cache
is capped at 32 MiB, falls back to scalar evaluation when unsupported, and
skips ineligible evidence. Host/sanitizer and final ARM component tests pass.
This improves full-scan throughput but does not establish the five-second
warm-update target. Count-bound eviction inside the requested history window
now has explicit telemetry and must disqualify full-history operation.

The independent-producer Analysis replay now passes on physical ARM at real
recorded pacing: 846 saved events over ten seconds yield 394 observations,
11 matched tracks and zero queue drops (high-water 191). Paced and unpaced
results are exact, as are host/ARM scores. The harness verifies original
single-anchor observation identities, support timestamps and moments before
inference; synthetic anchors use the sample counter's integer-nanosecond
lattice to avoid changing the saved clock model. It configures 600-second
history and 96 ten-second orbit knots but exercises only ten seconds of
evidence. Its orbit-profile score differs from the one-second-knot replay by
0.004308 Hz RMSE, retained as a diagnostic rather than a global error bound.

The initial bounded qualification was to replay all 24,681 saved candidate rows spanning
299.802 seconds with an independent paced producer, retaining explicit queue,
capacity, freshness and convergence failures. This remains saved-candidate
integration, not a substitute for the complete raw-IQ or live RF gates.
A coalesced final publication may isolate full-recording numerical correctness,
but cannot qualify continuous throughput. A separate run must request the
intended five-second publication cadence and expose missed cadence, result age
and losses rather than hiding reconstruction cost behind a longer interval.

Scope correction: the original C4 component gate and delivery checklist accept
the 64 reconstructed memberships with the six solver-dependent duplicate
identities documented. Exact reproduction of those six frozen-v1 candidate and
tracklet IDs is a separate compatibility lane, not an additional whole-goal
completion prerequisite. This does not relax C1-C3 scientific parity, the E1-E4
comparisons, or the requirement to preserve every mismatch and fixture.

Server-authority compatibility work remains relevant to C3 because decimal
spelling and tiny moment rounding differences enter the persisted support
digest. The initial host-only
compatibility prototype reproduces all 11,747 saved support moments bit for bit;
shortest-roundtrip formatting with Python's signed-zero spelling also reproduces
the original 394-observation prefix partitions and score exactly when supplied
the saved numeric moments. ARM emulation retains 446 third-moment bit differences
from the server's power function (maximum absolute error 7.75e-26), despite
passing physical tolerances. Exact server authority compatibility would require
a pinned implementation of that numerical path; the tested deterministic native
arithmetic remains unchanged. Fresh detector inputs and location outcomes still
need the separate integrated comparison. Keep published contracts and existing
goldens unchanged. The later isolated server-compatibility module and physical
receipts above supersede the prototype's power-function limitation; integration
and throughput remain separate gates. The read-only
[C4 duplicate identity audit](reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/README.md)
isolates the remaining six candidate-ID differences to one/two-ULP duplicate
choices sensitive to the server DGELSD fit. All 64 physical memberships agree.
A portable residual-tie policy would require a new version and explicit golden
review; no such policy or fixture change has been made.
The subsequent [DGELSD portability audit](reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/dgelsd-portability-addendum.json)
binds the pinned x86-64 NumPy/OpenBLAS implementation and its tall two-column
solver path. Existing alternative solvers already change these tied decisions;
the evidence does not support a small bit-equivalent replacement. Do not close
the optional exact-v1 identity lane by treating another mathematically equivalent
solver as the same numerical authority.

The additive support-profile Session path now also passes physical PLUTO+
CPU-only integration: 24,681 input rows, 11,747 projected observations, 64 tracks
and 3,372 track observations in 124.253 seconds, peak RSS 44,224 KiB. Fresh ARM
output reproduces all 58 comparable observation-ID vectors, support digests,
partition seeds and training masks. The six C4 identity ties remain documented
as the optional exact-v1 compatibility limitation.
See the [physical Session receipt](reports/2026_09_30_native_adaptive_deployment/runtime/session-compat-physical-v1/receipt.json).
The subsequent deferred stage moves support derivation from accept() to the
single analysis owner through the existing bounded queue. Its corrected build
passes host, ASan/UBSan, TSAN, ARM emulation and physical ARM replay. The latter
takes 124.313 seconds, peaks at 44,488 KiB RSS, and produces the identical track
output and 58 exact authority comparisons. The DS9 harness drains one event at
a time; separate component tests exercise concurrency and queue failures. See
the [deferred-stage physical receipt](reports/2026_09_30_native_adaptive_deployment/runtime/session-deferred-physical-v1/receipt.json).
This optional profile remains unselected in the deployed live CLI. Moving its
cost off the scanner callback does not remove CPU cost; backlog, capture
contention and continuous throughput still require qualification.

The real support profile now also passes a full recorded-candidate replay
through Analysis with an independent producer and background owner on PLUTO+.
At original playback speed, two analysis workers process 11,747 observations
and 64 tracks with zero drops and queue high-water 18. All scientific counters
match the host; RMSE differs by 9.095e-13 Hz against the existing 1e-6 Hz bound.
The producer runs for 299.802 seconds, followed by 34.266 seconds of processing.
Whole-process time is 365.479 seconds including fixture setup/validation, with
184,000 KiB peak RSS. This is coalesced publication and one fixed-site search,
without IQ detection or RF contention, not five-second regional-search proof.
Source-progress age stops advancing when input ends; the 34.266-second drain
must not be hidden behind that separate counter. See the
[physical profiled application receipt](reports/2026_09_30_native_adaptive_deployment/application/profiled-analysis-v1/physical-receipt.json).

The tracking residual predicate optimization passes all 60 causal DS9 prefix
comparisons exactly. On PLUTO+, serial full-recording control runs take
27.832/27.760 seconds and candidate runs take 26.210/26.215 seconds in reversed
pair order, a consistent 5.6–5.8% reduction. All four outputs are byte-identical
and retain 64 tracks; physical component tests also pass. This supports the
small production-source change but does not measure two-worker publication or
capture contention. The production change is now applied and passes host and
ASan/UBSan component suites, including focused admission/boundary tests, plus
another 60/60 exact causal-prefix comparison against the frozen control. See
the [production qualification](reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/receipt.json)
and [physical tracking receipt](reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/physical-arm/receipt.json).

The follow-up physical two-worker comparison uses the existing bounded runtime
pool: control 14.926/14.854 seconds versus optimized 14.073/14.079 seconds, in
control/optimized/optimized/control order. All four outputs are byte-identical
with 64 tracks. Peak RSS stays near 36 MiB. This confirms the gain with parallel
tracking but still exceeds five seconds before adding location scoring or
detector contention. See the [two-worker physical receipt](reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-two-worker-v1/physical-arm/receipt.json).

Historical detector baselines remain preserved: the scalar deployed-server
wrapper took 12.8–23.2 seconds per ARM call; the register optimization reduced
that to 10.3–18.3 seconds. The later interval-screen results above supersede
those timing measurements without joining their recovery evidence to the fast
production detector. All remain experimental; more cores alone cannot close
the measured throughput gap.

---

# LEO Tracker ReduxRedux: Architecture and Execution Plan

Status: authoritative implementation plan; all implementation requirements are initially `PENDING`.

This document records the decisions agreed for the fresh implementation in this repository. It is the contract for architecture, module ownership, delivery order, and acceptance. The older `leo-tracker`, `leo-tracker-redux`, `pluto-plus-utils`, their reports, and the attached long-dwell analysis documents are evidence and scientific references, not implementation instructions and not compatibility requirements.

## 1. Mission and scope

Build a lean platform that can:

- acquire CI16 IQ continuously or at configurable duty cycles from one or two remote Pluto+ radios over Ethernet;
- use one or both receive channels on each Pluto+;
- record exact 60-second CH4-lower single-RX dwells from either radio
  independently or from both radios under best-effort synchronized release;
- make an honest best effort to overlap captures from two radios without claiming hardware or phase synchronization;
- durably store self-describing, compressed, immutable raw IQ recordings on the local RAID;
- process new recordings and explicitly reprocess existing recordings with the current analysis pipeline;
- restore the previously demonstrated Starlink/Qin/QAM detection capability before extending it;
- support whole-dwell survey, candidate tracking, Doppler, locked acquisition, QAM evidence, controls, and later research stages;
- expose equivalent search, provenance, paths, power, Starlink, QAM, Doppler, and health information through a CLI and read-only web UI;
- protect selected recordings indefinitely and automatically reclaim unprotected data under storage pressure;
- continuously validate the system against a small protected corpus of real and controlled TEST recordings.

The expected maximum acquisition topology is two Pluto+ radios, with two RX channels per radio. Sample rate and dwell duration are research variables, not hard-coded constants. The initial operating point is expected to be near 2.5 MS/s, with duty cycles ranging from roughly 10% to 100%.

### Explicit non-goals for the initial system

- No phase-coherent or sample-coherent claim between separate Pluto+ radios.
- No acquisition or reprocessing controls in the web UI.
- No authentication, authorization, or TLS; the UI is open HTTP on the trusted LAN.
- No Redis, Celery, Kafka, Kubernetes, network object-store service, or NFS control plane.
- No API, database-schema, or file-layout compatibility with either older tracker repository.
- No automatic historical back-processing caused by a schema or software release.
- No deletion from `/mnt/qnap01`; the new project must contain no QNAP deletion path.
- No attempt to put raw IQ or large numerical artifacts inside PostgreSQL.

## 2. Authoritative system shape

```text
1-2 Ethernet Pluto+ radios
          |
          v
 acquisition coordinator + per-radio workers
          |
          v
 immutable recording bundle on /srv/bulk
          |                         \
          v                          v
 PostgreSQL catalog/jobs       retention controller
          |
          v
 processing workers -> immutable scientific products
          |                         |
          v                         v
 presentation projectors -> stable presentation products
          |
          v
 read-only FastAPI -> React web UI
          ^
          |
 acquisition and processing CLI
```

There are four long-running responsibilities:

1. Acquisition owns radios and publishes recording bundles.
2. Processing workers execute leased, versioned analysis jobs.
3. The read-only API serves current catalog and presentation data.
4. PostgreSQL is the catalog, job control plane, and current-analysis selector.

Retention runs from a systemd timer. Acquisition must not depend on analysis keeping up; a processing backlog is acceptable and visible.

## 3. System invariants

These rules may not be relaxed without an explicit architecture decision record.

1. **Raw IQ is immutable.** A committed recording is never edited in place.
2. **A recording is self-describing.** Its manifest and stream metadata are sufficient to reconstruct the catalog without PostgreSQL.
3. **Partial output is not committed output.** A missing final manifest or incomplete atomic publication cannot appear as a usable recording or analysis run.
4. **One session is the acquisition unit.** A synchronized two-radio attempt is retained or purged as one session, even when one stream fails.
5. **Timing claims are evidence-based.** Store requested and observed times, timing source, skew, overlap, gaps, and uncertainty; never infer coherence from a software barrier.
6. **Database and filesystem have separate roles.** PostgreSQL holds searchable state and pointers; `/srv/bulk` holds IQ and large artifacts.
7. **Analysis runs are immutable.** Reprocessing creates a new run and never modifies the current run in place.
8. **Promotion is atomic.** The UI sees either the previous complete run or the replacement complete run, never a mixture.
9. **Analyzer code is infrastructure-blind.** Analyzers do not construct paths, query PostgreSQL, or serve HTTP.
10. **Scientific and UI schemas are separate.** Frequently changing scientific products are converted by projectors into bounded, versioned presentation contracts.
11. **No silent test skips.** A required fixture that is absent or corrupt fails its declared test lane clearly.
12. **TEST is first-class provenance.** TEST recordings are obvious, permanently held by default, and excluded from normal aggregates unless explicitly included.
13. **Holds beat retention.** A held recording and its required current products are never automatically deleted.
14. **QNAP is read-only evidence.** Copying from QNAP is explicit; source files remain untouched.
15. **Migrations do not imply analysis.** Database evolution never silently queues old recordings.
16. **No-result is a scientific result.** `no_candidate`, `partial_coverage`, and `insufficient_data` are not confused with worker failure.

## 4. Repository and module boundaries

The target implementation is a Python monorepo with a TypeScript browser application compiled to static assets. A concrete module layout is:

```text
src/leo/
  domain/          IDs, value types, state machines, shared contracts
  config/          host config and immutable capture-profile loading
  catalog/         SQLAlchemy models, Alembic integration, repositories
  storage/         recording/artifact stores, manifests, IqReader
  acquisition/     Pluto transport adapters, coordinator, radio workers
  pipeline/        analyzer SDK, DAG, leases, executor, promotion
  analysis/
    quality/
    power/
    waterfall/
    starlink/
    qam/
    doppler/
    controls/
  presentation/    version-specific scientific-to-UI projectors
  api/             read-only HTTP routes and response contracts
  cli/             acquire and process command groups
  operations/      retention, reconciliation, health, maintenance
web/               React + TypeScript + Vite application
tests/
  unit/
  contract/
  integration/
  dsp/
  e2e/
  hardware/
```

### Required interfaces

`CatalogRepository` owns catalog transactions and exposes operations such as:

- create/finalize a capture session;
- create an analysis run and its job DAG;
- claim, heartbeat, complete, fail, and reclaim a job lease;
- register an immutable product idempotently;
- seal and atomically promote an analysis run;
- search sessions and resolve the current run;
- create/remove retention holds and record retention events.

`RecordingStore` owns recording layout, durable publication, validation, and reconstruction.

`ArtifactStore` owns logical artifact URIs, temporary output, hashing, `fsync`, atomic publication, validation, and garbage-collection eligibility.

`IqReader` exposes receiver-aware sample slices and streaming block iteration with exact sample/time mapping across compressed shards.

`Analyzer` receives `AnalysisContext`, `IqReader`, `ProductReader`, and `OutputSink`, and returns a typed `StageResult`.

`PresentationProjector` consumes declared scientific product versions and emits a declared presentation schema version.

`RadioTransport` isolates network/device-specific operations so acquisition coordination can be tested without hardware. Proven serial-attested Ethernet transport, paired-RX capture, continuity metadata, health checks, constant-IQ checks, and exclusive ownership concepts from `pluto-plus-utils` should be adapted behind this boundary.

The initial analyzer registry is explicit and in-repository. Dynamic third-party plugin discovery is deferred until there is a real need.

## 5. Acquisition design

### 5.1 Domain model

The primary entity is `capture_session`.

A session contains one or two `radio_stream` records. A radio stream contains one or two enabled receiver paths. RX0 and RX1 from the same Pluto+ are paired because they are returned by the same device refill. Separate Pluto+ radios are not assumed to share clocks.

A session supports:

- one Pluto+, one enabled RX;
- one Pluto+, paired RX0/RX1;
- two Pluto+ radios, with one or two RX paths each;
- best-effort synchronized mode;
- a partial session in which one radio fails and the surviving radio completes;
- imported legacy and TEST recordings.

### 5.2 Capture profiles

Replace the former “arms” concept with immutable, revisioned `capture_profile` definitions.

Human-edited YAML defines a profile. The first use creates an immutable database revision and digest. Editing a named profile creates a new revision; old sessions continue to cite the exact revision used.

Profile fields include:

- dwell duration;
- sample rate;
- RF bandwidth;
- RF/IF center and Starlink edge/channel intent;
- enabled receivers;
- gain mode and gain values;
- buffer/refill size;
- continuity policy;
- radio settle/prime behavior;
- synchronization mode;
- chunk/compression policy reference;
- campaign name and default tags.

Operators may select a profile or apply recorded one-shot overrides without editing code. All effective values and their digest are captured in the session manifest.

### 5.3 Best-effort two-radio synchronization

Synchronized mode means maximizing actual time overlap. It does not mean hardware triggering, common-clock timing, phase coherence, or exact sample alignment.

The coordinator must:

1. Discover, connect, serial-attest, and exclusively lock both radios concurrently.
2. Apply the same session intent and the correct per-radio settings.
3. Settle and prime both devices.
4. Have each radio worker report ready.
5. Release both workers against one near-future host UTC target.
6. Record independent observed first-sample and end-time evidence from each stream.
7. Calculate start skew, exact overlap interval, overlap duration, overlap fraction, and timing uncertainty.
8. Continue a surviving stream when its peer fails, while marking the session partial.

The manifest records the timing method for every value, for example device/FPGA metadata, host monotonic/UTC bracketing, or inferred sample count. The UI and CLI must display the observed overlap and an honest synchronization grade.

### 5.4 Acquisition reliability

- One bounded capture pipeline per radio separates device refill from compression/disk writing.
- Bounded queues apply an explicit failure/backpressure policy; data loss is never hidden.
- Every refill contributes continuity, sequence, sample-count, and timing evidence.
- Constant-IQ, clipping, gap, late-refill, and device-error evidence is recorded.
- Acquisition runs at normal CPU/I/O priority; analysis runs at lower weights.
- Consecutive dwell operation records the actual inter-session gap and never assumes 100% duty was achieved.
- Losing PostgreSQL after durable bundle publication must not lose the recording; a reconciler registers it later.

## 6. Recording storage

### 6.1 Storage topology

The canonical live root is the local cached RAID:

```text
/srv/bulk/leo/
  spool/
  recordings/YYYY/MM/DD/<session-id>/
  analysis/<session-id>/<analysis-run-id>/
  test-corpus/
  postgres/
  backups/
```

`/mnt/qnap01` is a legacy-import and evidence source only. It is not the live recording store, queue, lock service, or backup target. Local RAID is sufficient for the initial durability requirement.

### 6.2 Bundle layout

```text
recordings/YYYY/MM/DD/<session-id>/
  manifest.json
  radio-<serial>/
    iq-000000.ci16.zst
    iq-000001.ci16.zst
    timeline.jsonl.zst
```

Initial IQ encoding:

- signed little-endian CI16;
- logical layout `(sample, receiver, component)`;
- receiver order declared in the manifest;
- independently compressed Zstandard shards;
- approximately 128 MiB uncompressed per shard, aligned to complete refills;
- sample start/count plus compressed and uncompressed SHA-256 for every shard.

Zstandard level 3 is the initial default, subject to an on-host throughput/ratio qualification. It is configuration, not a scientific profile attribute. Independent shards support bounded-memory reading, random access, corruption isolation, and parallel processing.

### 6.3 Thin and detailed metadata

`manifest.json` is the small reconstruction and discovery record. It includes:

- session ID, source type, tags, and profile revision/digest;
- software release and host identity;
- radio serials, endpoint identity, firmware/hardware epoch, and receiver mapping;
- complete effective RF, sample, bandwidth, gain, buffer, and compression settings;
- requested and observed start/end times and the evidence/uncertainty for each;
- sample counts, encoding/layout, continuity summary, and stream terminal state;
- paired-radio relationship, skew, overlap interval/fraction, and synchronization grade;
- calibration references and digests;
- full chunk inventory, sizes, sample ranges, and hashes.

Detailed refill-level timing and continuity evidence lives in compressed `timeline.jsonl.zst`.

### 6.4 Crash-safe publication

1. Capture into `spool/<session-id>.partial`.
2. Publish each completed shard durably and append durable continuity metadata.
3. Close and verify stream inventories.
4. Write the session manifest last.
5. `fsync` files and directories.
6. Atomically rename the session into its dated recording path.
7. Register/finalize the session in PostgreSQL.

A crash after step 6 but before step 7 is repaired by catalog reconciliation. A partial spool directory is never analyzed as a committed recording. Recovery tooling may validate and explicitly finalize a provably complete partial bundle; ambiguous partial data is quarantined and reported, not silently accepted or deleted.

## 7. PostgreSQL catalog and migrations

Use PostgreSQL 18, SQLAlchemy 2, Psycopg 3, and Alembic. Tests use real PostgreSQL, never SQLite as a behavioral substitute.

### 7.1 Stable relational schema

Initial stable tables:

- `radio`
- `receiver_path`
- `hardware_epoch`
- `frequency_calibration`
- `capture_profile`
- `capture_profile_revision`
- `capture_session`
- `radio_stream`
- `recording_chunk`
- `tag`
- `session_tag`
- `retention_hold`
- `retention_event`
- `pipeline_release`
- `analysis_run`
- `processing_job`
- `processing_job_dependency`
- `processing_job_attempt`
- `analysis_product`
- `product_dependency`
- `current_analysis`
- `analysis_summary`

Large waterfalls, IQ, tracks, and arrays are paths plus hashes in the catalog, not database blobs.

Algorithm-specific detail initially belongs in versioned artifact schemas and bounded JSONB summaries. Only metrics proven useful for cross-recording search are promoted to indexed relational columns through reviewed migrations.

### 7.2 Migration policy

- Maintain one linear Alembic head initially.
- Never edit an applied migration.
- Every migration is reviewed with generated SQL.
- CI runs `alembic check` for ORM/schema drift.
- CI upgrades both an empty database and the previous released schema snapshot.
- Destructive or type-changing migrations use an explicit expand/migrate/contract sequence when needed.
- Product schema evolution is independent from relational migration.
- Old recordings and old product metadata remain readable after migration.
- Migrations never enqueue reprocessing implicitly.

## 8. Processing control plane

PostgreSQL is the only processing queue. A `processing_job` is leased using a short transaction and `FOR UPDATE SKIP LOCKED`.

Job states are `pending`, `leased`, `succeeded`, `failed`, and `cancelled`. Each logical job is unique on `(run_id, stage_key, scope_key)`. Attempts are immutable records. Leases use database time, have an owner and expiry, and are extended by heartbeat. An expired lease is safely reclaimable. Execution is at-least-once, so product publication and completion are idempotent.

The DAG stores explicit dependencies. A job is claimable only when all required dependencies have successful terminal scientific outcomes. Downstream behavior for `no_candidate`, `partial_coverage`, and `insufficient_data` is declared by the graph rather than embedded in worker code.

Start with four lower-priority processing workers and tune using observed CPU, RAM, disk, and backlog measurements. Resource classes prevent too many heavy waterfall or dense-acquisition stages from running together.

## 9. Analysis products and artifact storage

### 9.1 Run layout

```text
/srv/bulk/leo/analysis/<session-id>/<run-id>/
  scientific/
    quality/...
    power/...
    waterfall/...
    starlink-survey/...
    candidate-tracks/...
    qam/...
    doppler/...
    controls/...
  presentation/
    summary/...
    timelines/...
    waterfall/...
    overlays/...
  manifest.json
```

PostgreSQL stores logical URIs such as `bulk://analysis/<session>/<run>/...`; configuration resolves them to `/srv/bulk/leo`. The resolved path is available to CLI/UI users.

### 9.2 Scientific products

Scientific products preserve analysis evidence at useful precision and may evolve frequently. Initial approved encodings are:

- JSON or JSON.zst for small structured evidence;
- Parquet for candidate tables, tracks, and long time series;
- a documented, versioned tiled numeric encoding for large matrices.

Every `analysis_product` and run manifest records:

- product kind, role, semantic schema version, and media type;
- producing stage/algorithm/configuration digest;
- exact recording and input-product digests;
- receiver, segment, time/frequency scope, units, and coverage;
- semantic status such as `complete`, `partial_coverage`, `no_candidate`, or `insufficient_data`;
- logical URI, byte size, and SHA-256.

### 9.3 Presentation products

The UI does not read arbitrary scientific files. Version-specific projectors emit a stable, bounded presentation contract containing:

- recording/run summary;
- downsampled power and quality timelines;
- bounded waterfall tile pyramid and index;
- candidate, CFO, and Doppler overlays;
- QAM/pilot display evidence;
- coverage, units, provenance, and failure/no-result states.

For paired captures the recording detail exposes one explicitly keyed view per
manifest stream/radio. Detection, whole-dwell controls, QAM, Doppler,
waterfalls, and overlays are selected by product `scope_key`; they are never
silently borrowed from a peer stream. The original top-level scientific fields
remain a deterministic primary-stream compatibility view.

Presentation schema and HTTP API versions evolve deliberately. A scientific product change normally requires a projector update, not a browser rewrite or relational migration.

### 9.4 Product and run publication

Each product is written beneath the analysis spool, hashed, flushed, `fsync`ed, and atomically moved to its final path before idempotent catalog registration. The run manifest is written last after required products reach accepted terminal states. Once sealed, the directory is immutable.

The UI only reads a sealed run selected by `current_analysis`. Failed/incomplete run output remains non-current and is eventually cleaned under an explicit failed-run policy.

## 10. Analyzer contract and pipeline graph

Conceptual analyzer interface:

```python
class Analyzer:
    spec: StageSpec

    def run(
        self,
        context: AnalysisContext,
        iq: IqReader,
        inputs: ProductReader,
        outputs: OutputSink,
    ) -> StageResult: ...
```

`StageSpec` declares:

- stage and algorithm versions;
- accepted input product kinds/schema versions;
- output product kinds/schema versions;
- validated configuration schema;
- CPU, RAM, and I/O resource class;
- deterministic/non-deterministic behavior;
- retry and accepted terminal-outcome policy.

Analyzers are independently unit-testable with fake readers, product inputs, and sinks. `OutputSink` alone owns temporary paths, hashes, publication, and registration.

## 11. Reprocessing semantics

`leo process reprocess SESSION_ID` means “replace the UI/CLI-visible analysis with a newly completed run of the current pipeline,” not “mutate or delete the former run before work begins.”

1. Validate that raw IQ, manifest, and required calibration inputs exist.
2. Create a new `analysis_run` and complete versioned job DAG.
3. Process into a new run directory while the former current run remains readable.
4. Verify accepted terminal state and required scientific/presentation products.
5. Seal the run manifest.
6. In one transaction, mark success, switch `current_analysis`, and update the indexed `analysis_summary`.
7. Make large superseded artifacts eligible for later garbage collection while retaining their small receipts and provenance.

Initially allow only one active run per session. A second request fails clearly rather than creating ambiguous promotion order. Failed reprocessing never changes the current pointer. An API request resolves one current run ID at its start so it cannot mix product generations.

## 12. Scientific recovery and long-dwell analysis

Parity with demonstrated historical results is the first scientific milestone. Do not redesign the detector until the numerical primitives are recovered and protected by tests.

Port and freeze behind analyzer boundaries:

- Qin waveform/template generation;
- historical symbolwise acquisition;
- multiple timing/alias candidate retention;
- receiver-centered calibrated CFO search;
- conditioned fine-CFO refinement;
- pilot constellation and QAM metrics;
- inverse-noise dual-receiver combination.

The frequency contract is:

```text
absolute CFO = immutable receiver calibration center + searched residual CFO
```

Never return to a universal absolute `+/-400 kHz` acquisition box. Calibration and immutable receiver center are explicit inputs and provenance.

The production graph is one semantic graph with different budgets, not unrelated Quick/Standard/Research implementations:

```text
raw validation
  -> clipping, constant-IQ, continuity, and quality
  -> power timeline
  -> bounded waterfall
  -> calibrated sparse whole-dwell survey
  -> multiple acquisition basins
  -> activity-region and continuity tracking
  -> dense epoch/CFO refinement
  -> de-Doppler and locked integration
  -> pilot/QAM evidence
  -> held-out/null/surrogate controls
  -> optional TLE association
  -> scientific summary
  -> presentation projectors
```

- **Quick:** every recording; quality, power, bounded waterfall, sparse whole-dwell survey, bounded candidate cloud.
- **Standard:** normal full processing; tracking, dense acquisition, Doppler, controls, and QAM.
- **Research:** explicit/manual policy; wider searches, alternate models, more surrogates, and long integrations.

Compute tier and scientific confidence are distinct. Research output is not automatically a detection. Candidate lineage, search coverage, calibration, controls, and reasons for rejection/promotion must be retained.

## 13. Retention and deletion

Measure the filesystem containing `/srv/bulk/leo`, not the root filesystem.

- At 70% used, begin automatic reclamation.
- Reclaim until usage falls to 65%.
- At 75%, emit a prominent operational warning.
- At 80%, stop admitting new captures if no eligible data can be removed.

Reclamation order:

1. Expired failed-run spool and unreferenced temporary artifacts.
2. Eligible large superseded analysis artifacts.
3. Oldest eligible unheld capture sessions, deleting raw IQ and replaceable large current scientific artifacts while retaining a small tombstone, searchable summary, manifest identity, hashes, timing, and paths.

A session is eligible only if it is fully committed, unheld, not TEST, has no active processing/reconciliation claim, is not already purging, and satisfies the configured minimum analysis policy. A paired session is purged as a unit.

`retention_hold` is indefinite until explicitly removed. A hold protects raw IQ, manifest, and required current analysis/presentation products. TEST imports receive a hold automatically. Superseded experimental artifacts of a held recording may still be collected once they are not current or explicitly held.

Deletion is serialized and auditable:

1. Select and lock exact catalog targets.
2. Mark the session/artifacts `purging` transactionally.
3. Recheck holds and resolved paths.
4. Delete only under the configured `/srv/bulk/leo` root.
5. Record bytes reclaimed and tombstone state.

No code path may delete from `/mnt/qnap01`. Any future source deletion feature requires a separate design and explicit user authorization.

## 14. CLI and web UI

Use one `leo` executable with two top-level operational areas.

### 14.1 Acquisition CLI

```text
leo acquire radios
leo acquire doctor
leo acquire profiles
leo acquire once --profile NAME
leo acquire run --profile NAME
leo acquire status
```

### 14.2 Processing/data CLI

```text
leo process search [filters]
leo process show SESSION_ID
leo process paths SESSION_ID
leo process reprocess SESSION_ID
leo process jobs
leo process pin SESSION_ID --reason TEXT
leo process unpin SESSION_ID
leo process import-qnap MANIFEST --copy --tag TEST
leo process retention-status
leo process retention-run --dry-run
```

All commands have concise human-readable output and `--json`. Search supports time, radio, receiver, profile, source type, TEST, tag, hold, processing state, pipeline release, power, candidate, QAM, Doppler, coverage, and storage state where meaningful.

### 14.3 Read-only API and browser

FastAPI serves React/Vite static assets and GET/HEAD API routes. Initial route families are:

- health, storage use, and processing backlog;
- recording/session search;
- recording detail and resolved paths;
- current analysis and provenance;
- bounded presentation products and tiles;
- aggregate power, Starlink, QAM, and Doppler statistics.

There are no HTTP mutation routes for acquisition, reprocessing, pinning, retention, or deletion. The LAN service is open HTTP without authentication as explicitly required.

The browser must show:

- clear TEST and held badges;
- recording/profile/radio metadata and exact paths;
- actual cross-radio skew, overlap, uncertainty, and partial-stream state;
- quality and power timelines;
- synchronized receiver waterfalls and detector overlays;
- candidate lineage, CFO/epoch tracks, QAM, Doppler, and optional TLE evidence;
- pipeline/product versions, coverage, controls, no-result/failure states;
- storage pressure, purge state, and job backlog.

## 15. Regression corpus and test lanes

Create a small immutable corpus under `/srv/bulk/leo/test-corpus`. Copying from QNAP is allowed; deleting or moving the QNAP source is not.

Initial fixture categories:

1. RETRO known-pilot candidate and selected short window.
2. J1 unavailable historical evidence, with exact expected identities and the
   recovery audit retained but no executable or passing fixture claim.
3. One small synchronized QNAP pair for layout/import/UI validation, labeled `unlabeled` rather than detector truth.
4. Deterministic injected positive over frozen real noise.
5. Deterministic null and stationary-interferer/confounder controls.

A separately acquired or recovered immutable calibrated fixture is a future
capability gate. It is not J1 under another name and is not declared present
until its inputs, calibration authority, truth role, controls, and tolerances
have passed independent review.

Every executable fixture records an immutable fixture ID,
source/digest/license/provenance, expected role, expected metrics/tolerances,
`source_type=TEST`, tag `TEST`, and an automatic indefinite hold. An unavailable
historical declaration instead retains expected identities and audit lineage
without materializing bytes or claiming execution. TEST data is visible in
UI/CLI but excluded from ordinary aggregates by default.

Test lanes:

- **Every change:** unit, property, schema-contract, migration, small selected real-IQ windows, API contract, and focused browser tests.
- **Main branch:** complete small TEST-corpus ingestion through PostgreSQL, workers, CLI, API, and Chromium.
- **Nightly/release:** full 60-second real-data reprocessing, detector parity, long-dwell controls, resource bounds, and full browser flow.
- **Hardware canary:** scheduled single- and dual-Pluto captures; separate from deterministic CI.

Playwright runs real Chromium and retains traces/screenshots on failure.

## 16. Deployment

Use systemd directly on the dedicated host:

- `leo-acquisition.service`
- `leo-worker@.service`
- `leo-api.service`
- `leo-retention.timer`
- PostgreSQL 18
- nightly corpus/release qualification timer

Acquisition has normal CPU/I/O priority. Analysis workers have lower CPU/I/O weight so a backlog cannot interfere with recording. Services expose structured logs and health state keyed by session, run, job, radio, and worker IDs.

Back up PostgreSQL metadata and configuration locally. Raw data durability is the local RAID plus integrity manifests; no second raw copy is required initially.

## 17. Parallel execution program

Status values are `PENDING`, `IN PROGRESS`, `BLOCKED`, and `DONE`. All work packages begin `PENDING`.

### Dependency graph

```text
WP0 contracts/scaffold
  |--- WP1 catalog/migrations/jobs ---------|
  |--- WP2 storage/readers -----------------|
  |--- WP3 Pluto acquisition ---------------|--> WP8 integrated operations
  |--- WP4 analyzer SDK/executor -----------|
  |--- WP5 corpus + detector parity --------|--> WP9 long-dwell science
  |--- WP6 presentation/API/web ------------|
  `--- WP7 retention/reconciliation --------|

WP3 + WP5 + WP9 -> WP11 CH4 single-RX matched recovery
WP8 + WP9 + WP11 -> WP10 qualification and production gate
```

WP1-WP7 may proceed in parallel after WP0 freezes the shared identifiers, manifests, state machines, and interfaces. Implementations use fakes until their dependencies land. Package ownership must keep work in separate module trees; cross-package changes require contract review.

### WP0 — Contracts and repository scaffold (`DONE`)

Deliver:

- Python/TypeScript project skeleton and developer commands;
- architecture decision records for IDs, state machines, timing, schemas, and logical URIs;
- Pydantic/JSON Schema contracts for recording and run manifests;
- shared enumerations and error semantics;
- fake catalog, radio transport, IQ reader, product reader, and output sink;
- lint, type-check, unit-test, and real-PostgreSQL CI foundations.

Exit gate: contracts round-trip in Python and TypeScript, state transitions reject illegal moves, and downstream packages can build against fakes.

### WP1 — Catalog, migrations, and PostgreSQL jobs (`DONE`)

Deliver:

- stable schema and initial Alembic migration;
- repository layer with explicit transactions;
- job DAG, leases, heartbeats, retries, attempt history, and cancellation;
- run sealing/promotion and current summary transaction;
- search and hold primitives.

Exit gate: migration, concurrency, lease-expiry, idempotency, dependency, and atomic-promotion tests pass against PostgreSQL 18.

### WP2 — Recording/artifact storage and readers (`DONE`)

Deliver:

- recording and artifact stores;
- Zstandard shard writer/reader and receiver-aware `IqReader`;
- durable atomic publication;
- logical URI resolver;
- checksum validation, manifests, reconciliation, and quarantine support;
- generated-data fault-injection harness.

Exit gate: kill-point tests expose no partial committed object, random reads across shard boundaries are exact, corrupt data is detected, and catalog reconstruction works from manifests.

### WP3 — Pluto acquisition (`DONE`)

Deliver:

- adapted Ethernet/serial-attested Pluto transport;
- radio discovery, exclusive ownership, doctor/health, and settings application;
- one-radio paired-RX capture;
- bounded streaming compression/writing;
- two-radio readiness barrier and target release;
- actual timing/overlap/continuity accounting and partial-session behavior;
- profile-driven `once` and continuous operation.

Exit gate: generated transport tests plus hardware canaries prove correct settings/provenance, paired layout, honest overlap, peer-failure survival, and clean recovery from process/device/network failure.

### WP4 — Analyzer SDK and processing executor (`DONE`)

Deliver:

- analyzer/stage/product contracts and explicit registry;
- validated pipeline DAG and release digest;
- worker lease loop and resource-class scheduling;
- product output sink and run sealer;
- reprocess CLI and atomic current-run switch.

Exit gate: fake-analyzer integration proves retry safety, semantic no-result handling, immutable outputs, failed-run isolation, and atomic replacement.

### WP5 — TEST corpus and detector parity (`DONE`)

Deliver:

- protected fixture registry/importer;
- protected, fail-closed RETRO fixture and immutable numerical oracles;
- explicit J1 unavailable-historical-evidence declaration retaining its exact
  expected IQ, slice, and calibration identities;
- deterministic positive/null/confounder fixtures;
- Qin, historical acquisition, calibration, fine-CFO, QAM, and receiver-combination ports;
- numerical oracle tests with documented tolerances.

Exit gate: reproducible historical RETRO results are reproduced within
tolerance, null/control behavior is bounded, a missing required fixture fails
explicitly, and unavailable J1 evidence cannot be presented as executable,
passing, calibrated, or silently omitted.

RETRO satisfies its protected historical parity lane. Exact J1 IQ and frozen
calibration evidence remain unavailable under the bounded recovery audit. The
project owner accepted Option B in
`docs/adr/0006-j1-acceptance-evidence-disposition.md` on 2026-08-19. This closes
only the recoverable RETRO numerical-candidate parity requirement and the
machine-testable J1 disposition. It makes no J1 parity, calibrated-detection,
specificity, attribution, or payload-decoding claim.

### WP6 — Presentation, read-only API, and web UI (`DONE`)

Deliver:

- presentation schema v1 and projectors;
- read-only FastAPI routes and OpenAPI contract;
- React search, session detail, visualization, provenance, health, and storage views;
- conspicuous TEST/held/partial/no-result/failure states;
- Playwright fixtures, traces, and full browser flows.

Exit gate: synthetic and real TEST presentations pass schema contracts and Chromium E2E without HTTP mutation routes.

### WP7 — Retention, reconciliation, and operations (`DONE`)

Deliver:

- 70%/65% watermark controller, 75% warning, and 80% admission stop;
- hold-aware, session-unit deletion and tombstones;
- failed/superseded artifact GC;
- bundle/run/catalog reconcilers;
- dry-run/status CLI and auditable events;
- systemd definitions and operational health.

Exit gate: destructive tests on generated isolated data prove exact target resolution, pinned/TEST/current immunity, paired-session atomicity, threshold behavior, and no possible QNAP target.

### WP8 — Integrated acquisition-to-UI vertical slice (`DONE`)

Deliver:

- one real/simulated capture through bundle, registration, jobs, baseline analysis, projection, CLI, API, and browser;
- reprocessing current-run replacement;
- service restart and backlog recovery.

Exit gate: a fresh TEST capture is discoverable with correct paths/metrics in CLI and Chromium; successful and failed reprocessing exhibit the required pointer semantics.

### WP9 — Whole-dwell Standard/Research pipeline (`DONE`)

Deliver:

- sparse survey, multi-basin candidate cloud, continuity tracking, dense refinement, de-Doppler, locked integration, controls, QAM, optional TLE association, and presentation overlays;
- Quick/Standard/Research budget configurations for one graph;
- bounded-memory and coverage accounting.

Exit gate: full dwell fixtures preserve the correct basin, reproduce parity evidence, reject/qualify controls honestly, and remain inside measured resource budgets.

### WP11 — CH4-lower single-RX capture and matched pilot/QAM recovery (`IN PROGRESS`)

Deliver:

- one immutable 60-second, 2.5 MS/s, CH4-lower profile selecting the reviewed
  RX1/LNB-B and RX1/LNB-D reference paths at a frozen 40 dB gain arm;
- independent one-radio captures from `radio_pluto_5d4d` and
  `radio_pluto_19f2`, plus best-effort synchronized captures from both radios,
  all using the same profile revision;
- immutable, receiver/path/hardware-epoch-specific frequency-calibration
  inputs and explicit center-plus-residual search provenance, with no
  acceptance-eligible synthesized zero-calibration fallback;
- a versioned matched-known-pilot evaluator over exactly 600 predeclared
  25,000-sample windows spaced every 250,000 samples in each complete dwell;
- a pinned legacy-oracle receipt and an independent native receipt evaluated on
  the exact same IQ, retaining every window and the full matched-discordance
  table;
- normal catalog/artifact publication plus CLI and read-only UI presentation of
  exposure, candidate recovery, QAM accuracy/EVM, calibration, and reasons for
  inconclusive or rejected results; and
- a sealed hardware campaign receipt binding source revision, profile,
  calibration, recording manifests, processing runs, products, overlap, and
  statistical acceptance results.

Exit gate: at least ten complete independent dwells per radio and ten complete
synchronized-pair dwells pass the exact capture geometry and digest gates. For
each radio in each mode, 6.0 seconds/10% of every dwell is evaluated with no
silent denominator reduction; at least 30 legacy-positive windows exist or the
stratum is explicitly `INCONCLUSIVE`; the native path recovers at least 90% of
legacy-positive windows with a one-sided 95% lower confidence bound of at least
80%; recovered epoch/CFO agree within 8 circular samples and 500 Hz; every
capture with a legacy QAM-positive window has a native QAM-positive window; and
the paired native-minus-legacy hard-symbol-accuracy lower 95% bound is at least
`-0.05`. These are candidate-recovery claims only: specificity, Starlink
attribution, payload decode, cross-radio phase coherence, and device-side
sample-loss observability remain unclaimed unless separately proven.

Committed WP11 software foundation now includes the immutable centered RX1
profile and strict 10+10+10 capture-audit contract; pinned legacy-oracle and
release-local native execution; evidence-only calibration and matched-recovery
graphs; authoritative calibration, product-dependency, campaign, retention, and
outer-seal catalog lineage; deployed-release-derived configuration; a verified
RecordingStore-to-frozen-oracle bridge; queue gating on all 40 legacy receipts;
`leo process wp11 config|create|legacy|queue|finalize|show`; and a
bounded GET/HEAD-only campaign API and browser presentation. The authoritative
reader independently verifies immutable documents, exact capture/calibration/run/
product lineage, the unique native dependency, aggregate read budgets, and the
candidate-only scientific limitations before exposing a campaign. The integrated
portable gate at revision `cf49714` passed 534 Python tests, Ruff check and format,
mypy over 133 source files, lock verification, one Alembic head, four frontend unit
tests, the production frontend build, and two isolated production-Chromium tests.
The exact post-soak runbook requires CALIBRATION/ACCEPTANCE tags, durable automatic
holds, legacy evidence before queueing, and suppresses the default Standard run for
those selected evidence lanes.

WP11 remains `IN PROGRESS`: no real centered-profile calibration campaign has yet
been promoted, none of the required 30 hardware sessions/40 streams has been
captured, and no authoritative matched-recovery campaign has therefore produced
the required statistical result. The bounded 40-stream orchestration fixture is
structural evidence only and is explicitly not production-acceptance evidence.

### WP10 — Qualification and production gate (`IN PROGRESS`)

Deliver:

- 24-hour acquisition soak;
- storage-pressure and fault-recovery campaign;
- full nightly/release corpus and Chromium run;
- operator runbook and measured capacity/worker tuning;
- final requirement traceability review.

Exit gate: every mandatory requirement below is `DONE`, no critical fault loses a committed held recording, and production acceptance gates pass.

Committed interim WP10 evidence includes the isolated storage-pressure/fault
campaign in
`docs/qualification/2026-08-19-isolated-storage-pressure-fault-campaign.md`,
the degraded RAID sizing baseline in
`docs/qualification/2026-08-19-raid-resync-capacity-baseline.md`, and the sealed
protected-corpus/Chromium release run in
`docs/qualification/2026-08-19-release-qualification.md`. WP10 remains
`IN PROGRESS`: the terminal soak, installed-unit restart/resume, final-six-hour
cohort calculation and drain, post-resync tuning, and final
traceability review are still mandatory.

The supported terminal runtime-continuity producer is now
`leo acquire capture-soak-runtime`: it reads the exact terminal systemd
invocation without changing it and publishes confined create-only evidence.
The active production soak is therefore still evidence-in-progress, not an
accepted result; its terminal document must be captured before the separate
restart/recovery exercise.

## 18. Exact acceptance gates

### 18.1 Database and migration gate

- One Alembic head and no ORM/schema drift.
- Empty-to-head and previous-release-to-head upgrades pass.
- Eight concurrent test workers never hold the same live job lease.
- Expired leases are reclaimed without duplicate logical products.
- Job attempts and failures remain inspectable.
- Old catalog rows and product metadata remain readable after migration.

### 18.2 Recording and storage gate

- CI16 round-trip is bit-exact for one/two RX and one/two radio sessions.
- Arbitrary reads crossing compressed shard boundaries return exact samples.
- Truncation, digest mismatch, bad layout, and continuity gaps are surfaced.
- Fault injection at every publication step exposes no partial bundle/product as committed.
- A bundle committed before a database outage is registered by reconciliation.
- A reconstructed catalog retains radio, profile, timing, pairing, calibration, and hash provenance.

### 18.3 Synchronization/acquisition gate

- Same-Pluto RX paths have identical declared sample counts/layout and pairing evidence.
- Dual-radio readiness and target release are exercised repeatedly on hardware.
- Requested start, actual start/end, skew, overlap, fraction, timing method, and uncertainty are persisted and displayed.
- Peer connection/device failure leaves a truthful partial session and does not discard the successful stream.
- Device/network/process faults do not create a falsely complete session.
- A 24-hour scheduled acquisition soak has no unexplained loss where continuity
  is observable, explicitly records non-observability otherwise, and has no
  unbounded memory/disk queue. Host buffer counts alone never prove device-side
  loss absence.
- The production soak sustains at least 50% sample-derived duty and no
  inter-capture gap exceeds 30 seconds. These external qualification thresholds
  apply even if the immutable harness policy has no corresponding field.
- After inherited jobs drain, soak-origin pending/leased jobs stay below 1,000
  and the worker service rate over the final six active hours is at least the
  soak job-arrival rate. Aggregate queue decline cannot mask cohort growth.

### 18.4 Processing/reprocessing gate

- Analyzers pass unit tests without filesystem or PostgreSQL access.
- Worker kill/lease expiry does not create duplicate visible products.
- Memory use is bounded with dwell length through streaming interfaces.
- `no_candidate` and partial coverage follow declared graph policy.
- Failed reprocessing leaves the former current run and UI unchanged.
- Successful reprocessing atomically switches summary and every visible product to one new run ID.
- Concurrent API reads observe only complete generations.

### 18.5 Detector and scientific gate

- Qin/template primitives match frozen numerical oracles.
- RETRO candidate epoch, CFO, pilot/QAM metrics, and candidate rank meet documented tolerances.
- J1 remains explicitly `UNAVAILABLE_HISTORICAL_EVIDENCE`; its exact expected
  identities and audit stay declared, it is never executed or counted as a
  pass, and no J1/calibrated-detection/specificity claim is made.
- The whole-dwell search retains multiple basins and finds the known basin even when it is not the first coarse rank.
- Injected positive, null, stationary-interferer, corrupted-input, and held-out control cases produce their documented outcomes.
- Candidate claims include search coverage, calibration, lineage, controls, and confidence distinct from compute tier.

#### Future calibrated-fixture gate (not yet adopted)

Receiver-calibrated capability will become a separate mandatory gate only
after an independently reviewed fixture revision freezes immutable raw dual-RX
IQ geometry and digest, radio/settings/timing provenance, per-receiver
calibration authority and digest, predeclared search coverage and tolerances,
and independent positive/null/stationary-interferer/wrong-pattern/surrogate
controls. The fixture must have a new identity and must not reuse J1's ID or
oracle values. A receiver frequency calibration may qualify frequency handling
and reproducible candidate behavior; a calibrated detection or specificity
claim additionally requires reviewed truth/negative evidence and a false-alarm
methodology. This future gate is not currently instantiated and is not a
dependency of the present candidate-only production gate.

The mandatory WP11 frequency calibration and matched candidate-recovery gate
does not instantiate this future calibrated-*detection* fixture. It qualifies
frequency handling and noninferior reproduction of the historical candidate
behavior on identical IQ; it still makes no specificity or attribution claim.

### 18.5A CH4-lower single-RX matched-recovery gate

- One profile revision selects exactly RX1, 2.5 MS/s, 2.5 MHz bandwidth,
  60 seconds, CH4 lower, and 40 dB manual gain on both radios.
- Ten independent sessions per radio contain exactly 150,000,000 CI16 samples
  on one receiver and make no synchronization or overlap claim.
- Ten paired sessions contain one complete stream per radio with the same
  geometry, at least 99% estimated overlap, explicit uncertainty, no phase
  coherence claim, and explicit device-loss non-observability where applicable.
- Every recording, calibration, legacy-oracle result, native result, and
  processing run is immutable, hashed, path-confined, retained, and linked in
  one sealed campaign receipt.
- Calibration identity includes radio serial, physical RX/path, hardware epoch,
  center, uncertainty, validity, evidence URI and digest. Missing, expired, or
  mismatched calibration makes the scientific result `INSUFFICIENT`; an
  implicit zero center is never acceptance eligible.
- Each complete stream schedules exactly 600 windows of 25,000 samples at a
  250,000-sample cadence. Missing windows remain in the denominator and no
  candidate budget may truncate the acceptance inventory.
- Legacy and native kernels run independently on identical IQ and retain
  `n11`, `n10`, `n01`, `n00`, recovered epoch/CFO deltas, QAM accuracy/EVM,
  calibration and window lineage.
- Every radio/mode stratum has at least 30 legacy-positive windows or is
  explicitly `INCONCLUSIVE`; native recovery is at least 90% and its one-sided
  95% lower bound is at least 80%.
- Recovered basins agree within 8 circular epoch samples and 500 Hz CFO. Every
  capture with a legacy QAM-positive window has a native QAM-positive window;
  that gate is accuracy at least 60% and RMS EVM at most 1.25.
- The paired native-minus-legacy hard-symbol-accuracy lower 95% bound is at
  least `-0.05`; identical epoch/CFO kernel parity retains the stricter frozen
  RETRO numerical tolerances.
- CLI and read-only UI expose both algorithms' rates, exposure, confidence
  bounds, calibration and candidate-only status. No result is called payload
  decode, calibrated detection, specificity, attribution, or cross-radio
  coherent combination.

### 18.6 Retention gate

- At 70% synthetic utilization, reclamation starts and stops at or below 65%.
- 75% warning and 80% admission-stop behavior are deterministic.
- Held and TEST sessions survive every automatic retention test.
- Active jobs, current protected products, and paired session members cannot be orphaned.
- Tombstones and searchable summaries survive raw/large-artifact purge.
- All destructive tests operate on generated isolated data and prove path confinement below `/srv/bulk/leo`.
- No QNAP deletion API, command, or resolver exists.

### 18.7 CLI/API/browser gate

- CLI human and `--json` views agree on identity and values.
- CLI and HTTP expose the same current run, paths, profile, power, Starlink, QAM, Doppler, coverage, TEST, and hold state.
- HTTP exposes GET/HEAD only for project routes and cannot acquire, reprocess, pin, purge, or delete.
- Playwright verifies search, TEST filtering/badges, session detail, overlap, paths, power, waterfall, overlays, provenance, partial/failure/no-result states, and post-reprocessing replacement.
- Main-branch E2E ingests through the real catalog/workers; it is not a static mock-only demonstration.

### 18.8 Production gate

- All preceding gates pass.
- A 24-hour acquisition soak and a full 60-second detector corpus run pass on the target host.
- Capture remains healthy with a deliberately induced processing backlog.
- Service restarts recover committed bundles, expired jobs, and current-run state.
- Storage and worker capacity measurements are recorded and operational thresholds are configured from those measurements.

## 19. Requirement checklist

Every row is initially `PENDING`. A row becomes `DONE` only when its referenced acceptance evidence is committed and reproducible.

| ID | Requirement | Acceptance evidence | Status |
|---|---|---|---|
| R-001 | Fresh modular implementation in `leo-tracker-reduxredux` with no legacy compatibility obligation | WP0 architecture/module contract review | DONE |
| R-002 | Support one or two Ethernet Pluto+ radios | WP3 transport and hardware canary | DONE |
| R-003 | Support one or two RX paths per Pluto+ | CI16 paired-layout and hardware tests | DONE |
| R-004 | Best-effort synchronized mode maximizes and measures overlap without coherence claims | Synchronization gate | DONE |
| R-005 | Capture parameters and dwell/sample-rate experiments require no code change | Revisioned profile contract and CLI tests | DONE |
| R-006 | Acquisition can approach 100% duty while processing remains decoupled | 24-hour soak and induced-backlog test | PENDING |
| R-007 | Raw IQ is compressed, immutable, independently chunked, and self-describing | Storage gate and reconstruction test | DONE |
| R-008 | Exact radio/settings/times/pairing/calibration/continuity metadata is retained | Manifest schema and reconstruction assertions | DONE |
| R-009 | Live IQ and analysis reside on `/srv/bulk/leo` | URI/path configuration integration test | DONE |
| R-010 | QNAP is copy-only and never automatically modified or deleted | Static/API review plus retention confinement test | DONE |
| R-011 | PostgreSQL is the robust catalog and processing queue | WP1 integration/concurrency suite | DONE |
| R-012 | Alembic supports frequent reviewed migrations without automatic back-processing | Migration gate | DONE |
| R-013 | Analysis artifacts are immutable, versioned, hashed, and stored on `/srv/bulk` | Product publication/fault tests | DONE |
| R-014 | Scientific artifacts and stable UI presentation products are separate | Presentation contract tests | DONE |
| R-015 | Analyzer modules are independently testable and infrastructure-blind | Analyzer fake-boundary tests | DONE |
| R-016 | Processing handles new captures and explicit existing-data re-ingestion | Vertical-slice and reprocess tests | DONE |
| R-017 | Reprocessing replaces visible analysis atomically and preserves last good output on failure | Reprocessing gate | DONE |
| R-018 | Reproducible historical detector/QAM numerical capability is recovered from available immutable evidence before novel optimization; J1 remains unavailable historical evidence | Fail-closed RETRO production parity lane plus ADR 0006 and the machine-validated J1 unavailability declaration | DONE |
| R-019 | Whole-dwell analysis retains multiple basins and includes Doppler, QAM, and controls | WP9 detector/scientific gate | DONE |
| R-020 | UI is read-only open HTTP on the LAN | Route audit and Playwright gate | DONE |
| R-021 | CLI has distinct acquisition and processing areas with human and JSON output | CLI contract/integration tests | DONE |
| R-022 | UI and CLI expose paths, provenance, power, Starlink, QAM, Doppler, coverage, and state | Cross-interface assertion suite | DONE |
| R-023 | Playwright E2E validates a real browser against freshly ingested TEST data | Main/nightly Chromium artifacts | DONE |
| R-024 | Small real/control corpus is copied locally, immutable, tagged TEST, and held | Corpus manifest and retention tests | DONE |
| R-025 | Missing required real-data fixtures never silently skip | Fixture preflight failure test | DONE |
| R-026 | Automatic retention starts at 70%, targets 65%, warns at 75%, and stops admission at 80% when blocked | Retention threshold suite | DONE |
| R-027 | Held recordings are never automatically deleted | Hold concurrency/destructive suite | DONE |
| R-028 | Purged recordings retain searchable tombstones and small summaries | Retention/UI integration test | DONE |
| R-029 | Local RAID is sufficient; no second raw-data copy is required initially | Deployment configuration review | DONE |
| R-030 | Services deploy under systemd with acquisition protected from worker load | Soak, restart, and resource-weight tests | PENDING |
| R-031 | Committed filesystem data survives database/service crashes and is reconciled | Crash/reconciliation campaign | DONE |
| R-032 | Final system passes the complete production gate on the dedicated host | WP10 qualification report | PENDING |
| R-033 | Each Pluto+ independently records an exact CH4-lower 60-second single-RX dwell that enters the normal workflow | WP11 independent hardware manifests, digests, runs, CLI and UI evidence | PENDING |
| R-034 | Both Pluto+ radios record the same CH4-lower single-RX arm under honest best-effort synchronized release | WP11 paired hardware manifests with at least 99% estimated overlap and explicit uncertainty | PENDING |
| R-035 | Native pilot/QAM candidate recovery on the new 60-second arm is noninferior to the pinned `leo-tracker` oracle on identical IQ | WP11 matched 600-window statistical campaign receipt | PENDING |

## 20. Change control

Changes to an invariant, destructive behavior, synchronization claim, storage root, raw encoding, promotion semantics, or web mutation boundary require:

1. a written architecture decision record;
2. explicit review of failure and migration behavior;
3. an updated acceptance gate and requirement trace;
4. tests landed before the changed behavior is enabled.

Research analyzers and product schemas may evolve rapidly within these boundaries. The purpose of the platform is to make that evolution safe without repeatedly redesigning acquisition, storage, catalog, retention, or the browser contract.

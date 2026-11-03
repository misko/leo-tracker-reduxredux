# Native ARM completion audit v1

This audit covers only the native ARM plan in `plan.md` before the original
server architecture heading. It maps the plan's existing gates to retained
evidence; it does not change a gate or treat an installation as scientific or
real-time acceptance.

## Verdict

The native goal remains **incomplete**. The requested firmware is installed and
attested, the native component boundaries are largely implemented and tested,
and portable and server-support-profile applications are installed as
versioned, non-autostart artifacts. The open gates are full detector recovery
and scientific parity, lossless continuous capture with analysis, five-second
warm-location freshness, an exercised 600-second history, continuous regional
search qualification, and physical Pi/USB qualification. The plan's
reference-search gate permits explicit budget exhaustion; global mathematical
convergence is not an additional completion requirement.

Status terms below have narrow meanings:

- **Complete/deployed** means the named component or artifact passed its stated
  tests and, where stated, is installed. It does not close downstream gates.
- **Partial** means a real boundary was exercised but the plan's full gate was
  not met.
- **Open** means retained evidence explicitly fails the gate or omits a required
  scope.

Scope correction: the original C4 component gate requires reconstruction of
membership, support and partitions, and the delivery checklist marks it complete
with the six solver-dependent duplicate identities documented. Exact reproduction
of those six frozen-v1 candidate and tracklet IDs is useful compatibility evidence,
but it is not an additional native completion prerequisite. Likewise, five seconds
is the warm-location freshness target; cold discovery, reacquisition and the other
regional-streaming cases remain separately qualified C7 behavior. This correction
changes no numerical result, fixture or tolerance, and does not relax the mandatory
C1-C3 scientific-parity or E1-E4 gates.

## Gate map

| Plan gate | Authoritative evidence | Audit status | Exact evidence still missing |
|---|---|---|---|
| Exact PPU 0.59 firmware on `192.168.1.15` | The [artifact binding](../firmware/artifact-binding.json) identifies `v0.59-plutoplus-spf-dual-rx-counter-fix`, DFU SHA-256 `1fa69d2784efbcabaaaed5bc5f5d625deabfd7da725627c9634a694db5bd9df0`. The supported LAN flash [succeeded](../firmware/flash-receipt.json), and [postboot attestation](../firmware/postboot-attestation.json) records the expected firmware, serial and protocol-v3 capabilities. | **Complete/deployed** | None for the firmware gate. This evidence makes no detector, numerical, or real-time claim. |
| Native component and application availability | C0 fixtures, C4-C6, C8-C10, local/source-neutral scanner paths and bounded execution have component receipts. The portable application is installed through the [support-port deployment](support-port-v1/deployment.json). The exact support profile is separately installed through the [profiled companion deployment](profiled-companion-v1/deployment.json); `live-current` remains portable, with RF and autostart disabled. | **Complete/deployed at component scope** | Downstream system gates below. A physical lifecycle or saved-input replay is not capture-concurrent qualification. |
| C1-C3 fractional observation and full detector recovery parity | The [corrected full host replay](../ds9/corrected-full-replay-v1/README.md) passes all 2,215 visits, 35,440 retained candidates and 24,681 gate decisions, with exactly 11,747 passing detections. One corrected physical ARM dwell also passes. The ordinary deployed detector is a different, lower-recovery algorithm. | **Corrected host science passes; production/ARM coverage open** | Full-corpus ARM verification and integration of the corrected detector into the application remain outstanding. The corrected wideband ARM call costs 55.30 seconds baseline, 50.29 seconds with exact-rounding research, against 120 ms of samples. The earlier narrow-band timings do not describe this corrected DS9 workload. |
| C4 track reconstruction and exact-v1 identity limitation | The named support profile reproduces all 11,747 support numerics and decimal lexemes; the deferred Session path reproduces all 58 membership-comparable track authority records on physical ARM in the [Session receipt](../runtime/session-deferred-physical-v1/receipt.json). C4 reconstructs all 64 physical memberships. The [duplicate-tie audit](../tracking/c4-duplicate-tie-audit/receipt.json) records six candidate-ID and tracklet-ID differences caused by one/two-ULP DGELSD duplicate choices, with zero source-membership mismatches. | **C4 component complete; exact-v1 limitation documented** | No additional C4 component evidence is required by the original gate. The mandatory E3 comparison must still propagate fresh detector authority through location and keep the six exact-v1 differences visible. Exact frozen-v1 identity would require the pinned numerical path, or a new versioned tie policy and explicit golden review; neither is a native completion prerequisite. |
| E1-E4 coverage | The corrected full host path preserves all 64 physical track memberships and 3,372 alias indices from fresh detections. Its native partitions and some location results differ from the cached server artifact. Fresh-native [ARM tracking](../tracking/corrected-native-arm-v1/README.md) and [two-site scoring](../location/corrected-native-arm-v1/README.md) each reproduce host output byte-for-byte. E4 saved-event replays preserve observations but omit raw-IQ detection and RF contention. | **Partial** | One coherent ARM composition must cover raw IQ through candidates, observations, tracks, partitions, regional search and final coordinates, plus independently paced scheduling. The separate tracking and score fixtures do not substitute for that composition or resolve native/server partition differences. |
| Lossless continuous capture plus analysis throughput | The [live qualification](../live-qualification/qualification.json) records 3,468 intact visits in the 585-second run, zero missing samples, and four detector queue drops; `lossless_analysis_pass` is false. The final four-slot build has a clean 60-second run with 350/350 analyzed visits. Saved-candidate Analysis replays exclude detector and RF contention. | **Open** | A long run of the final composition with no missing samples, queue drops, capacity evictions or growing backlog, including detector, projection, tracking and location work under the same resource budget. No new RF run is currently useful while the exact detector exceeds its 120 ms arrival budget; any future RF closure requires a new bounded user authorization because the prior 26-minute campaign is closed. |
| Five-second warm location freshness | The latest [sidecar application ARM pair](sidecar-workspace-release-v1/physical-paced-pair.json) spans 299.802 seconds and preserves 11,747 observations and 64 tracks without drops. Cache off services 31/59 requests; experimental cache on services 40/59. Maximum result source age is respectively 20.401 and 14.241 seconds. Both exit 4 for failed freshness; deployed cache remains off. | **Open, measured failure** | A capture-concurrent ARM run must demonstrate provenance-bound warm location updates no older than five seconds, with bounded queues and missed requests reported. This saved-event test excludes detection and RF contention. Cold discovery, wrong hypotheses, reacquisition, expiry and TLE replacement remain separate C7 cases; the plan does not require full regional rediscovery for every five-second request. |
| 600-second causal history | The application exposes a 600-second/96-by-10-second-knot development profile, and physical orbit storage/coverage feasibility is established. The full paced receipt explicitly records only 299.802 seconds of source evidence and `full_600_second_evidence_span_exercised=false`; the real support-profile replay has the same limit. | **Open** | At least 600 seconds of causal evidence must exercise retention, expiry, late evidence, capacity accounting, orbit coverage and publication/search behavior without loss. Merely configuring a 600-second window or allocating its orbit cache does not satisfy this gate. |
| C7 regional search and streaming qualification | On frozen reference inputs, both original 400-point host searches reproduce ordered inventories, scores and incumbents in the [C7 receipt](../location/c7-reference-search-v2/receipt.json), with budget exhaustion explicit. The [corrected fresh-native host searches](../ds9/corrected-full-replay-v1/full-public-c3-c4/c7-search/summary.json) also exhaust 400-point budgets: Sacramento has the same incumbent; Reno differs. Physical ARM fresh-native evidence currently covers two fixed sites, not these regional searches. | **Reference regression complete; ARM streaming open** | A budgeted regional search over fresh detector-derived authority must be qualified on ARM with capture contention, result-age limits, cold discovery, wrong hypotheses, reacquisition, expiry and TLE replacement. Budget exhaustion must remain visible. The plan does not require proving global convergence beyond the reference search policy. |
| Pi platform qualification | The [USB qualification](../usb/qualification.json) passes host and sanitizer tests, ARM cross-build, optional SoapySDR 0.8 compilation, fake-provider lifecycle, and a Pluto CPU-only saved-IQ replay. It explicitly records no USB hardware/RF use, no specified USB model, no exact hardware counter, unbounded timestamp uncertainty and no attested coherent dual RX. | **Open; external hardware dependency** | The user must select and provide the Pi/USB SDR model and configuration. That physical source then needs capability, ownership/restoration, discontinuity, timestamp uncertainty, receiver topology and workload performance qualification. Software-ordinal evidence cannot be promoted to coherent-counter authority. |

## Completion boundary

The retained evidence supports shipping and reviewing individual native
components and the versioned diagnostic applications. It does not support a
claim that the full adaptive native application has achieved server-equivalent
IQ recovery and observation science, continuous lossless operation, five-second
warm location updates, a fully exercised 600-second history, continuous regional
search under the declared budget, or Pi hardware support.

After this audit, the [tracking predicate release](tracking-predicate-release-v1/deployment.json)
became the portable default, retaining its predecessor. The corrected
[one-site ARM cache test](../online/exact-score-cache-v1/physical-receipt.json)
also passed after the diagnostic's simultaneous-coordinator OOM was fixed.
Neither result closes the system gates above; the default application does not
enable the experimental cache.

The subsequent [integrated cache ARM pair](exact-score-cache-integration-v1/physical-receipt.json)
preserves identical final scores and lossless observations at original pace.
Cache-on reduces missed cadence from 30 to 23 of 59 and post-producer processing
from 33.030 to 18.713 seconds. Both runs still exit 4 for freshness failure;
their fixed-site saved-event scope does not close capture, detector, regional,
or 600-second evidence gates. The default release remains unchanged.

The subsequent [rank-copy deployment](one-per-source-rank-release-v1/deployment.json)
activates `fce5af960f9eba87`, retaining `2a01927d03040337`. Complete host DS9
science and physical lifecycle tests pass after a coherent rebuild. The exact
rank optimization reduces standalone single-worker ARM tracking by 7.03% in
the retained ABBA comparison. This is not a new application freshness result;
the system gates remain open and the experimental score cache stays disabled.

The later [source-key-view release](source-key-view-release-v1/deployment.json)
activates `f51b826eeeebdb23`, retaining `fce5af960f9eba87`. The coherent build
passes complete host saved-event science and physical ARM lifecycle tests.
Its isolated tracking ABBA comparison reduces final warm reconstruction by
6.51%, with complete output unchanged on host and ARM and all 60 host causal
prefixes exact. This remains a component timing result; capture-concurrent
application freshness has not been requalified and the cache remains disabled.

The [corrected eight-visit detector diagnostic](../ds9/receiver-authority-ablation-v1/wideband-research/retention-audit-v1/qualification.json)
resolves the selected missing-RX0 discrepancy by using the recording-derived
-312.5 kHz receiver center. The maintained server reproduces the compared
integer epoch, gate and five fractional fields on all 43 persisted rows,
matched by rank; IDs, support timestamps and moments were not compared here.
All 43 gate decisions match (23 pass, 20 fail). The isolated wideband native wrapper matches all 64
retained candidates within the original tolerances, recovering 23/23 passing
detections. This selected sample does not replace the open full-corpus and
real-time detector gates above. The initial zero-center run remains retained as
an incorrect-geometry diagnostic. RF/channel/edge authority comes from persisted
projection rows; the retained capture manifest binds raw hashes and counters.
The original input manifest is only hash-referenced in the available evidence.

The user has named RTL-SDR as the first intended Pi SDR family. The exact
dongle variant and Pi endpoint remain unspecified. The subsequent
[single-receiver DS9 source regression](../usb/single-rx-ds9-v1/README.md)
passes host, sanitizer and physical ARM CPU tests for both isolated channels;
it does not qualify RTL-SDR hardware, capture timing or the downstream detector.

The later [single-receiver detector qualification](../usb/single-rx-detector-v1/README.md)
does qualify detector equivalence to the corresponding ordinary dual-receiver
channel on all 80 saved DS9 dwells, in ordinary and fractional modes, on host,
under sanitizers, and on physical PLUTO+ CPU. This is ordinary-detector
equivalence, not server recovery parity or full single-receiver application
qualification. The [USB source-port adapter](../usb/source-port-v1/README.md)
also passes host, sanitizer and physical ARM CPU tests. Its valid-retune-boundary
requirement remains unmet by the generic Soapy provider; the
[RTL-SDR audit](../usb/rtl-sdr-retune-audit-v1.md) identifies hidden reset errors
and an unmeasured settling interval that require qualification on selected
hardware.

The immediate external dependencies are selection and availability of the Pi
and specific USB SDR hardware, and a genuine continuous recording with at least 600
seconds of qualified causal evidence. The bounded
[history-corpus inventory](history-corpus-inventory-v1.md) found no such
recording among 2,205 finalized adaptive manifests; its longest attested span is
300.1272296 seconds, while 98 directories without a parseable finalized
manifest remain explicitly unassessed. A future live-RF acceptance run also
needs renewed bounded authorization, but detector throughput is already an
independent prerequisite. No additional firmware action is required. The six
C4 exact-v1 identity differences remain preserved compatibility evidence, not
an external dependency or a whole-goal completion prerequisite.

The latest deployed application is `applications/bdec8f78923ee41d`, incorporating
the qualified dense-sidecar tracker. The full host saved-event result remains
11,747 observations and 64 tracks with the prior score and zero drops; physical
ARM lifecycle checks pass. Previous `f51b826eeeebdb23` remains available.
See [activation evidence](sidecar-workspace-release-v1/activation.log). Its
paced cache-off application check now preserves all observations/tracks and
reference score with zero drops, but fails freshness: 31/59 publication requests
serviced, 28 missed, maximum publication computation 13.057 seconds. The serial
cache-on experiment also preserves final science and zero drops but services
40/59 requests with 19 misses; maximum publication computation is 13.089 seconds.
Both exit 4 for failed freshness. No RF or autostart was enabled, and the
deployed cache default remains off.

The corrected detector now has [one-dwell physical ARM evidence](../detector/corrected-wideband-arm-v1/README.md):
all 16 retained candidates match the corrected host wrapper within the frozen
tolerances, including all 12 complete-candidate gates (seven pass). It takes
55.300 seconds for a 120 ms dwell, so detector real-time qualification fails by
a wide margin on this measurement. The broader 2,215-visit corrected detector
replay now passes on the host: 35,440 retained candidates, 24,681 rank-level
gate decisions, and exactly 11,747 passing detections match the reference
within the frozen comparator. All 2,215 visit receipts pass; wall time is
1,419.47 seconds with four workers. See the [full summary](../ds9/corrected-full-replay-v1/full-output/summary.json).
It is not a full-corpus ARM throughput test, ordinary production-detector
qualification. The [fresh-native downstream host comparison](../ds9/corrected-full-replay-v1/README.md)
reconstructs all 64 physical track memberships and support bounds, with 3,372
matching alias indices. Location equivalence remains open: native provenance
and support serialization change partitions; satellite winners agree on 60/64
tracks at each registered site, and the 400-point Reno search has a different
incumbent. Both regional searches exhaust their budget without convergence.
These findings leave the original full-pipeline
and continuous capture acceptance gates open.

The subsequent research-only [exact-rounding ARM comparison](../detector/corrected-wideband-nextup-research-v1/physical-comparison.json)
preserves all non-timing row fields and numeric lexemes across two control and
two candidate runs. Mean detector call time improves from 55.291 to 50.287
seconds (9.05%) on the same saved dwell. This remains about 419 times its
120 ms sample duration and does not change the deployed detector or close a
real-time gate.

The recorded-plan integration now has a final physical ARM scanner test
([receipt](../scanner/recorded-plan-v1/physical-final3.time.json),
[installed hash](../scanner/recorded-plan-v1/physical-final3.log)). The final
`c635bb61` test executable exits zero in 2.899538542 seconds. Its component
coverage includes twenty saved visits through a queue of capacity one with a
delayed test detector and no drops. Recorded execution drains after each visit;
the adaptive live path remains asynchronous. This prevents artificial replay
queue loss, but establishes neither corrected-detector throughput nor RF cadence.
The [recorded DS9 exporter/provider](recorded-ds9-composition-v1/README.md)
has host and sanitizer qualification on original visit 301 and metadata for the
frozen 32-visit panel. Its final source-provider ARM unit test and actual
visit-301 raw-file traversal also pass (0.009506 and 0.571832 seconds whole
process respectively). The strict bundle-reader ARM unit suite passes after a
test-only correction for `/var/tmp` resolving to `/tmp`; the prior assertion
failure is retained as rejected evidence. The complete recorded raw-IQ-to-Analysis application is
still being integrated; these component receipts do not close its E2E gate.

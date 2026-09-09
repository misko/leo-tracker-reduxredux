# Adaptive scanner: real provider and host integration

2026-09-09. **Provider-to-host integration now works offline, including complete
300-second source spans. The production adaptive scanner is not yet deployed or
complete.** No radio, RF, production service, flashed firmware, FPGA or kernel
was accessed or changed for this checkpoint.

## Outcome

The actual userspace metadata provider now admits explicit adaptive V2 requests,
feeds real numerical-worker observations into the native scheduler policy, and
returns source-attested decisions and terminal inventory. The host reconstructs
the actual dual-RX visits through the ordinary TCP/libiio backend and preserves
settings restoration and detector-result delivery.

This closes the provider/host transport and lifecycle gap in the
[native checkpoint](2026_09_09_adaptive_hop_v2_checkpoint.md). It does **not** close
the application's immutable V2 capture/publication/analysis adapters or UI.
Those must use the new actual-visit model; passing it to the existing fixed V1
capture writer would be incorrect.

Local implementation revisions:

- libiio `42762db3e4a42901c7b9869a3d0d6be7c1147745`.
- PPU `2361ea11ce00d049ec911710fbcf02b86731da30`, after merging remote main at
  `d05e718` without conflicts. That merge retains the independent finite-pilot,
  PSS cleanup and paired source-support updates.
- Leo's companion V2-aware classifier port and component/integration tests are
  included with this report. The evidence index retains their exact source hashes.

No push, remote merge or production deployment occurred at this checkpoint.

## Provider and scheduler

`IIOD_SCANNER_ADAPTIVE_HOP` defaults OFF. Enabling it requires the positive-only
SDK profile and userspace device provider; the unchanged kernel provider is
rejected at configuration. Only the explicit opt-in build advertises adaptive
request/event/status V2 and the pinned policy. Runtime admission requires the
policy generation to equal the GLRT generation and the complete pinned settings.
Malformed settings are rejected before sampler setup or register writes.

The existing userspace factory validates all eight volatile profile CRCs and
creates the V2 scheduler with narrow choose/commit callbacks. The acquisition
owner alone copies SDK observations into the bounded feedback queue. The hop
thread never waits for GLRT, calls the worker, or owns IQ. Shutdown stops the hop
thread, releases the device and SDK, and only then frees its referenced policy.

The policy remains: three uniform startup visits per target; immediate positive
promotion; three consecutive evaluated misses **and** two seconds since the
last positive source-dwell end before demotion; 3:1 active/quiet weighting;
nominal three-second exploration; unhealthy-feedback fallback to equal scanning.
Unknowns are not misses. A bounded detector miss is never published as a proven
absence of Starlink. Dwell/rate/IF/bandwidth/guard settings and dual-RX recording
are unchanged; classification is RX1-only.

## Host reconstruction and lifecycle

New explicit codecs reject V1/V2 confusion. `AdaptiveHopStreamV2` verifies stream
generation, cross-block counters, sequential actual event IDs/visits, requested
tuning and guards, source-time decision order, complete sample coverage and
terminal accounting. It retains one dwell plus two permitted event-lag blocks
and one boundary refill; missing event delivery beyond that bound fails closed.
Metadata history is bounded by the requested maximum of 2,500 visits.

Each visit retains its actual event, profile and separate decision/proposal.
There is deliberately no synthetic sweep index. Shadow proposals never change
the labels or source intervals of the IQ actually received. Both receivers are
reconstructed exactly; source counters above 2**53 remain integers and GLRT's
fractional offset remains a separate unchanged field.

Only an attested next transition or completed terminal status closes a full
dwell. Cancellation retains all delivered decisions and distinguishes complete
valid IQ, invalid transition time, unclassified tail time and its unreceived
suffix. Partial time is not counted as a full dwell. Duty counts two receivers
once, using source-counter elapsed time; it is not detector CPU time.

The explicit adaptive client/backend reuses serial and physical-LAN admission,
bufferless profile preparation, clock brackets, raw metadata capture and exact
host settings restoration. Missing/incompatible detector negotiation refuses
the request before OPEN rather than producing a mislabeled fixed recording.
During an admitted capture, detector-reporting faults are advisory: IQ continues.
Source corruption instead fails capture validation, cancels and cleans up, and
cannot manufacture a successful receipt.

## Verification

| Lane | Result | What it proves |
| --- | ---: | --- |
| PPU | 804 passed | V2 codecs, reconstruction, lifecycle/admission, fixed V1 regression and merged pilot/PSS/source-support tests |
| Leo | 517 passed | Pure policy, V2-aware classifier admission, source/result binding, existing runtime/publication/API regressions |
| Build configuration | 20 passed | Default-off, positive-profile/userspace prerequisites and configuration rejection |
| Actual adaptive TCP | 22 passed | Raw V2 and complete client/backend paths, both rates/modes, full 300 s counter spans, cancellation and injected reporting/source faults |
| Legacy actual TCP | 16 per profile, 32 total | Fresh default/unqualified and positive-only builds still retain fixed V1 behavior |
| Sanitized provider | Passed | Actual provider/SDK/worker/feedback composition with synthetic positives, both rates/modes, cancellation and detector-failure fallback |
| Sanitized native/platform tests | Seven targets passed | Factory preflight/restore intent, old/new wire/session/scheduler, policy adapter and threaded handoff |
| Changed Python modules | Ruff and Python-3.12 strict type checking passed | Five PPU source modules; no dependency/type-target changes to the project |

The native adapter repeats 458,752 activity-mask decisions and 4,000 threaded
decisions. The provider sanitizer instruments libiio/provider code; its SDK and
worker use the unchanged separately built artifacts, not newly instrumented
copies. Prior SDK-specific sanitizer evidence remains a separate checkpoint.

### Three distinct evidence scopes

1. **Paced provider with synthetic pilots:** the real numerical worker and
   feedback policy run; radio recall receipts are substituted. At each rate,
   shadow and adaptive runs each complete 34 visits, with 13 and 15 positives
   respectively and ten weighted decisions. An injected detector failure still
   completes 34 visits and retains all results, with 30 fallback decisions.
   This small synthetic comparison is not a measured RF sensitivity gain.
2. **Threaded native scheduler tests:** real scheduler/policy/session threads
   run against synthetic IO/observations. They test concurrency separately from
   the provider fixture's substituted hardware scheduler.
3. **Actual TCP/client tests:** zero RX1 and constant RX0 travel through the real
   provider, server, TCP binding, backend, stream consumer and classifier port.
   Four full-duration cases cover 2.5/5 MS/s × shadow/adaptive, with accelerated
   counters and incremental IQ disposal. These are not paced 300 s ARM runs,
   positive-RF network qualification or measurements of live acquisition duty.

The [evidence index](evidence/2026_09_09_adaptive_provider_host/index.json) retains
JUnit results, per-case counter-span properties, commands, source/artifact
hashes, generated pilot manifests and failed attempts. It contains no IQ or
executables. Raw artifacts remain under `/tmp/leo-adaptive-provider.nZDbhN`.

## Failures found and retained

- A new corruption test exposed that the existing shared backend refined the
  first-sample clock bracket before comparing HOPS against the ABI-3 counter
  header. Binding validation now precedes clock refinement. The first run had
  one failure and 514 passes; the corrected subset passes 515, included in the
  final 804-test run.
- The first V2 classifier unit fixture advertised a two-result inventory then
  lowered it to one in its final frame; the reader correctly refused it. Another
  fixture omitted the V1 helper's required retention argument. Correcting those
  synthetic fixtures yields 64 passing classifier/frame tests, included in the
  final Leo lane. No scientific threshold, tolerance or golden data changed.
- The shared environment's NumPy stubs cannot be parsed under the project's
  Python-3.11 type-check target. Checking with the actual Python-3.12 interpreter
  target exposed two local typing errors, both fixed. Strict 3.12 checking
  passes; no fresh 3.11 compatibility pass is claimed and dependency pins are
  unchanged. Initial formatting diagnostics were also corrected.
- The existing Starlette/httpx deprecation warning remains visible in the Leo
  test receipt; it is not represented as a test failure or hidden.

## Remaining work for the full requested outcome

1. Add Leo-owned immutable adaptive capture/publication contracts, storage and
   runtime adapter, plus actual-time analysis and activity/cooldown/allocation UI.
   Retain strict old/new recording compatibility and separate advisory results.
2. Qualify the frozen detector and scheduling operating point on held-out saved
   IQ. Historical data cannot supply detections for unsampled hypothetical visits.
3. Build/package and run the **exact new integrated build** under paced 300 s
   ARM producer load at both rates. Old SDK timing is not qualification for this
   changed provider/client. Verify every-dwell throughput, callback deadlines,
   bounded backlog and unchanged acquisition geometry.
4. After separately authorized bounded live canaries, verify counter-based duty,
   physical settings, original IQ/result inventory, publication/UI and cleanup.
   Use only an admitted spare over its physical `192.168.1.*` interface, preserve
   all exclusions, and do not displace production or exceed the RF time limit.
5. Review compatible releases, merge into the requested remote branches, deploy
   opt-in and verify operation and rollback. Keep the full goal open until these
   release and operational requirements are evidenced.

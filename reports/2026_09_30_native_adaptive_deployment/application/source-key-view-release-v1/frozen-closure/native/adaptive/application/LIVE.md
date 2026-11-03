# Opt-in local live composition

`leo-adaptive-live` composes the qualified local PLUTO source and preparation
lifecycle, timed scanner, detector, timing brackets, `Session`, online tracking,
orbit construction, and bounded location-search slices. Running it without
arguments only prints capabilities. It does not open a radio or detector and
cannot start acquisition without the literal `--capture` argument.

Live inference requires correct system UTC and a recent supplied TLE catalogue.
Establish UTC after boot, before starting capture; do not step the clock during
an active session. The target was found at January 1970 during deployment and
received a one-time host clock transfer while capture was idle. That transfer
does not qualify subsecond accuracy or persistence across reboot. Saved-data
tests use recorded timestamps and are unaffected. See
`reports/2026_09_30_native_adaptive_deployment/application/clock-precondition.json`.

The executable exposes two explicit development profiles. Ten-second history
uses 32 one-second Hermite knots; 600-second history uses 96 ten-second knots.
Both use the full supplied TLE catalogue and never create a shortlist. The
orbit window includes the retained track interval, configured score tau
endpoints, and one interpolation knot at each end. Evidence outside the exact
window fails instead of silently coarsening knots. The 600-second option is a
full-history development path; it is not a global interpolation or full-system
qualification claim.

The worker-aware capability and telemetry shapes use
`leo-native-live-capabilities/v4` and `leo-native-live-summary/v4`. Version 4
adds the configured CPU concurrency cap and detector/analysis worker counts.
These counts do not claim CPU affinity or exclusive core reservation. The
published v3 contract remains associated with the preceding pinned-search
release, and earlier major shapes remain bound to their historical binaries.

The capture form requires every limit and authority explicitly:

```text
leo-adaptive-live --capture \
  --duration-ms N --maximum-visits N --active-dwell-ms 120|240|360 \
  --block-ms 20|120 --maximum-detector-latency-ms N \
  --cpu-workers N --detector-workers N --analysis-workers N \
  --publication-ms N --history-seconds 10|600 --generation N \
  --exact-template /absolute/file --control-template /absolute/file \
  --tle-catalogue /absolute/file \
  --input-digest sha256:... --analysis-digest sha256:... \
  --session-id ID --search-origin LAT LON \
  --search-radius-km R --search-region-km R --search-level-km R \
  --search-point-budget N --search-slice-points N \
  --target PROFILE FREQUENCY_HZ CHANNEL lower|upper ACTUAL_RF_HZ [...]
```

The live defaults are two total compute lanes, one detector worker, and one
analysis worker. Each count is bounded to one through four and detector plus
analysis workers must not exceed the declared total. The full budget is
validated before template loading, detector construction, provider creation,
or any radio operation.

Duration is capped at 30 minutes. The current radio geometry is fixed at two
receivers, 2.5 MS/s, 2.5 MHz bandwidth, 40 dB manual gain, and 16 kernel
buffers. Target profiles and receiver/channel/edge/RF authority remain fixed
for the process. Catalogue count is bounded to 20,000, search input is bounded,
and template/catalogue parsing happens before radio ownership or mutation. TLE
identity comes from matching line-1/line-2 catalogue fields and supports Space
Track Alpha-5; duplicate or inconsistent identities fail before provider use.

The timed scanner callback takes a fresh coherent source snapshot inside a
measured POSIX bracket immediately before each policy selection. The analysis
worker uses `utc_before - maximum_detector_latency` as its conservative quiet
frontier and never regresses the `Session` watermark. Detector latency must be
less than retained history. Result, failure, and candidate arrival are checked
from enqueue to application callback. This closes the scanner's
result-before-candidate ordering window fail-closed. Missing or unordered live
enqueue/start/finish monotonic telemetry is itself a qualification failure.

Detector contexts are constructed sequentially before source ownership. Their
capabilities must agree, and configurations are bound by a caller-attested
digest over the analysis digest, exact template bytes, control template bytes,
sample rate, and mode. Each scanner worker has one independent context. Partial
construction and every later exit destroy all contexts. This attestation binds
caller inputs; it is not introspection of private detector state.

Publication has consumed-prefix semantics. An accepted candidate delivered
after one publication may enter the next while it remains inside declared
latency and history. The worker drains accepted input before quiet advancement,
publishes periodically, and evaluates only the declared points per slice. If a
producer queues evidence in the narrow drain-to-watermark interval, advancement
is deferred and retried; it never holds the producer lock through tracking. A
successful publication updates the newest track snapshot. The live composition
opts into pinning a started search to its original snapshot while newer
publications coalesce into one pending search. After the active search finishes,
the newest pending snapshot starts; an orbit rebuild waits until then. Expiry,
stream replacement and orbit replacement still invalidate stale work. The
coordinator's default policy retains its historical invalidation behavior for
existing callers. Output binds the last result to snapshot and orbit
generations and reports convergence, budget, selected latitude/longitude,
east/north offset, MSE/RMSE, and matched/unmatched counts when an incumbent
exists.

`AnalysisConfig::analysis_workers` owns its tracking execution lifetime. One
worker preserves the serial path and creates no executor. Two through four
workers create the bounded tracking executor before `Session` and keep it alive
until after `Session` destruction. Supplying both an external tracking port and
more than one owned worker is rejected.

The analysis library also accepts explicit `caller_driven` execution. Its owner
calls `poll()` for one iteration; the production CLI uses the independent
background worker. `progress()` returns the last complete iteration safely from
another thread. This permits deterministic replay of publication/search
interleavings without timer-dependent tests. Final shutdown performs one final
iteration and reports pending or unconverged search work rather than silently
claiming that every published snapshot has a completed result.

Cadence uses fixed integer intervals from the first measured source bracket; it
does not drift by resetting from completion time. Telemetry preserves the
invariant `requests = serviced + misses + pending`. Publication compute time is
measured on the analysis owner. Snapshot and result ages are reported as lower
and upper bounds using the latest measured bracket's `utc_before` and
`utc_after`; the lateness-adjusted causal frontier is reported separately.
Snapshot-publication-start to completed-result monotonic duration exposes slow
tracking/orbit/search work even after source progress stops. A producer enqueue
race at publication is recorded as a retryable deferral, not an internal
publication failure, and the pending cadence request remains accounted.

Scanner queue drops, detector failures, callback-latency violations, incomplete
visits, missing samples, application queue drops, coordinator ingest rejects,
history-capacity evictions, publication failures, search failures, restoration
failures, or source errors make `capture_integrity_qualified` false and return
failure. `reduced_history_qualified` is emitted only for the 10-second profile;
the 600-second run is labeled `full_history_development_executed`. Quiet/no-track
publications are reported without fabricating a location result.
`full_standard_qualified` and `fractional_server_parity_qualified` remain false
for both development profiles and the installed fast detector.

Cleanup waits for any in-flight cancellation callback, stops and closes the RF
source, exits firmware scan ownership, restores radio geometry, gain modes,
buffers and Fast Lock state, and releases the owner before joining potentially
slow analysis. Scope guards cover exceptions and every return after ownership.

Builds require matching explicit online and timed-scanner artifacts:

```sh
LEO_ONLINE_LIBRARY=/path/to/online-build \
LEO_SCANNER_BUILD=/path/to/timed-scanner-build \
native/adaptive/application/build-live.sh host /tmp/leo-live-host
```

Modes are `host`, `sanitize`, and `arm`. Host and sanitizer builds run the core
Analysis test, injected executable-lifecycle test, and no-argument capability
command. Tests cover the default 2/1/1 budget, invalid and oversubscribed
budgets before side effects, partial detector-context cleanup, incompatible
multi-context capabilities, owned analysis-worker lifetime, external-port
conflicts, and exact radio restoration. They use no local IIO device, IQ,
hardware, or RF.

No live RF capture has been run or qualified by this component work.

## Installation runbook

Install a frozen ARM bundle beneath
`/mnt/glrtbench/native-adaptive/applications/<binary-sha>/` and point the
separate `/mnt/glrtbench/native-adaptive/live-current` symlink at that version.
The directory must contain
`leo-adaptive-live`, `libleo-adaptive-detector.so`, and the
`libleo-adaptive-detector.so.1` symlink. Installation does not enable a service
or run `--capture`. Verify only the capability path first:

```sh
/mnt/glrtbench/native-adaptive/live-current/leo-adaptive-live
```

Every capture command must supply absolute template and TLE paths plus current
digests and target authority. There is deliberately no historical TLE default.
The current known qualification limits include bounded search slices when the
budget is not exhausted and false full-standard/fractional-server-parity flags.
The 600-second option uses 96 ten-second knots and remains a development mode;
the CLI option alone does not qualify its timing, memory, or interpolation.
Any loss/failure counter in the summary keeps capture integrity false.

The 2026-09-30 physical ARM CPU replay over the complete 299.802-second saved
event span was lossless and reproduced the 64-track one-point score, but it did
not meet the requested five-second freshness bound. It serviced 17 of 59
cadence requests and missed 42. Publication compute reached 39.356 seconds,
snapshot-to-result time reached 56.724 seconds, and final drain took 91.357
seconds. All 17 started one-point searches completed; reconstruction at each
full-prefix publication is therefore the measured first bottleneck. This is a
preserved failed timing qualification, not evidence for relaxing the cadence.

The standalone exact per-lane weighted-Hough prefix-cache experiment has now
completed; production integration remains deferred because its measured warm
call still exceeds the deadline. It may append cached slope-bin indexes only when the previous
ordered candidate sequence is an exact prefix and lane, RF, reference, and
configuration are unchanged. Expiry, insertion or reordering, changed
authority, or a memory-cap breach must take the cold path. Acceptance requires
bit-exact cold/cached tracks at every saved five-second prefix, explicit
invalidation tests, a fixed memory bound, and a new physical publication-time
measurement. Caching completed lane results alone is not promising on this
fixture: 7.47 of eight lanes changed at an average five-second boundary.

The earlier deployed composition invalidated searches at each publication and
could also stall when a refinement batch exceeded the fixed point allowance.
The deployed update described above addresses that lifecycle with pinned
snapshots and resumable batches. A retained search must stay bound to its
snapshot and orbit generations, expire with its declared history, and report
its older provenance. The completed one-point physical replay does not qualify
location discovery over a larger search.

The current verified 2026-09-30 ARM release is installed at
`/mnt/glrtbench/native-adaptive/applications/d75596931e4598d5/`, with
`/mnt/glrtbench/native-adaptive/live-current` pointing to it. The prior
`30c1c262ef7fac78`, `8f787ab9ac716446`, `befd1a655a4fe908`, and `db4df528ef6c271e` checkpoints
remain installed for receipt reproducibility.
Neither installation enables a service or starts capture.
This release includes the source-neutral scanner engine through its local
adapter. Physical fake-provider tests cover ownership and failure cleanup;
they do not qualify a USB SDR or new live RF operation. The persistent tracking
prefix cache remains excluded: its measured ARM warm call takes 24.045 seconds.
The current release includes guarded exact bin-index acceleration and lane-local
exact fit caching, contiguous selected-point weights and peak-cutoff filtering
in cold reconstruction, measured at 27.857 seconds on the saved
full observation fixture. Optional fit-cache allocation failures fall back to
uncached fitting; component-owned fault-injection tests exercise recovery.
The prior `7f0aa67cbcd1b758`, `bc0ce529d530995f` and `4f298578c6022764` releases are retained. No continuous real-time claim
follows from this component speedup. Deployment evidence is in
`reports/2026_09_30_native_adaptive_deployment/application/peak-cutoff-deployment.json`.

The preceding `bc0ce529d530995f` composition passes a complete saved-candidate replay on
physical ARM at 5x recorded input speed with coalesced publication: 11,747
observations, 64 matched tracks, zero drops and reference RMSE agreement within
3.7e-13 Hz. Its final analysis drain still takes 57.12 seconds. A 100x overload
test dropped 71 observations and failed validation as intended. These runs
exercise neither raw IQ nor continuous publication deadlines; the full evidence
is in `reports/2026_09_30_native_adaptive_deployment/application/exact-fit-cache-replay-arm/receipt.json`.

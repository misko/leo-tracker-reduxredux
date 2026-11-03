# Native online coordinator

This component owns the portable online state boundary from projected
`leo::adaptive::Observation` values to immutable tracking/location snapshots.
It calls the public tracking, pipeline, orbit, score, and search APIs directly;
it has no Python, server, database, scanner, or device dependency.

Ingress is causal. The caller supplies a nondecreasing source-time watermark,
and an observation whose support ends after that watermark is rejected. UTC is
never inferred from callback arrival time. History is bounded by both count and
UTC span. Expiration can also be driven without a new candidate through
`advance_watermark()`. `derive_support_authority()` creates only the normalized fractional
support moments (`moment0=1`, `moment1=0`, plus the observation's moment2/3);
callers retaining the original decimal support authority may supply it directly.
No published winners, training masks, or location responses are ingested.

Publication is explicit so a caller can select a bounded cadence instead of
reconstructing on every observation. Each publication contains only observations
whose support ended at or before its watermark. It creates a new immutable
generation. Appends may coalesce while a search continues over the last
published prefix; a later publication, stream-generation replacement, or TLE
replacement invalidates that search. The coordinator is a single state owner
and is not a concurrent API.

`Config::tracking_execution` optionally borrows a synchronous tracking lane
dispatcher from the application. The default remains serial. The dispatcher
must finish every accepted callback before returning or throwing, and its
context must outlive the coordinator. Publication still merges lane results in
deterministic order. A dispatch failure returns `Status::error`, preserves the
previous immutable snapshot, and permits a subsequent publication retry. The
coordinator creates no worker pool; the application owns the total CPU budget.

`Config::publication_search_policy` defaults to that compatibility behavior.
The opt-in `pin_started_snapshot` policy holds the immutable snapshot used by
an active search while newer publications advance `current_snapshot()`. Search
results continue to name the pinned snapshot generation. Snapshot age expiry,
stream-generation replacement, TLE replacement, and explicit cancellation
still stop the search. The shared snapshot keeps its track records alive; TLE
replacement cancels before the new orbit snapshot becomes visible.

`resume_search(maximum_points)` retains the native adaptive search between calls
and never scores more than the supplied point budget. If the next deterministic
native batch does not fit, the result is `running_unconverged` and reports
`required_points`. Complete, cancelled, stale, unconverged, and error states are
distinct. Orbit epoch and pipeline session epoch must match, preventing a silent
relative-time shift.

In `pin_started_snapshot` mode, a native deterministic batch larger than the
caller's point budget is retained internally and scored over repeated calls.
Each call evaluates at most `maximum_points`; the coordinator submits the full
batch only after preserving its original point order. Default mode retains the
published whole-batch `required_points` behavior.

`compare_reference()` is a pure same-prefix diagnostic. Its output never enters
tracking, partitioning, scoring, or search.

Build and run the component tests with:

```sh
native/adaptive/online/build.sh host /tmp/leo-online-host
native/adaptive/online/build.sh sanitize /tmp/leo-online-sanitize
native/adaptive/online/build.sh arm /tmp/leo-online-arm
```

When another component is changing tracking or location sources concurrently,
`LEO_ONLINE_BASE_LIBRARY=/path/to/libleoonline.a` reuses the matching qualified
tracking, pipeline, orbit, score, search, and SGP4 objects and rebuilds only the
online coordinator plus its tests. The receipt must bind that base archive.

Host and sanitizer builds run lifecycle tests and a real DS9 causal-prefix test:
492 freshly native complete-scan candidates produce 11 native tracks and flow
through the public pipeline. The replay builds all 11,129 supplied TLEs. It
compares a five-point uninterrupted search with repeated one-point slices while
a newer snapshot is published, and separately compares the original one-point
result and all aggregate score/stat fields with the public scoring ABI. This
proves the coordinator path and deterministic pinned-prefix behavior; it is not
a location-accuracy claim. ARM builds create the library and both test
executables without running target code.

The DS9 test also publishes the same prefix with two workers completing lanes
in reverse order and requires exact tracking, support digests, partition seeds,
observation identities, masks, times, and frequencies. Lifecycle tests inject a
dispatcher failure and verify that retry preserves generation semantics.

`leo-online-replay CANDIDATES.tsv GRAPH.tsv TLES.txt` is the recorded application
replay used by that acceptance. It retains one coordinator from causal ingest
through publication, TLE installation, resumable search, and result emission.
Its input paths are explicit and it performs no RF, device, network, or server
access. The build also exposes the same executable as `test_ds9_online` for the
component test runner.

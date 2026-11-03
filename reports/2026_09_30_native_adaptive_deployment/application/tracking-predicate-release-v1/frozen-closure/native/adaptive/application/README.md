# Application session composition

The [live composition](LIVE.md) is opt-in and the [recorded replay](REPLAY.md)
keeps historical execution separate from radio ownership.

`Session` connects scanner events, measured UTC projection, a bounded observation
queue and the online tracking/search coordinator. It adds no hidden threads.
Use one serialized capture producer and one analysis state owner. A deterministic
replay can call both synchronously; on PLUTO+ the analysis owner belongs on the
background CPU lane. Live execution defaults to a configured two-lane
concurrency cap with one detector worker and one analysis worker. A caller may
select a bounded larger layout such as four/two/two on a Pi. These counts do not
set affinity or reserve physical cores.

The producer refreshes timing with `observe` and submits scanner callbacks with
`accept`. Projection is short and queue admission never waits for analysis.
The admission receipt distinguishes a projected observation from a queued one;
overflow increments `queue_dropped` and never fabricates a successful handoff.
`stats` is safe from either owner. Queue capacity is explicit and fixed.

Only the analysis owner calls `consume`, `advance_watermark`, `publish`, orbit
replacement or search methods. Publication is an explicit cadence boundary:
new ingress coalesces while a search finishes a bounded slice. Watermarks must
derive from measured source progress, including during quiet intervals, so old
tracks expire. New source generations get new Session objects; drain/cancel and
join the old analysis owner before destroying one. A failed timing refresh must
be surfaced by the caller and cannot be repaired by silently resetting its clock.

`publish` rejects a nonempty inbox with `invalid`; drain it first. Its snapshot
contains the consumed evidence known at that boundary, not a promise that no
later detector result can carry earlier physical support. Such late evidence
enters the next publication. The short inbox check never holds the producer
mutex while tracking runs.

`advance_watermark` also rejects a nonempty inbox before expiring history. The
caller must account for detector jobs still in flight when declaring quiet
source progress; an empty observation inbox alone does not establish this.

The opt-in live application CLI composes this library with local capture, while
the original scanner CLI continues to emit candidate-stage records. Live
full-standard and real-time qualification remain open.
The component test exercises producer/consumer concurrency, explicit overload
and a complete projected-observation-to-track snapshot handoff. Build against
an independently built online library:

```sh
bash native/adaptive/application/build.sh /tmp/app /tmp/online
/tmp/app/test-session
```

Build all linked libraries with matching sanitizer or ARM options. See the
timing, ingress and online component documentation for their scientific gates.

The session regression also compares reversed detector completion and two
concurrent event producers against serial ingestion. With one analysis owner,
all retained observations produce identical final track fields, support digests,
partition seeds and training masks. This tests the downstream handoff only;
multi-context scanner and live application deployment remain separately
qualified. Intermediate publications
retain consumed-prefix semantics, and events outside history or latency bounds
do not become valid merely because multiple workers are enabled.

`execution.hpp` defines the application CPU budget and owns the optional
tracking workers. A live budget reserves one to four total CPU lanes, at least
one detector worker and at least one analysis worker; replay may reserve zero
detector workers. Their sum cannot exceed the declared total. One analysis
worker preserves serial tracking and allocates no executor. Two to four analysis
workers expose borrowed synchronous tracking and scoring ports backed by one bounded native
executor. Keep `TrackingExecution` alive until every coordinator or session
using its port is destroyed. It rejects overlapping dispatch, drains accepted
work before propagating a callback failure, and creates a fresh executor on the
next dispatch. Work from later, unsubmitted chunks is not reported as accepted.
Tracking publication and point scoring use this pool sequentially on the single
analysis owner. Each scoring lane owns its numerical context and reduces in
fixed lane order. An owned pool rejects an existing external tracking or scoring
binding instead of silently overriding it. This integration requires a matching
online build; the earlier deployed worker release parallelizes tracking only.

Build its focused host, sanitizer, or ARM component test with:

```sh
tests/native_adaptive/application/build_execution.sh host /tmp/leo-app-execution-host
tests/native_adaptive/application/build_execution.sh sanitize /tmp/leo-app-execution-sanitize
tests/native_adaptive/application/build_execution.sh arm /tmp/leo-app-execution-arm
```

`tests/native_adaptive/application/build_paced_analysis.sh` builds a separate,
test-only composition around `live::Analysis`. One producer thread replays
persisted projected events according to source-counter offsets while the
Analysis worker independently owns consume, publication, a full-catalogue orbit
bank, and bounded search. Prefix mode compares paced and unpaced results on the
same host. Full modes cover the available 299.802-second recording and compare
the final score with an independent synchronous native reference. The physical
full paced run is lossless but failed the five-second publication target; its
failure is retained in the deployment report. The configured 600 s history with
96 ten-second knots is a memory/coverage profile, not evidence that 600 seconds
of observations have been exercised. These tests do not qualify raw IQ,
detector execution, RF capture, live clock authority or regional discovery.

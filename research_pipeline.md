# Independent Standard and Research Pipelines

## Status

Parked design. Do not implement or enable the Research pipeline until the
offline probe-geometry comparison and bounded capacity tests below have been
reviewed. Standard remains the only automatic ordinary-capture pipeline.

## Objective

Provide two first-class analysis lanes over the same immutable recording:

- **Standard:** two 20 ms pilot probes starting at 0 and 25 ms in every
  50 ms subwindow.
- **Research:** three 20 ms probes starting at 0, 15, and 30 ms in every
  50 ms subwindow.

The lanes share raw IQ and pure scientific implementation, but have independent
configuration, run lifecycle, current promotion, queue state, artifacts, PNGs,
failure state, and browser tab. Neither lane consumes the other lane's
scientific products.

## Probe contracts

Introduce an additive `ProbePatternV2` with explicit placement rather than an
implicit probe count:

```python
standard = ProbePatternV2(
    subwindow_ms=50,
    probe_ms=20,
    start_offsets_ms=(0, 25),
)

research = ProbePatternV2(
    subwindow_ms=50,
    probe_ms=20,
    start_offsets_ms=(0, 15, 30),
)
```

Validate that offsets are unique, ordered, nonnegative, map to integral
samples, and satisfy `offset + probe_ms <= subwindow_ms`. The exact ordered
offsets are part of the schedule and configuration digests. For 60 complete
seconds Standard emits 2,400 probes/path and Research emits 3,600 probes/path.

Research probes overlap by 5 ms. Persist exact support intervals and report raw
probe count separately from effective non-overlapping support. Overlapping
observations must not be presented as statistically independent trials.

## Pipeline authority and catalog model

Add `PipelineLane = standard | research` and an immutable
`PipelineDefinition` that binds:

- definition ID/canonical digest;
- lane;
- exact executable Git SHA;
- graph digest;
- configuration document and digest.

Keep executable release authority separate from pipeline definition so one
reviewed binary may expose both immutable configurations without pretending
that one SHA has only one configuration.

Migrate active/current identity from one row per session to one row per
`(session_id, pipeline_lane)`:

- at most one active run per session and lane;
- one independently promoted current run per session and lane;
- failure, cancellation, retry, and promotion affect only their lane;
- existing ordinary current runs migrate explicitly to Standard.

Persist the definition ID on every run. Product readers, lineage closure,
presentation selection, PNG identities, and cache keys must bind the exact
definition and run. Cross-lane product substitution must fail closed.

## Scientific implementation

Use one pure receiver analyzer parameterized by `ProbePatternV2`; do not fork
Standard and Research detector implementations. Both lanes retain the same
edge authority, GLRT64/Symbolwise/Anchor-8 comparisons, primary-candidate QAM,
degree 1/2/3 trajectory fitting, and corrected replay. Only GLRT64 observations
may propose trajectories in either lane.

Both lanes require `cfo_acquisition_mode=independent_wide_per_probe` with an
exact -400 to +400 kHz initial search on every scheduled probe. This policy and
its bounds are part of each immutable definition/configuration digest. A shared
outer-window seed is not an allowed Standard or Research execution mode.

The offset-0 probes are a mandatory parity subset: for identical IQ and
scientific configuration, every Research offset-0 result must equal the
corresponding Standard result within the frozen numerical tolerance.

Initial implementation performs independent raw verification and science for
both lanes. Cross-run content-addressed reuse is a later optimization, not a
correctness dependency.

## Scheduling and operations

- Standard remains automatically queued for eligible ordinary captures.
- Research begins as explicit/manual only.
- Workers claim reviewed pipeline definitions, not merely a release label.
- Research has a distinct queue/resource class and cannot consume all heavy
  tokens or starve Standard.
- Queue/UI surfaces identify lane, session, subject, release, definition, and
  progress.
- Do not auto-enable Research at a 180-second capture cadence until measured
  drain time proves it will not accumulate a backlog.

## API and browser

Use lane-parameterized endpoints rather than duplicated implementations:

```text
GET  /api/v2/recordings/{session}/analyses/standard
GET  /api/v2/recordings/{session}/analyses/research
POST /api/v2/recordings/{session}/analyses/standard/rerun
POST /api/v2/recordings/{session}/analyses/research/rerun
```

The recording detail page has top-level **Standard analysis** and
**Research analysis** tabs. Each tab owns its status, release/definition,
run/re-run action, paired/radio/RX selection, trajectory table, and persisted
PNG gallery. Standard is selected initially and only the selected lane is
fetched. `Not run`, queued, running, complete, partial, and failed are rendered
independently; absence or failure in one lane never hides the other.

## Checkpoints and tests

### C0 — schedule contract

- Exact one-second starts/counts for `(0,)` and `(0,15,30)`.
- Exact 60-second counts of 1,200 and 3,600 per path.
- Reject negative, duplicate, unordered, overflowing, or fractional-sample
  offsets and incomplete trailing seconds.

### C1 — catalog lanes

- Populated migration maps old current runs to Standard.
- Standard and Research may be active simultaneously for one session.
- A second active run in the same lane rejects.
- Independent promotion, failure, cancellation, retry, and retention tests.
- No cross-lane product/dependency/current substitution.

### C2 — execution authority

- Same executable SHA may advertise two exact reviewed definitions.
- Workers reject unknown definitions and graph/config/executable disagreement.
- Research throttling cannot starve Standard; claim mismatch is attempt-neutral.

### C3 — numerical behavior

- Standard produces 20 and Research 60 probes for one second.
- Every common offset-0 probe agrees within frozen tolerance.
- Only GLRT64 enters segmentation/tracking.
- Linear/quadratic/cubic fits and corrected replay remain deterministic.
- Correct upper/lower edge is mandatory in both lanes.
- Wrong-edge, noise, rolled-pilot, gap, truncation, overlapping-support, and
  crossing/intermittent-track controls remain negative or explicitly partial.

### C4 — full vertical

On real PostgreSQL and compressed local fixture IQ, create, execute, seal, and
promote both lanes. Assert exact run/job/product/dependency inventories,
independent current pointers, immutable manifests, crash/retry behavior, and
zero QNAP writes.

### C5 — API/UI

- Playwright proves both tabs, Standard default selection, lazy lane-specific
  requests, independent state, correct run-specific PNG URLs, and lane-specific
  re-run buttons.
- Research `Not run` is never rendered as `No signal`.
- Corrupt/missing Research evidence cannot hide valid Standard evidence and
  vice versa.

### C6 — bounded capacity qualification

Use the reviewed local corpus. Run at least five repetitions per lane and
record wall time, CPU, RSS, IQ bytes, probe throughput, and queue drain.
Numerical parity gates precede performance comparison. Keep Research manual
until its measured concurrency limit and 180-second cadence behavior are safe.

## Implementation order

1. Freeze `ProbePatternV2` and schedule tests.
2. Add pipeline definition/lane contracts.
3. Migrate active/current catalog identity to session plus lane.
4. Parameterize the existing analyzer with the pattern.
5. Register both definitions under one executable authority.
6. Add lane-aware worker claims and resource limits.
7. Generalize presentation/API selection by lane.
8. Add browser tabs and lane-specific actions.
9. Run numerical parity, real vertical, and bounded capacity gates.
10. Keep Standard automatic and Research manual until reviewed capacity passes.

## Offline comparison evidence — 2026-08-20

The initial comparison used the known-signal, read-only four-path fixture
`production-24h-20260819-01-trial-00000132`, `stream-0`, RX0, lower edge. The
QNAP source was copied normally to an isolated local temporary root; all
analysis and artifacts were written locally. No acquisition, live service, or
QNAP path was changed.

All six schedules were rerun with independent full-range CFO acquisition per
probe. The comparison tool also now consumes the exact configured probe length;
the earlier 5 ms, 10 ms, and 50 ms detector/tracker results were invalidated
because that tool had sliced a hard-coded 20 ms support.

| Geometry | Probes | QAM/pilot positives | Fitted trajectories | Families | GLRT64 replay representatives |
|---|---:|---:|---:|---:|---:|
| 1 x 20 ms | 1,200 | 294 | 69 | 6 | 4 |
| 2 x 20 ms | 2,400 | 576 | 81 | 8 | 4 |
| 3 x 20 ms | 3,600 | 871 | 86 | 5 | 4 |
| 5 x 10 ms | 6,000 | 1,346 | 78 | 7 | 5 |
| 10 x 5 ms | 12,000 | 2,619 | 78 | 8 | 5 |
| 1 x 50 ms | 1,200 | 325 | 69 | 5 | 3 |

The long candidate intervals near 19--25 s and 25--38.5 s recur across all
schedules. The 5 x 10 ms and 10 x 5 ms runs each retain five representatives,
while their maximum QAM accuracy remains below the 20 ms and 50 ms cases. They
remain Research challengers pending repeatability and direct runtime/RSS
qualification.

The historical 1 x 20 ms control establishes shared-seed choice as a material
source of one-second CFO structure. Standard and Research now admit only
`independent_wide_per_probe` with exact -400/+400 kHz bounds; the mode and
bounds are part of configuration/cache identity.

Artifacts, including per-method Standard plots, QAM timelines, full-duration
GLRT64 before/after correction plots, trajectory-family plots, JSON, and CSV,
are under `artifacts/probe-geometry-comparison/`. These are exploratory
candidate-only results, not attribution or payload evidence, and do not yet
justify enabling Research automatically.

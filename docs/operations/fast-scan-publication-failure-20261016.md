# Fast-scan orbit publication failure investigation

Inspected remote main `3e2fe57d1` and the running production services on
2026-10-16. No RF collection or scientific-policy changes were made.

## Recent legacy analysis failures

Thirteen successive recordings from `fast8-auto-20261016-154519-5b805d74-1-upper`
through `fast8-auto-20261016-220156-22c968b0-1-upper` failed at
`FastScanStore.publish_orbits`, after the scientific stages completed.
Every pipeline log ends in `PermissionError` creating its run directory beneath
`/srv/bulk/leo/fast-scan-orbits-v1`. The namespace was `root:root 0755`;
the analysis service runs as `leo:leo` with umask `0027`.

The initial root-run PNG backfill created that namespace. The deployment omitted
it from `ExecStartPre` directory preparation. The example backfill worked as root,
and the later service-user smoke test only read the example's existing immutable
artifacts, so it failed to exercise creation of a new run directory. These checks
therefore missed the permission defect. Automatic discovery deliberately does
not retry failed jobs, so repairing ownership alone cannot recover prior failures.

Repair: prepare the namespace as `leo:leo 0750`, add the same preparation to the
base service and an upgrade drop-in, and resume only the thirteen jobs whose
logs identify this publication failure. Each recovery invocation uses the saved
tracking input, existing scientific checkpoints, a 30-second analysis slice and
a 90-second process timeout. Mark completion only after the standard receipt
reports every stage complete. Do not rerun GLRT or shared-model inference.

All thirteen publication failures have now recovered. Each standard invocation
returned success, and every receipt reports `orbit_plots: true` alongside the
existing scientific stages. Their automatic statuses were changed to complete
only after those receipts passed. The service itself was not restarted; the
ownership repair applies immediately and the installed upgrade drop-in prepares
the namespace on future service starts.

## Orbit panel behavior on current main

The shared-model API release is `f141dbb30321bc8f9e8183576c511431ea60a6b3`.
It prefers the selected shared-model publication and falls back to legacy plots.
At inspection, the shared-model namespace contained 74 four-PNG manifests.
The latest failed legacy scan already had a successful shared-model plot set:
all four images loaded at 2400-pixel width in a production browser. Legacy job
failure and shared-model plot availability are independent statuses.

The UI previously rendered the entire orbit section only when `artifacts` was
nonempty and swallowed orbit-request errors. Empty publications and failed
requests therefore appeared as an absent panel. The repair keeps the panel
visible for a selected run and displays either a not-yet-published notice or
the request error while continuing automatic refreshes. Existing PNG galleries
remain visible. Production verification covers published images and injected
empty-manifest/503 responses.

Shared-model unavailable results are distinct from rendering errors. Of 97
shared jobs inspected, 81 were complete, 15 unavailable and one running.
Fourteen unavailable results said neither shared-q endpoint passed strict
admission; one lacked calibration bootstrap tracks on both receivers. The plot
worker only publishes for a complete, verified selected model.

Seven completed shared jobs also predated automatic orbit rendering. Their
`plot_state` was absent and they had no shared orbit manifest. `pending()` selects
only absent or running scientific statuses, and `process()` returns immediately
for a completed prior result, so the upgraded watcher cannot backfill them.
These seven were explicitly rendered with `leo.cli.shared_fast_orbits`,
using their immutable terminal/stage evidence and a 180-second subprocess limit
per result. Existing shared jobs with published PNGs and unavailable scientific
results are excluded. No inference is rerun and no admission threshold is relaxed.
All seven renderers returned success in 24–30 seconds each, and their statuses
now record `plot_state: complete`. The API serves four shared-model PNGs for
each recovered result.

Validation: 14 targeted Python tests, all 249 web tests, the production web build,
and browser checks of actual PNGs plus simulated empty-manifest and 503 responses
passed. The UI-only deployment preserved the shared-model API selection and both
analysis watchers. The current main worktree contains the reproducible source
changes, deployment snippets and regression tests.

## Other historical failures

The full legacy inventory initially contained 323 jobs: 297 complete, 24 failed,
one tracking and one recording. Besides the thirteen permission failures:

* Four captures were rejected for invalid sample support. Sealed window metadata
  identified `adc12_clipping`: 2026-10-11 21:38:14 UTC (one visit), 2026-10-12
  16:58:39 UTC (five), 2026-10-14 17:34:18 UTC (three), and 2026-10-16 13:44:17
  UTC (one, visit 2432). `tracking_input` rejects any invalid window; it does not
  silently omit it. This behavior was left unchanged.
* Two early tracking publications used a four-channel tracklet contract for CH8.
* Three early tracking failures had empty input or no track meeting the frozen
  geometry thresholds.
* Two captures failed at acquisition: a regressed terminal counter/partial
  support and a transport timeout followed by device-restoration failure.

These eleven older failures are not permission-recovery candidates and remain
failed. Successful shared-model admission is not inferred from their statuses.

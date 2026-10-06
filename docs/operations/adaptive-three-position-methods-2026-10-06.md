# Adaptive baseline, T1AT and V16 rollout

Status: API/WebUI deployed; full-budget scientific replay, worker cutover and merge
are still in progress. No new RF collection is authorized or needed. The unchanged
baseline remains independently published.

## Qualification evidence

The ordinary deployment-tier command was run against remote main
`c906693a7ac42d60b1dfcb7a69a700ec3e074ba5` at implementation revision
`523f1f56f414f73302ff60defc7ef3ec8a67bf77`:

```
./ops test --base c906693a7ac42d60b1dfcb7a69a700ec3e074ba5
```

All 27 selected pytest shards, Ruff checks/formatting, WebUI tests and build
passed. Whole-repository mypy failed with 28 errors in 14 unchanged files. An
independent extraction of `src` and `pyproject.toml` from the exact main revision
produced the identical 28 error lines: zero added or resolved errors. These include
missing existing Pluto SDK modules, pre-existing literal-version inheritance,
float literal annotations, and existing scratch/catalog typing. This is **not** a
passing whole-repository receipt. Preserve the failed receipt and the control
comparison; do not relabel the fast gate as deployment qualification.

Receipt: `.leo/test-receipts/e0dc6c170e8b0d8522741124e22cfe65b64244c4c4b79c9896db69da26db3669.json`.
Local logs: `/tmp/leo-regional-release-tests.log` and
`/tmp/leo-regional-main-mypy.log`.

An additional 89 affected numerical, application, contracts, storage, API and CLI
tests passed using the actual production worker interpreter:
`/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python`.
It is Python 3.14.4 with NumPy 2.4.6, SciPy 1.18.1 and Pydantic 2.13.4. Local
development uses Python 3.13.15 with the same numerical/Pydantic versions.

The fixed-state scientific parity checks and bounded saved-scan smoke replay are
documented in [the implementation plan](../plans/adaptive-three-position-methods.md).
The full 400-point-per-method replay is running in bounded, resumable slices under
`.leo/regional-position/full-budget`. It must finish before accuracy/runtime and
actual generated PNGs can be assessed. Smoke results are not release accuracy
evidence.

## Scoped runtime staging

Follow the existing analysis-overlay deployment approach. Do not deploy a bare
checkout over the live overlays or acquire RF to qualify an unrelated full-radio
release. Preserve the effective worker environment, scratch root, lease renewal,
resource limits and capture admission cutoff.

Current worker source: `/opt/leo-adaptive-memory/9181d637d/src`.
Current API source: `/opt/leo-adaptive-history/97e28127b/api/src`, followed by
`/opt/leo-v060-adaptive/a491b1ca7ee021e3e0e19a8c98becd2c9b1dae8b/src`.
Current WebUI: `/opt/leo-sacramento-only/f8ba2d1a1/web/dist`.

Build separate immutable worker/API source trees from these effective sources,
copying their resolved files. Apply the reviewed source delta to each role:
exclude API entry points from the worker tree and CLI entry points from the API
tree. The five existing source files changed in each role match the current-main
base byte-for-byte; differences found in the other role's unused entry points
must not be overwritten accidentally. Add the new modules and record all hashes.

Before selecting the staged trees, verify their imports and affected tests using
the production interpreter. Record the complete active worker instance list and
the previous drop-ins. Change only analysis workers, queue reconciliation and API
source/UI selectors. Do not change RF capture services, database schema, or
concurrency quotas. Restart workers at job boundaries or use their existing
SIGINT cancellation/requeue behavior; never steal a live lease.

## API/WebUI cutover

The immutable staged trees are `/opt/leo-regional-position/aef0cb9477a9-r2`.
`stage.json` records the source revision, complete file hashes, inherited trees,
reviewed replacements and WebUI asset hashes. The worker tree passed 55 affected
tests using its actual imports and production interpreter. The API tree passed
19 contract/storage/API tests, including unchanged baseline V2 and V3 routes.

Staging exposed an old, unused V2-only baseline renderer in the live API tree.
The r2 API stage additionally pins `presentation/adaptive_tle_position.py` to the
already-deployed live-worker/current-main implementation. No baseline numerical
code changes. The r2 worker tree is hash-identical to the tested first stage.

The API was switched with
`/etc/systemd/system/leo-api.service.d/zzzzzzzzzzzzzz-regional-position.conf`.
Its effective source starts with the r2 API tree; its static assets come from
the r2 `web/dist`. The API remains read-only on port 8090. Worker and capture
selectors have not changed.

Live HTTP and Chromium checks verified:

- The screenshot scan's baseline document is byte-for-byte equivalent to the
  pre-cutover response, and its 135,150-byte PNG retains digest
  `sha256:9000d4b352f2279dbbbc1bd8c853b6957fbe075ef25c5dec2edeaa4cddd95b46`.
- Chromium decodes that image at 840 by 720 pixels.
- The new regional endpoint returns pending and the actual recording detail view
  displays the T1AT/V16 panel without alerts. No regional image is claimed yet.
- The served bundle is `index-LR8f9R8p.js`; API and existing capture timer are active.

Local browser evidence is `.leo/regional-position/live-ui-check.json` and
`live-regional-panel.png`. The full-budget replay continues separately under its
original configuration binding. Actual live T1AT/V16 image decoding and automatic
worker completion remain outstanding.

## Completion and rollback checks

Require the following before declaring the task complete:

- Full-budget numerical replay with both RF arms, all stage failures, runtime and
  memory recorded; reference position used only after selection.
- Production API serves digest-verified baseline, T1AT and V16 PNGs, and browser
  inspection confirms each image loads in the recording detail view.
- A newly admitted adaptive job reaches verified three-method completion through
  the automatic queue. Pending slices yield without hiding the completed baseline.
- Native partial-band captures show three explicit insufficient-evidence figures,
  consistent with their immutable `not_qualified_for_partial_band` source contract.
- Live API, prior worker instances and capture cadence remain healthy; production
  evidence is tied to the reviewed source and merged remote-main revision.

Rollback restores the previous worker/API source and WebUI drop-ins, reloads
systemd and restarts only the changed services. Keep all new products and
checkpoints; previous software ignores their versioned namespaces. Preserve the
current worker source at `/opt/leo-adaptive-memory/9181d637d/src` and the API/UI
selectors above as rollback authorities.

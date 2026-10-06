# Adaptive baseline, T1AT and V16 rollout

Status: analysis workers, queue, API and WebUI deployed and verified on 2026-10-06.
The saved-scan production canary completed through the normal queue, and Chromium
loaded all three PNGs. Source changes are tracked in PR #67. No new RF was collected;
the unchanged baseline remains independently published.

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
The full 400-point-per-method replay completed under
`.leo/regional-position/full-budget`, using the production interpreter and `leo`
service user. It used 2,956 original GLRT windows, 648 distinct trial locations and
four final regional hypotheses. One hypothesis failed the calibration prefit
stationarity check and was explicitly excluded. The other three supplied the same
six starts to each model/RF-arm combination: 24 final fits, 17 stationary.

Results for `scan-fw-4eaab4879fec576b`:

| Method / RF arm | Reference error | Posterior frequency RMS | Selection score | Selected fit |
| --- | ---: | ---: | ---: | --- |
| T1AT fitted-c | 2.149 km | 75.00 Hz | 37033.65 | Stationary |
| T1AT c=0 | 2.124 km | 145.04 Hz | 37532.32 | Stationary |
| V16 fitted-c | 1.766 km | 67.02 Hz | 38500.65 | **Not converged** |
| V16 c=0 | 1.729 km | 140.09 Hz | 37425.21 | Stationary |

Selection scores include the receiver-correction penalty. Compare scores within
a model; C0 and V16 use different likelihood and timing-prior settings.

The existing baseline reference error is 5.79 km. Its capped RMS is a different
quantity from the posterior RMS above. Fitted c improves frequency RMS in this
comparison, while c=0 is slightly closer to the reference for both models. This
single saved-scan diagnostic does not establish general localization improvement.
The ablation is explicitly conditional on shared fitted-c upstream calibration
and association. The reference enters only after estimate selection.

V16 fitted-c returned optimizer success, but its independent stationarity residual
is 8.339, above the 0.001 threshold. Its objective is also higher than the selected
c=0 objective despite the fitted model's additional freedom. Retain this as a
bounded, non-converged diagnostic; do not describe it as a certified optimum or a
position fix. Both maps and the WebUI expose the convergence status. All selected
estimates are inside their spatial boundaries. The searches leave 149/175 cells
deferred and do not certify a global optimum.

The seven resumable slices consumed 3,252.40 seconds (54.21 minutes) of processing,
with a maximum RSS of 548,492 KiB (535.64 MiB), roughly one CPU core, and zero swaps.
This is measured saved-scan processing time, not an interactive latency promise.
Local receipts: `full-budget-summary.json`, `full-budget-resources.json`, and
`qualified-T1AT.png` / `qualified-V16.png` under `.leo/regional-position`.

Qualification found a projected 20-second timing seed rounded to
`20.000000000000004`, causing every objective evaluation to be rejected. Numerical
revision `05ba40d4fd689075519ae68e2b693d1539ed48f7` starts timing seeds strictly
inside the unchanged bounds. Both score regressions and 19 related staged-runtime
tests pass. The full replay restarted under a new binding; none of the superseded
replay's checkpoints were reused. No coarse point in the corrected replay was
unscoreable. Final mypy still reproduces exactly the same 28 main-control errors,
with no added or resolved errors (`/tmp/leo-regional-final-mypy.log`).

Scientific configuration:
`sha256:692a799d6b6612deee23d15d4fb6bc0265f8f8fbd3e52d969a57936f2e8a603e`.
Checkpoint binding:
`sha256:6d56942f894d204389f032e2ba051a91ef7e5ec8bef09d2ae6ea0f7a0a89ef38`.

## Scoped runtime staging

Follow the existing analysis-overlay deployment approach. Do not deploy a bare
checkout over the live overlays or acquire RF to qualify an unrelated full-radio
release. Preserve the effective worker environment, scratch root, lease renewal,
resource limits and capture admission cutoff.

Pre-cutover worker source: `/opt/leo-adaptive-memory/9181d637d/src`.
Pre-cutover API source: `/opt/leo-adaptive-history/97e28127b/api/src`, followed by
`/opt/leo-v060-adaptive/a491b1ca7ee021e3e0e19a8c98becd2c9b1dae8b/src`.
Pre-cutover WebUI: `/opt/leo-sacramento-only/f8ba2d1a1/web/dist`.

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

The initial API staged trees were `/opt/leo-regional-position/aef0cb9477a9-r2`.
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
The final worker and queue source is
`/opt/leo-regional-position/05ba40d4fd68-r2/worker/src`. The final API and WebUI use
`/opt/leo-regional-position/5600cd81e5f2-r2/api/src` and its sibling `web/dist`.
Both stages have byte-identical Python sources; the later stage fixes intrinsic
image sizing for browser lazy loading. Its 50 affected UI tests and production
build pass. The API remains read-only on port 8090.

Workers switched at 17:56 UTC. All 19 previously active instances remain active;
scratch paths, capture cutoff, lease behavior and resource quotas are preserved.
The queue timer uses the new source for prospective admission. The new static
result/checkpoint namespaces are pre-created as `leo:leo`, mode 0750, by worker
`ExecStartPre`; workers do not need write permission on the bulk root. The existing
RF capture timer and its cadence were not changed.

Live HTTP and Chromium checks verified:

- The screenshot scan's baseline document is byte-for-byte equivalent to the
  pre-cutover response, and its 135,150-byte PNG retains digest
  `sha256:9000d4b352f2279dbbbc1bd8c853b6957fbe075ef25c5dec2edeaa4cddd95b46`.
- Chromium decodes that image at 840 by 720 pixels.
- The regional endpoint returns complete; both 1080-by-960 images decode in the
  recording detail view, their payloads match the advertised digests, and there
  are no regional-panel alerts. The table and PNG show V16 fitted-c as not converged.
- Chromium initially exposed zero-sized lazy images. Intrinsic dimensions plus an
  explicit responsive width override the gallery's `width: auto`; `object-fit:
  contain` preserves the image aspect ratio. Three fresh-browser runs passed with
  unmodified DOM, including image decoding and digest checks.
- The served bundle is `index-C7REbQC-.js`; API and existing capture timer are active.

Local browser evidence is `.leo/regional-position/live-ui-check.json` and
`live-regional-panel.png`. Production job **48369** was admitted through the public
bounded backfill CLI for this one saved capture and completed on worker 21 in one
attempt. Its 679 verified numerical stages were seeded through checkpoint ports;
no finished document or PNG was copied into production. The ordinary tracking
worker generated and published the result. Production numerical methods and image
digests match qualification exactly; the document's bank-preparation timing receipt
naturally differs on replay.

PNG digests:

- T1AT: `sha256:14ab564330e0fda82c30103c6e84c2ac4e74318aab0c7fb7a96fb7b0a6e9296f`
- V16: `sha256:a12cea08121f7e6e0d8a57b11a8839aa67f20e98c3a41f5b95a99f369bba64fd`

## Coverage and rollback

Native partial-band inputs retain the immutable
`not_qualified_for_partial_band` declaration and generate three explicit
insufficient-evidence figures through their analysis completion path. Component
tests cover that path, its queue completion checks and its WebUI panels. No native
partial-band capture was found in the bounded inspection of 186 recent production
captures, so the live browser canary above qualifies the ordinary adaptive path;
it must not be described as a live partial-band qualification.

Rollback removes only this rollout's `zzzzzzzzzzzzzz-regional-position.conf`
drop-ins from the worker template, queue service and API service, reloads systemd,
and restarts the affected services using their existing SIGINT/requeue behavior.
The prior selectors remain in their earlier drop-ins. Keep all new products and
checkpoints; previous software ignores their versioned namespaces. Do not change
capture services, database schema or golden scientific fixtures.

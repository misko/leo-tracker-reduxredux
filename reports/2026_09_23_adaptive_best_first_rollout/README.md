# Adaptive best-first TLE position rollout

**Status: v2 deployed, canary-qualified and browser-verified; the frozen 24-hour v2 backfill is in progress.**

This directory records the qualification evidence and the fixed session inventory for promoting
`scanner-adaptive-tle-position-v2` into the standard adaptive analysis pipeline. V2 changes only
the Sacramento prior radius from 500 km to 250 km; Reno remains 500 km, and both retain the same
1,000 km search box, grid phase, numerical estimator, randomized masks, levels and 400-point
budget. Release `fb152566148e662dc22d7948607fd65998f033a9` is active in production. A completed
backfill must be supported by the final 165-session integrity receipt; enqueueing alone is not
completion. The v1 receipts in this directory are historical evidence and are explicitly
superseded for new publication by v2.

## Deployment and live verification

Release `fb152566148e662dc22d7948607fd65998f033a9` was activated for the v2 API at
05:50:25 UTC on September 23 and for all 17 adaptive analysis workers at 05:56:50 UTC. The v2
producer and workers are pinned to that immutable release; the existing `current-worker` selector
is not the authority for these overridden adaptive services.

All 13 selected v2 development deployment gates passed, including PostgreSQL, mypy, formatting,
component tests and the web build/tests. The immutable v2 release qualification passed its recorded
plan; its exact commands and evidence are in `v2-release-qualification.json`.
The earlier v1 release `7532ff9d7172997eb3c78d93fa4b212b8c6ee2a6` and its unchanged-acquisition
check remain historical evidence. V2 introduced an immutable contract, store and routes with
Sacramento 250 km / Reno 500 km priors while preserving v1 as a read-only historical product. No
new radio collection was started for either rollout.

The historical v1 production UI was checked with normal Scanner navigation for
`scan-fw-f91acea118327e66`. Its 1560×720 PNG loaded, the digest-bound image URL matched the v1
manifest, and both prior results and all 31 eligible tracks / 873 observations were visible. Two
unrelated compatibility/fallback browser errors are recorded verbatim in the v1 browser receipt;
they did not affect that panel.

- V2: [development gates](v2-development-test-receipt.json),
  [immutable release qualification](v2-release-qualification.json),
  [API deployment](v2-api-deployment.json), [worker activation](v2-worker-activation.json),
  [release pinning](v2-pinning.json), and [queue gate](v2-queue-gate.json)
- Historical v1: [development gates](development-test-receipt.json),
  [release qualification](release-qualification.json), [API deployment](api-deployment.json),
  [worker activation and unchanged acquisition identity](worker-activation.json), and
  [browser screenshot](ui-canary.png) / [browser receipt](ui-canary.json)

The actual v2 production browser check also passed for `scan-fw-f91acea118327e66`, using normal
Scanner navigation, one history-page advance, and scrolling to the results panel. It displayed
Sacramento 250 km and Reno 500 km with 31 tracks / 873 observations, loaded the digest-bound
1560×720 PNG, and provided the v2 JSON download link. No JavaScript page errors were observed.
See the [v2 screenshot](v2-ui-canary.png) and [browser receipt](v2-ui-canary.json). The older v1
screenshot remains historical evidence only.

The first four v2 estimator jobs completed successfully on their first attempts. Their cumulative
two-prior numerical runtimes were 138.079 to 211.643 seconds, and sampled peak physical memory was
4.045 to 6.574 GiB PSS per forked process group, with no sampled swap. Before those jobs leased,
four memory slots were occupied by bounded adaptive-scan hop analyses; that initial delay is queue
occupancy rather than estimator runtime. See [the bounded v2 resource receipt](v2-resource-rollout.json).

## Method

For each saved scanner session, the analysis reconstructs every disjoint trajectory track with at
least six observations spanning at least three seconds. It uses the latest causal Starlink catalogue
snapshot before the declared 505-second guard and excludes labelled debris. No known receiver
coordinate, supplied reference coordinate, saved site-conditioned candidate shortlist, or truth
label enters inference.

The default v2 analysis evaluates a 250 km-radius prior centred on Sacramento and a 500 km-radius
prior centred on Reno. Denver is excluded by the current initialization assumption. The search box
remains 1,000 km for both priors, so changing the Sacramento radius does not shift the underlying
grid phase. Each prior uses a bounded
best-first search with 100, 50, 25, and 12.5 km cell-centre levels and a 400-point budget. Search
priority is the exact score at an evaluated centre. There is no certified spatial lower bound and no
claim that a budget-limited result is the global optimum of the continuous region.

At every receiver centre, the full causal catalogue is screened with the qualified coarse-visibility
gate and evaluated in bounded candidate blocks. For each track and catalogue identity, orbit-time
shift and constant frequency offset are fit on the fixed randomized training partition. The identity
is then selected by randomized-evaluation RMS, matching the qualified research estimator. That
evaluation partition therefore participates in model and location selection; it is not an independent
final test. The published value is labelled a **selection score**, not a likelihood, posterior,
calibrated uncertainty, or GPS-quality position fix.

The location objective is the duration-proxy weighted mean squared residual across all eligible
tracks, capped at 800 Hz per track and reported as its square root. Weights are distinct one-second
bins relative to the session start. They are an evidence-duration proxy, not calibrated independent
information; receiver paths and tracks may remain correlated. The 200 Hz track threshold and
qualifying observation count are diagnostics. The standard output selects the best incumbent across
all evaluated levels and separately reports the best evaluated 12.5 km centre.

## Qualified v2 canary

The source-bound canary is `scan-fw-cf510316ae7f05d5`. It contains 34 eligible tracks, 750 unique
observations, and 11,104 causal catalogue candidates. Track IDs, observation IDs, randomized masks,
partition seeds, and represented-second weights match the frozen research evidence exactly.

| Prior | Result | East (km) | North (km) | Capped weighted RMSE (Hz) |
|---|---|---:|---:|---:|
| Sacramento 250 km | Global and finest incumbent | -106.25 | -81.25 | 184.35118554536405 |
| Reno | Global and finest incumbent | -243.75 | -181.25 | 184.51095863043360 |

The v2 Reno result reproduces all 400 v1 coordinates and scores exactly, including selected
catalogue identities and time shifts. Sacramento evaluated 400 points within 250 km; all 158
coordinates shared with the v1 run have exactly equal scores. The smaller prior changed search
allocation and selected a different point. The post-selection reference error was 19.215 km for
v2, versus 13.444 km for the v1 global incumbent and 6.719 km for the v1 finest incumbent. Thus the
slightly lower v2 selection score is **not evidence of improved position accuracy**. Both searches
reached the point budget with deferred cells, so neither establishes the continuous-region optimum.

The Sacramento selection score changed from 184.78354 Hz to 184.35119 Hz (`-0.23%`, or
`-159.5975 Hz²` in weighted capped MSE). Seven of 34 selected catalogue identities and 31 of 34
selected integer time shifts changed. These nuisance and association tradeoffs can lower the
selection score while increasing reference error; they do not establish which identities are
correct. The principal scientific limitation is therefore the flexibility and degeneracy of the
joint identity/time-shift/offset selection under a finite search budget, rather than prior radius
alone. See the machine-readable score decomposition and companion plot in `v2-canary/`.

The v2 prediction bank built in 31.064 seconds. Recorded cumulative runtime was 90.046 seconds
after Sacramento and 143.497 seconds after Reno with four forked point workers. Runtime is host- and
load-dependent and is not a throughput guarantee.

Two initial live v2 examples illustrate the spread that the final backfill must preserve rather
than filter. Session `scan-fw-f91acea118327e66` produced Sacramento 5.791 km / 122.965 Hz and Reno
15.995 km / 135.209 Hz post-selection diagnostics from 31 tracks and 873 observations. Session
`scan-fw-192f760c85926340` produced Sacramento 181.181 km / 398.722 Hz and Reno 445.442 km /
204.898 Hz from 34 tracks and 1,053 observations. These reference errors are evaluation metadata,
not inference inputs; the contrasting outcomes show why a complete frozen-window audit is needed.

Canary evidence:

- [V2 comparison and source-binding receipt](v2-canary/comparison.json)
- [V2 complete machine-readable document](v2-canary/document.json)
- [V2 sealed manifest](v2-canary/manifest.json)
- [V2 digest-bound map PNG](v2-canary/map.png)
- Historical v1 evidence: [parity receipt](canary-parity.json), [API status](canary-status.json),
  and [map](canary-map.png)
- [Frozen 24-hour inventory](inventory.json)

The PNG may show the supplied reference position and horizontal error only after inference is
sealed. That reference is presentation/evaluation metadata and never affects catalogue selection,
partitioning, search priority, or the selected coordinate.

## Published evidence and verification

Each completed session is published immutably under
`scanner-adaptive-tle-position-v2/<session-id>/` with a canonical `document.json`, a digest-bound
`map.png`, and a sealed `manifest.json`. The JSON binds the scanner input and analysis manifests,
configuration, causal snapshot, frozen per-track observations and masks, compact evaluated-point
inventory, search trace, deferred frontier, and global and finest per-track selections. The local
store rejects QNAP paths.

The read-only routes are:

```text
GET /api/v1/scanner/tracking/{session_id}/adaptive-tle-position-v2
GET /api/v1/scanner/tracking/{session_id}/adaptive-tle-position-v2/map.png?sha256={artifact_sha256}
```

Before marking rollout complete, verify all of the following against the staged production release:

1. Component, integration, typing, formatting, web build, and web tests pass from the release tree.
2. A production canary publishes a complete manifest whose input and analysis digests match the
   current scanner source, whose JSON and PNG hashes verify, and whose state is visible through the
   API and scanner UI.
3. The UI labels the value as a selection score and no position fix, renders both prior results,
   distinguishes global and finest incumbents, and loads the digest-bound PNG.
4. An insufficient session, if encountered, publishes no coordinates and renders its explicit reason
   in both JSON and PNG. Integrity or infrastructure failures must fail the job rather than become an
   insufficient scientific result.
5. The optimized production canary retains the qualified track/observation inventory and numerical
   result within the parity tolerances in `canary-parity.json`.

## Frozen backfill window

The closed window contains 165 sessions from `2026-09-22T04:36:38Z` through
`2026-09-23T04:36:38Z`. The exact IDs and publication timestamps are frozen in `inventory.json`.
At inventory time, 163 sessions had figures-ready analysis and complete tracking, one was still in
tracking, and one had partial adaptive analysis. These are workflow prerequisites, not scientific or
truth-based eligibility gates.

The v1 enqueue and partial resource measurements are retained as historical receipts in
`enqueue-receipt.json`, `v1-resource-rollout.json`, and `v1-superseded-incomplete.json`. That
backfill was deliberately stopped when the prior policy changed; it is not a completed rollout.
The same frozen 165-session inventory is now being processed into the v2 namespace. V2 jobs use
the existing four-slot memory resource class and four forked scoring processes per job.

The [initial progress receipt](v2-backfill-progress.json) verifies two frozen publications and
163 pending, with no invalid publications. This is an early snapshot, not a completion claim.
The [completion monitor](v2-completion-monitor.json) runs independently of the interactive session,
checking the frozen inventory every 180 seconds. Once all publications are sealed, it runs the
full served-API/hash audit and produces `v2-rollout-summary/positions.csv`,
`position-summary.json`, and `position-summary.png`, plus a completion receipt. Any invalid
publication or summary failure produces an explicit failure receipt. It neither alters the queue
nor publishes Git commits. Its reproducible helper is [watch_completion.py](watch_completion.py).

The speculative commands in the original frozen inventory predate activation and are superseded
by the exact qualified release below. The producer was run as the `leo` service account with its
existing environment file, through a bounded systemd oneshot. Its argument vector was:

```text
/opt/leo-tracker/releases/fb152566148e662dc22d7948607fd65998f033a9/.venv/bin/python
  -m leo.cli.adaptive_processing_queue --bulk-root /srv/bulk/leo
  backfill-tracking --since-utc-ns 1790051798000000000
  --until-utc-ns 1790138198000000000 --limit 165
```

Use the v2 release's `tools/audit_adaptive_tle_position_rollout.py`, with `--bulk-root
/srv/bulk/leo`, `--inventory` pointing to this directory's frozen inventory, `--api-base
http://127.0.0.1:8090`, a new `--output` path, and `--require-complete`. It checks the public immutable
store, current scanner input and analysis hashes, served JSON and PNG, image decoding and split
metadata. Run `summarize.py` using the same interpreter, bulk root and inventory plus a new
`--output` directory to reproduce the aggregate CSV/JSON and plot after completion.

After the run, append a separate immutable result receipt containing the deployed release ID,
configuration digest, start/end timestamps, enqueued/completed/insufficient/failed counts, failed
session IDs and reasons, verified API/UI sample IDs, output document and artifact digest audit, peak
resource observations, and confirmation that all 165 frozen IDs were accounted for. Until that
receipt exists and passes review, the backfill remains in progress.

## Scientific follow-up

The rollout result should be treated as a bounded catalogue-and-position selection diagnostic.
The next scientific checks are to repeat the frozen-corpus comparison across v1 and v2, quantify
how often the smaller Sacramento prior changes the selected basin, and test time-shift
quantization, capped-track saturation, and candidate ambiguity on frozen positions. These checks
must preserve training-only nuisance fitting and must not use reference position to select a model
or location.

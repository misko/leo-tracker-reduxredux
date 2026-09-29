# Deployed adaptive GLRT audit — 2026-09-29

The automatic full-scan pipeline uses **20 ms windows at 120 ms stride**.
It additionally runs **20 ms windows at 20 ms stride on up to 64 selected
dwells** for relative-phase analysis. **10 ms stride is supported and is the
standalone/API default, but the automatic queue overrides it.** There is no
single stride describing all standard processing.

This is a read-only audit of deployed service commands, process command lines,
installed source, stored per-visit products and HTTP responses. No jobs were
started and no IQ was read or re-analyzed. See [evidence.json](evidence.json)
and the reproducible [audit.py](audit.py). The evidence snapshot ran from
14:02:11 to 14:02:29 UTC; processing counters can advance subsequently.

## Effective deployment, rather than standalone defaults

- Queue enqueue service: release `2c30eaf50064623a666e1c078c56a02cb3223a70`.
- Running adaptive workers: release `47e2705e437722daa5e6d6bb1c252d54b7a21dbc`.
- Running API process and its working directory: release
  `17484895464c225ebba977487aa36d3d81658bd8`.
- `/opt/leo-tracker/current-worker` resolves to another release and is not the
  effective executable of the pinned adaptive worker service.
- Capture service: immutable cadence runner
  `59359bf6f25c3aa63be22b541d0ad84d48c0ccd0b593e1aa599e2d5860787532`.

Live process inspection found nine adaptive analysis child processes explicitly
running `leo.cli.adaptive_hop_analysis ... --probe-stride-ms 120`. The queue
source also uses 120 when checking metrics, launching analysis and handing off
to tracking. This is not an inference from a default setting.

The source checkout `/home/mouse9911/gits/leo-adaptive-png-no-legends` is at the
running worker revision. The reviewed detector, analysis CLI, relative-phase
CLI, tracking source and tracking service files were byte-compared with installed
worker files. The reviewed UI panels also match the installed API release.
Hashes of the principal deployed sources are recorded in `evidence.json`.

## Every relevant processing path

| Path | Actual window/stride | Scope and role |
|---|---|---|
| Capture feedback | Whole-visit CI16 mean-power classifier, not GLRT | Current cadence runner uses `Ci16EnergyDetector(-38 dBFS)` to classify active/quiet visits. Firmware capabilities and historical on-radio GLRT panels are separate from this current path. |
| Main automatic GLRT | 20 ms / 120 ms | Every retained visit, both recorded receivers; generates sealed metrics and the three overview PNGs. |
| Within each GLRT probe | Acquisition, integer GLRT scoring, fractional epoch/CFO refinement | These operations process the same scheduled 20 ms excerpt. The peer-receiver fallback uses the same excerpt, not a hidden 10 ms schedule. |
| Automatic relative phase | 20 ms / 20 ms | Rank visits using paired candidates from the main metrics; re-run GLRT on at most 64 selected visits; then perform broadband and matched-pilot phase checks. |
| Tracking/TLE/position stages | Consume the main 120 ms metrics | The adaptive tracking reader explicitly binds 120 ms. These stages fit trajectories and predictions; they do not fill gaps by launching a dense GLRT scan. |
| Standalone adaptive analysis | Default 20 ms / 10 ms; configurable | CLI supports 10/20/40/60/120 ms. Application and numerical config defaults are 10 ms. Explicit production arguments override these defaults. |
| HTTP analysis status | Defaults to the 10 ms product | GET reads that configuration's status. It neither schedules analysis nor describes which arm the queue selected. |
| Web UI standard view | Explicitly requests 120 ms | Offers a separate 10 ms dense view “if published”; selecting it does not schedule work. |
| Legacy dual-RX phase V1/V2 | Uses a selected GLRT binding; CLI defaults to 120 ms | V1 publishes a supplied reviewed PNG; V2 extracts seeded phase from stored IQ and metrics. Their separate CLIs are not launched by the current automatic queue. |
| Local/joint GLRT refinement panel | Separate bounded comparison experiment | The UI displays saved refinement-comparison products. Its producer is `scanner_refinement.py`, not the automatic adaptive queue; it is not evidence of a full-scan dense GLRT pass. |

Numerical phase extraction has its own time grids. For example, relative-phase
broadband correlation uses 0.5 ms windows at 0.2 ms increments. These are phase
measurements, not 20 ms GLRT acquisition probes. The 20 ms acquisition excerpt
also should not be described as proof of coherent integration over every sample
throughout the entire 20 ms.

Principal code references in the matching source checkout:

- `src/leo/cli/adaptive_processing_queue.py:138,257,304`: production selection.
- `src/leo/cli/adaptive_hop_analysis.py:152,231`: configurable CLI and automatic
  overview/relative-phase handoff.
- `src/leo/scanner/adaptive_hop_analysis.py:287,330,661`: 20 ms window,
  actual-length probe count, and detector call.
- `src/leo/scanner/detector.py:131,281`: per-probe scoring and exact start/stop loop.
- `src/leo/cli/adaptive_relative_phase.py:65,81`: selected-visit limit and explicit
  20 ms stride override. The derived phase product remains bound to its parent
  main GLRT analysis, not a separately published all-visit 20 ms metrics set.
- `src/leo/storage/scanner_tracking_source.py:142`: explicit 120 ms reader.
- `web/src/AdaptiveAnalysisPanel.tsx:84,117`: default and selector wording.
- `src/leo/api/app.py:619,636`: HTTP default of 10 ms.

## Variable dwell length is independent of GLRT stride

The active dwell setting is chosen from 120, 240 and 360 ms; quiet dwell is
120 ms. The analyzer uses each visit's actual valid sample span, not simply the
configured maximum active dwell. For a window P=20 ms and stride S, the count is
`floor((actual_dwell_ms - P) / S) + 1` per receiver.

| Actual valid dwell | Automatic starts at 120 ms stride | Dense probe count at 10 ms | Relative-phase probe count at 20 ms |
|---|---|---:|---:|
| 120 ms | 0 ms | 11 | 6 |
| 240 ms | 0, 120 ms | 23 | 12 |
| 360 ms | 0, 120, 240 ms | 35 | 18 |

Thus a 360 ms visit normally contributes `[0,20)`, `[120,140)` and
`[240,260)` ms to the main GLRT. Changing stride does not change how much IQ
was recorded. Probes reset at each valid visit and do not span retunes.

All four sampled captures had only 120 ms actual valid visits, despite active
dwell settings of 240 or 360 ms. Sampled persisted visit products contain one
probe per receiver at start 0, with `probe_ms=20` and `probe_stride_ms=120`.
For `scan-fw-d479435ef17109f8`, all 2,218 capture events have zero active mask;
the decision reasons are eight warmup events and 2,210 weighted events. This
is consistent with the quiet/base-dwell path. It does not establish that longer
dwells never occur elsewhere or validate the RF classifier's scientific accuracy.

## Live API and artifact evidence

| Session suffix | Rate | Visits | Full-scan 10 ms | Full-scan 20 ms | Full-scan 120 ms | Relative phase |
|---|---:|---:|---|---|---|---|
| `ca88edc9307953b1` | 10 MS/s | 2,214 | Not started | Not started | Partial | Pending |
| `685d045965fa924b` | 5 MS/s | 2,218 | Not started | Not started | Partial | Pending |
| `d479435ef17109f8` | 10 MS/s | 2,218 | Not started | Not started | Figures ready | 64 selected, 61 supported |
| `6376718c921309b1` | 5 MS/s | 2,220 | Not started | Not started | Figures ready | 64 selected, 63 supported |

The two completed examples have completed tracking. Their 20 ms relative-phase
replays do not create full-scan 20 ms GLRT products, explaining why the 20 ms
status remains “not started.”

For each completed example, fetched the three GLRT PNGs (`coverage`,
`glrt64-response`, `cfo-trajectories`) and two relative-phase PNGs
(`relative-phase-overview`, `relative-phase-dwells`) from configuration/digest-bound
HTTP URLs. **All ten returned HTTP 200 and image/png, valid PNG signatures,
matching byte counts and matching manifest SHA-256 digests.** This checks those
artifacts only; no complete browser or all-position-artifact acceptance test was
performed during this audit.

## Corrections and consequences for the proposed experiment

My earlier statement that “production uses 120 ms stride” correctly describes
the main full-scan analysis but was incomplete about the automatic 20 ms
relative-phase replay. The plan must distinguish the main assignment from each
stage's deliberate derived analysis configuration.

The UI's “one probe per dwell” and “per 120 ms retained dwell” wording is too
broad for variable-length visits. The algorithm schedules two/three probes for
240/360 ms visits. Separately, the relative-phase UI omits the selected stride
and therefore follows the server's default 120 ms parent binding even when the
main panel is switched to 10 ms. These are concrete presentation/integration
issues to address in the proposed change, not proof that the stored 120 ms
metrics are wrong.

For a clean full-scan 10/20 ms trial, keep the phase stage's existing 20 ms replay
fixed in both arms and bind it explicitly to the correct parent metrics. A change
to that replay would be a second experimental factor. In particular, do not
replace every occurrence of 120 with a new global stride or conflate a view
default, parent binding and local replay schedule.

No live setting was changed. The earlier capacity estimate is for main GLRT
probe counts only; it excludes selected-dwell replays and downstream work.

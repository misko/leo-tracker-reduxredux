# Automatic adaptive broadband/pilot phase

The adaptive analysis queue now runs `adaptive-broadband-pilot-relative-phase-v1`
after sealed GLRT metrics and overview publication. A scan job completes only
when the phase product and both digest-bound PNGs are published. Processing is
resumable at dwell boundaries, with a 120-second additional budget per queue
slice. An in-flight dwell may exceed that budget; raw IQ is never truncated.

The automatic profile selects up to 64 dwells by the strongest phase-blind paired
GLRT margin in the existing overview. It reanalyzes six 20 ms probes in those
120 ms dwells. This is selected-dwell coverage, not exhaustive analysis of every
recorded dwell. Selection, total counts and supported counts are shown in the UI.
No historical bulk backfill is implied: the queue reconciles missing phase on
recent completed scans, and finishes phase for every newly analyzed scan.

The pure numerical estimator uses physically common captured bandwidth, fractional
delay and differential frequency/drift compensation, phase-normalized channel
fitting on the first half, disjoint frequency-band validation, and refined
known-pilot phase compared at matching frame times. Each dwell has an independent
reference; neither calibrated geometric phase nor continuity across retunes is
claimed. `supported` describes heuristic broadband checks. A pilot comparison
count means a comparison was available, not that its discrepancy passed a
calibrated accuracy threshold.

New artifacts are:

- `relative-phase-overview`: per-dwell broadband coherence, wrong-time control,
  A/B phase scatter, matched-pilot discrepancy and qualification counts.
- `relative-phase-dwells`: up to twelve representative trajectories, showing
  wrapped phase and frame-matched pilot/broadband points. All selected dwell
  numerical results remain in sealed checkpoints.

Insufficient-signal and single-RX scans also publish explicit explanatory PNGs.
They never invent a phase trajectory. The manifest carries the capture geometry
binding digest when available; missing geometry does not prevent relative-phase
extraction and is never treated as calibration.

The independent namespace is `scanner-adaptive-relative-phase-v1`. Existing phase
V1/V2 and GLRT contracts are unchanged. Source manifest and GLRT configuration
digests bind every phase product. Reads are metadata/PNG-only and never initiate
IQ analysis. Immutable files, no-follow directory handles, checkpoint seals, and
artifact hashes reject stale or substituted results.

API routes (automatic profile defaults to `probe_stride_ms=120`):

```text
GET /api/v1/scanner/adaptive-sessions/{session_id}/analysis/relative-phase
GET /api/v1/scanner/adaptive-sessions/{session_id}/analysis/relative-phase/{name}.png
    ?binding_sha256=sha256:...&artifact_sha256=sha256:...
```

The adaptive analysis panel polls metadata and displays both registered PNGs.
Manual saved-IQ replay, useful for bounded repair or verification:

```bash
python -m leo.cli.adaptive_relative_phase --bulk-root /srv/bulk/leo \
  --session-id scan-hop-e46d3aba244cf641 --maximum-seconds 120
```

Repeat only while the result says `partial`. `complete` is idempotent and verifies
its published PNGs without rerunning science. A failed scientific fit is recorded
as insufficient signal; source corruption or publication failure is an error.

Pre-deployment real-data verification produced both PNGs for:

| Scan | Selected | Broadband-supported | With later pilot comparisons |
|---|---:|---:|---:|
| `scan-hop-e46d3aba244cf641` | 64 | 63 | 64 |
| `scan-hop-f6f9037314e87e27` | 64 | 59 | 64 |

The production estimator reproduces visit 588's 8.90° A/B scatter. Its matched-pilot
discrepancy is 3.16° versus 3.28° in the report, because production computes the
physical common-band filter instead of retaining that report's fixed band edges.
These statistics are inter-method agreement, not errors against geometric truth.
No RF was collected for this verification. Known-template tests cover upper/lower
edges at 2.5 and 10 MS/s; real-data verification above is at 2.5 MS/s.

The feature-103 capture format is admitted through new V6 analysis/history
products and a V5 mixed history page. This preserves the original contracts,
native 2.5/10 MS/s rates and zero-gap consecutive visits. Cancelled receipts
expose only their complete retained visits. Previously these captures reached
the legacy rate validator and made the entire adaptive history request fail
with 409. The regression exercises source reading, checkpoint/resume, overview
and phase PNG publication, and HTTP retrieval for a zero-gap 10 MS/s fixture.

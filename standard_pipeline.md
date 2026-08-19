# Standard Analysis Pipeline — Working Record

Status: recorded design direction; not yet the production Standard pipeline.

This document preserves the analysis sequence agreed during the August 2026
single-recording investigation so it can be reviewed and implemented later.
It does not change pipeline contracts, releases, jobs, catalog state, or the
read-only UI.

## Development policy

- Reuse immutable recordings already on disk before collecting more radio IQ.
- Prefer lean, bounded analysis iterations. A development capture may pause for
  up to 30 minutes when new IQ is genuinely needed, but multi-hour or 24-hour
  radio campaigns are not an early-development prerequisite.
- Pilot and QAM results remain candidate-only. They do not establish Starlink
  specificity, attribution, payload recovery, or calibrated production
  acceptance.
- Every scientific score is paired with a same-IQ negative control where the
  method supports one.

## Proposed Standard sequence

### 1. Waterfall

Produce a frequency-versus-time PNG for the complete recording:

- frequency on the horizontal axis;
- elapsed recording time on the vertical axis;
- stable physical frequency labels derived from the applied receiver tune;
- bounded FFT/time aggregation suitable for a 60-second, 2.5 MS/s dwell; and
- provenance binding the PNG to session, stream, receiver, manifest digest,
  sample geometry, and renderer configuration.

Current exploratory producer:

```console
uv run --with 'matplotlib>=3.10,<4' \
  python tools/analyze_recording_waterfall.py SESSION_ID
```

### 2. Windowed pilot and QAM search

Use the existing schedule:

1. divide the recording into configurable coarse chunks (currently 1 second);
2. divide each coarse chunk into 50 ms subwindows;
3. analyze the first 20 ms of each subwindow;
4. process coarse chunks in a bounded process pool; and
5. preserve the same probe identity and timestamp across every method.

The common acquisition stage supplies a candidate frame epoch and coarse CFO.
Each confirmer then scores the same IQ, epoch, and CFO. The exact Qin edge-pilot
code is compared with a 17-symbol-rolled same-IQ control.

Produce one PNG per approach plus a bounded comparison PNG and numerical CSV:

- Anchor-8 conditioned relative phase;
- adjacent differential-16;
- adjacent differential-32;
- GLRT-32 residual-CFO search;
- GLRT-64 residual-CFO search;
- legacy-style edge-pilot noncoherent score;
- current full-frame symbolwise score; and
- known-symbol QAM hard-symbol accuracy/EVM.

These are confirmer curves conditioned on common acquisition. They must not be
presented as eight independent blind searches.

Current exploratory producers:

```console
uv run --with 'matplotlib>=3.10,<4' \
  python tools/analyze_edge_pilot_qam_timeline.py SESSION_ID --workers 4

uv run --with 'matplotlib>=3.10,<4' \
  python tools/compare_edge_pilot_methods.py SESSION_ID --workers 4
```

### 3. CFO versus time and continuous track segmentation

Construct timestamped candidate certificates from the windowed search. At
minimum each point carries:

- session/stream/receiver and probe identity;
- elapsed time and exact sample interval;
- acquired epoch and coarse CFO;
- method-specific residual CFO and resulting refined CFO;
- exact and rolled-control scores and their margin;
- support/uncertainty fields; and
- QAM accuracy/EVM when available.

Plot CFO versus time and split candidates into approximately continuous tracks.
Never bridge unrelated CFO branches merely because both have strong pilot/QAM
scores. Initial linking may use explicit time-gap, frequency-jump, slope, and
curvature gates, followed by separately reviewed endpoint-predicted tracklet
stitching across longer missing intervals. The intended later design supports
multiple simultaneous tracks through prediction, gated assignment, track
birth/death, missed-window tolerance, and immutable per-track provenance.

The current input has only one retained acquisition winner per probe. It can
test linking and outlier rejection, but it cannot prove multi-target
disentanglement when two real tracks coexist at the same timestamp. The future
candidate contract must retain multiple bounded candidates per probe before a
multi-track tracker can be qualified.

## Artifacts generated during the investigation

Reference recording:

- session: `production-24h-20260819-01-trial-00000132`;
- scope: `stream-0`, receiver `RX0`;
- duration/rate: 60 seconds at 2.5 MS/s; and
- manifest digest:
  `sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d`.

Generated beneath `artifacts/`:

- `production-24h-20260819-01-trial-00000132-stream-0-rx0-waterfall.png`;
- `production-24h-20260819-01-trial-00000132-stream-0-rx0-qam-timeline.{png,csv,json}`;
- `production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.png`;
- individual `pilot-methods-{anchor8,differential16,differential32,glrt32,
  glrt64,edge_tracker,symbolwise,qam_accuracy}.png` files;
- `production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods-cfo-track.png`;
- `production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.csv`;
  and
- `production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.json`.

Track-linking experiments subsequently add:

- `production-24h-20260819-01-trial-00000132-stream-0-rx0-glrt64-tracks.png`;
- individual `glrt64-tracks-{continuity,predictive,robust_quadratic,
  stitched_predictive}.png` comparisons; and
- a content/provenance sidecar `glrt64-tracks.json`.

The identical four-linker comparison is also rendered once per evidence family
as `{anchor8,differential16,differential32,glrt32,glrt64,edge_tracker,
symbolwise,qam_accuracy}-tracks.png`, with individual linker panels and a JSON
sidecar for every family. Differential and GLRT families add their residual CFO
to the common acquired CFO; the other families use the common acquired CFO and
only contribute their selection score.

Observed exploratory result: every pilot family independently highlights the
strong interval around 26–39 seconds, while a weaker and apparently separate
CFO branch is visible around 20–24 seconds. This agreement motivates track
segmentation; it is not itself a calibrated detection result.

Anchor-8 and current-symbolwise sensitivity experiments add
`{anchor8,symbolwise}-segment-recovery.{png,json}`. They compare the current
fixed gate, a negative-control-tail threshold, seeded hysteresis, cross-method
seeding, and a GLRT-64-seeded robust CFO corridor. The corridor exists because
the independently acquired symbolwise CFO can jitter by more than the strict
adjacent-point gate even when the aggregate ridge is coherent. On this
recording, GLRT-64 seeds plus an 8 kHz robust residual corridor and 0.6-second
miss tolerance recover a candidate tracklet from 6.20 to 9.65 seconds. This is
method fusion for candidate generation, not a calibrated symbolwise detection.
The companion `glrt-symbolwise-segmentation.{png,json}` keeps the distinction
explicit: pure GLRT-64 segments its residual-refined CFO, pure Symbolwise grows
five-sigma verification seeds through positive-margin points inside its own CFO
corridor, and a third panel shows the fused result for comparison.

## Before production implementation

Review and freeze:

- the bounded multi-candidate-per-probe contract;
- detector thresholds from labeled/replayed evidence rather than this one
  recording;
- uncertainty propagation from epoch/CFO search into track gates;
- multi-track assignment, merge/split, birth/death, and gap policy;
- exact presentation schemas and UI semantics;
- product provenance, release binding, idempotence, and retention; and
- adversarial tests for noise, controls, crossing tracks, parallel tracks,
  intermittent occupancy, CFO ambiguity, and false branch connection.

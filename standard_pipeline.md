# Standard Analysis Pipeline — Working Record

Status: the all-method polynomial trajectory-feedback loop is implemented as an
additive Standard/Research stage. Its products remain candidate-only and need
more recordings before thresholds can be calibrated.

This document preserves the analysis sequence agreed during the August 2026
recording investigation. The first iteration used one receiver path; the
four-path replay below now covers both receivers on both radios in the same
committed recording. It does not change pipeline releases, jobs, catalog state,
or the read-only UI.

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
3. analyze 20 ms probes starting at offsets 0 and 25 ms in each subwindow;
4. process coarse chunks in a bounded process pool; and
5. preserve the same probe identity and timestamp across every method.

Every one of the resulting 2,400 probes/path in a complete 60-second recording
independently searches the full -400 to +400 kHz acquisition
range; a coarse result from the surrounding one-second chunk or another 50 ms
subwindow must never seed it. Within one probe, the common acquisition result
supplies the candidate frame epoch and CFO to each confirmer, so GLRT64,
Symbolwise, Anchor-8, and QAM remain directly comparable on the same IQ and
hypothesis. The exact Qin edge-pilot code is compared with a 17-symbol-rolled
same-IQ control. Search mode and bounds are immutable configuration/cache
identity.

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
  python tools/analyze_edge_pilot_qam_timeline.py SESSION_ID --edge lower --workers 4

uv run --with 'matplotlib>=3.10,<4' \
  python tools/compare_edge_pilot_methods.py SESSION_ID --edge lower --workers 4
```

Run both commands once for each exact `(stream_id, receiver_id)` path. Do not
treat four receiver paths as four independent captures when they came from one
dual-radio manifest.

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

### 4. Trajectory-conditioned feedback detection

Every detector family independently contributes observations to linear,
quadratic, and cubic iterative track fitting. Near-duplicate fitted curves are
grouped into trajectory families before replay so equivalent method/order fits
do not cause a combinatorial explosion.

For each retained family representative, Standard analysis now:

1. evaluates its polynomial CFO continuously over the candidate support;
2. analytically integrates that frequency polynomial into phase;
3. dechirps the original immutable IQ probe with that phase model;
4. reacquires in a narrow residual-CFO domain around zero; and
5. reruns Anchor-8, differential-16/32, GLRT-32/64, edge tracker,
   symbolwise, and QAM accuracy on the corrected probe.

The first and feedback passes operate in bounded parallel one-second batches.
The analyzer rereads IQ for the feedback pass and never materializes one full
corrected recording per trajectory. Persisted products retain per-probe
baseline/corrected margins and the exact family, method, polynomial order, and
sample identity. They remain candidate-only: increased response after a fitted
correction is evidence of CFO coherence, not Starlink attribution.

GLRT-64 is the primary Standard tracking lane. Other methods remain in the
scientific products as corroborating diagnostics, but a GLRT-64 member is
preferred as each deduplicated family's correction representative whenever one
exists. Standard publishes two additional durable artifacts:

- `starlink.glrt64-trajectory-table`, a scientific JSON table containing each
  linear/quadratic/cubic model's reference time, highest-power-first CFO
  coefficients, support interval, point count, residual RMS, BIC, EM iteration
  count, fit-quality flag, correction-selection flag, and paired replay gain;
  and
- `starlink.glrt64-trajectory-plot`, an immutable full-dwell PNG showing initial
  GLRT-64 response, each trajectory-corrected response, initial CFO points, and
  labeled well-matched linear/quadratic/cubic fits. Thick fits are the models
  actually replayed.

The table defines frequency as
`cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)`, allowing later
processing to reconstruct the correction without interpreting the PNG.

### 5. Four-path recorded-time comparison

For a dual-radio/dual-RX recording, render the four path results as four rows
with one shared x-axis. Convert a path-local probe time using:

`shared_time_s = (path_first_estimate_utc_ns - earliest_first_estimate_utc_ns) / 1e9 + local_time_s`.

The x-axis spans the union from the earliest radio first-sample estimate to the
latest last-sample estimate. This preserves measured radio start skew. It does
not imply phase coherence: timing uncertainty, synchronization grade, and
`phase_coherent` remain explicit metadata. Each row contains the initial
GLRT-64 response, trajectory-corrected response, initial CFO observations, and
well-matched linear/quadratic/cubic CFO fits; thick fits are those replayed.

Current renderer:

```console
session=production-24h-20260819-01-trial-00000132
for path in stream-0:0 stream-0:1 stream-1:0 stream-1:1; do
  stream=${path%:*}
  rx=${path#*:}
  base=artifacts/${session}-${stream}-rx${rx}
  uv run python tools/analyze_edge_pilot_qam_timeline.py "$session" \
    --stream "$stream" --receiver "$rx" --edge lower --workers 2 \
    --output "${base}-qam-timeline.png"
  uv run python tools/compare_edge_pilot_methods.py "$session" \
    --timeline-csv "${base}-qam-timeline.csv" \
    --stream "$stream" --receiver "$rx" --edge lower --workers 2 \
    --output "${base}-pilot-methods.png"
  uv run python tools/run_trajectory_conditioned_redetection.py "$session" \
    --input "${base}-pilot-methods.csv" \
    --stream "$stream" --receiver "$rx" --edge lower --workers 2 \
    --output "${base}-trajectory-redetection.png"
done
uv run python tools/render_four_path_glrt64_feedback.py "$session"
```

It requires the four path-specific pilot-method CSV and trajectory-feedback
JSON documents, verifies their manifest/input bindings, and emits one PNG plus
a content-hashed JSON sidecar.

## Artifacts generated during the investigation

Reference recording:

- session: `production-24h-20260819-01-trial-00000132`;
- recording geometry: one committed dual-radio capture containing four paths,
  `stream-0/RX0`, `stream-0/RX1`, `stream-1/RX0`, and `stream-1/RX1`;
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

The same Waterfall -> windowed search -> all-method comparison -> trajectory
feedback sequence was subsequently run over all four receiver paths. The
four-path waterfall is
`production-24h-20260819-01-trial-00000132-four-path-waterfall.{png,json}`.
Each path has its own `qam-timeline`, `pilot-methods`,
`trajectory-redetection`, full-duration GLRT-64 PNG, and trajectory-table CSV.

Exploratory path summary:

| Radio / path | Positive 20 ms probes | Track hypotheses | Families | Replayed fits |
|---|---:|---:|---:|---:|
| `radio_pluto_5d4d` / `stream-0/RX0` | 233 | 60 | 4 | 3 |
| `radio_pluto_5d4d` / `stream-0/RX1` | 174 | 75 | 2 | 2 |
| `radio_pluto_19f2` / `stream-1/RX0` | 186 | 27 | 2 | 1 |
| `radio_pluto_19f2` / `stream-1/RX1` | 376 | 51 | 2 | 2 |

The positive-probe count uses the exploratory QAM/pilot gate and is not a
calibrated detection count. The combined shared-clock outputs are:

- `production-24h-20260819-01-trial-00000132-four-path-glrt64-trajectory-feedback.png`;
  and
- `production-24h-20260819-01-trial-00000132-four-path-glrt64-trajectory-feedback.json`.

For this recording, `stream-1` starts at estimated UTC ns
`1787121029924226035`; `stream-0` starts 1,425,210 ns later. The union is
60.001424810 seconds. The manifest reports degraded best-effort synchronization
and `phase_coherent=false`, so the shared clock is appropriate for comparing
second-scale trajectories but not for cross-radio phase combination.

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
`iterative-tracklet-em.{png,json}` then tests the proposed longer-track design:
robust local lines are initialized independently in fixed 1-second windows,
nearest endpoint/slope state proposes pairs, the best valid pair is merged and
quadratically refitted until convergence, and classification EM repeatedly
assigns each observation to one curve or to clutter before refitting. The thin
lines in the PNG are the original 1-second seeds; thick lines are final tracks.
The same diagnostic runs the full merge/assignment loop with both quadratic
and cubic Doppler models in a two-by-two comparison. Per-track BIC is recorded
alongside RMS so the cubic's inevitable residual reduction is not mistaken for
evidence that the additional curvature parameter is justified.

The all-method bank and feedback replay add
`trajectory-redetection.{png,json}`. On this recording the bank produced 60
method/order track hypotheses but only four distinct trajectory families. The
GLRT-64 quadratic representative over 6.2–9.7 seconds raised median GLRT-64
margin by 0.326 and median QAM accuracy by 0.219 after correction; the
symbolwise-only trajectory over the same region produced essentially no gain.
That paired result is why the Standard product preserves both hypotheses rather
than assuming that the first fitted CFO curve is correct.

## Before calibrated production claims

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

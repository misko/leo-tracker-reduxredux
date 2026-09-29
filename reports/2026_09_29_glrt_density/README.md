# GLRT density development pilot

Session: `scan-fw-2fab8e56185dc020`. Existing saved IQ only; no RF acquisition,
production settings, dataset membership, or published production artifacts changed.

## Measured result

**More lane tracklets, but no measured held-out accuracy improvement in this
pilot.** All windows below are 20 ms long.

| Main-analysis stride | RX-probes | Production lane tracklets | Paired held-out RMS | Paired availability |
|---|---:|---:|---:|---:|
| 120 ms, current | 442 | 9 | 547.52 Hz | 29/40 |
| 10 ms, dense | 4,862 | 13 | 552.34 Hz | 29/40 |
| 20 ms, control | 2,652 | 13 | 552.34 Hz | 29/40 |

The dense RMS is 4.82 Hz / 0.88% higher. The common panel has 29 receiver
observations from 21 held-out visits, across seven matched training tracklets.
Three tracklets improve and four worsen; some have only one or two reference
points. Equal-track-weight RMS also increases, from 512.03 to 519.18 Hz. Median
absolute error rises from 417.04 to 461.65 Hz; the 95th percentile absolute error
is 942.22 versus 936.82 Hz. These are descriptive statistics, without a population
confidence interval or claim that the small difference is significant.

All nine operational baseline tracklets match uniquely in each denser arm.
Each denser arm has four additional unmatched lane tracklets; their physical
identity and correctness are not established. The training-only fits have nine
baseline versus fourteen dense tracklets, with five additional unmatched dense
tracklets. Dense median operational track span is 16.54 s versus 25.26 s in the
baseline, reflecting a different track population; the larger track count alone
does not establish better continuity.

The 10/20 ms arms project **exactly the same 6,364 scientific candidate rows**.
Their track counts, supports, frequency intercepts and rates agree; one track's
reported fit RMS differs by only 1.14e-13 Hz due to floating-point ordering of
different provenance IDs. All paired held-out predictions agree exactly. The
10 ms arm has 11,692 passing candidate hypotheses before overlap filtering;
5,328 of these additional hypotheses are filtered out before tracking.

Of the 40 eligible references, six lack a spanning baseline training track,
four have ambiguous baseline track spans, and one falls outside the fixed
canonical prediction branch. All arms score the remaining 29. This preserves
the same denominator and avoids selecting held-out candidates by residual.

The measured dense replay took **1,040.43 seconds (17.34 minutes)** with at most
two CPU workers, 1,694.76 CPU seconds, and a peak 303,760 KiB RSS. The six track
fits total 15.74 seconds. The successful final validation/fitting/rendering stage
took 43.98 seconds including five of those fits; there was also a short validation
retry and final plot refresh. Detector replay extrapolation gives roughly **174
minutes for this entire five-minute scan**, or 23.2 hours for eight similar full
scans. Those are projections, not launched work. The 20 ms control was derived
from the dense results, so no independent whole-panel 20 ms runtime is claimed.

All **61 existing WebUI PNG routes** returned HTTP 200 and image/png, with valid
PNG signatures, matching byte counts and manifest hashes: three GLRT, two phase,
and 56 tracking/position artifacts. The main analysis binding still matches the
frozen baseline binding. There is no pre-experiment byte snapshot for this scan's
entire PNG inventory; the checks establish current publication integrity, not a
byte-for-byte before/after comparison. Thirteen protocol/runtime tests pass.

**Decision:** this pilot does not support changing production to 10 ms stride
for accuracy. The unchanged tracker gains no additional frequency observations
from its overlap compared with 20 ms stride. Wider coverage does reveal additional
candidate segments, which need independent validation before claiming improved
tracking. The proposed 10% accuracy-improvement criterion is not met by this
pilot's point estimate, and confirmation-level statistical gates remain untested.

## Scope and reproducibility

The original frozen specification contains 60 seconds. Before comparing dense
outcomes, the measured first-dwell cost triggered a documented reduction to the
first **30 seconds**; see `protocol-amendment.md`. This complete chronological
panel has **221 visits**, all actually 120 ms long, at 5 MS/s, both receivers,
upper CH1–4. Preserve the original partition: 181 training visits and 40 held-out
visits. Both receivers and every window within a visit share its partition.

All three arms use 20 ms probes and the pinned deployed worker implementation
`47e2705e437722daa5e6d6bb1c252d54b7a21dbc`. Strides are 120 ms (current main
analysis), 10 ms (proposed dense), and 20 ms (coverage control). The 20 ms control
is derived from the even dense windows, with fresh replay equivalence checks.
The experiment explicitly constructs the public `TrackingInput` port for each
arm and invokes unchanged `project_scanner_candidates` and
`reconstruct_persistent_hop_trajectories`. It does not use the normal tracking
store's hard-coded 120 ms analysis selection for dense inputs.

The production projector skips overlapping probes. Thus the 10 ms arm's starts
at 10,30,50,70,90 ms do not reach production tracking. This is a property of the
existing pipeline, not an experimental optimization or change. Candidate counts
include multiple hypotheses and must not be read as independent detections.
Production lane tracklets here are different objects from the strongest-per-visit
associations in the original GLRT overview screenshots. Physical group counts,
where shown, are diagnostic; primary matching never combines channels or RXs.

## Accuracy protocol

`references.json` was frozen before opening fitted predictions. It contains all
80 held-out visit/RX opportunities and their candidate hypotheses. Forty have
one eligible frequency cluster; 27 have no passing candidate and 13 have multiple
frequency clusters. The reference is the highest-margin candidate within the
sole cluster, selected independently of every fitted trajectory.

Tracks are matched using training-time lane, span, and predictions only. Splits,
merges, and ambiguous matches remain in `track-correspondence.json`. A reference
is scored only when exactly one baseline training track spans its time, and the
arm has an unambiguous matched track spanning that time. Track alias offsets are
fixed from training; predictions outside that fixed canonical branch are counted
as unavailable, with no test-time frequency wrapping or best-candidate selection.

Paired RMS uses the same reference observations in every arm. Availability uses
all 40 eligible references as its denominator, and is **availability of the
paired, baseline-track comparison**, not a count of every possible dense-only
discovery. Additional discoveries are visible in the operational track metrics.
`scores.json` preserves every excluded/failed case; `per-track-rms.csv` separates
the track-level results. Frequencies are normalized to the production tracker's
11.2 GHz RF reference.

These are alias-conditional, held-out **CFO trajectory prediction errors**.
They are not TLE-based residuals, absolute Doppler errors, surveyed positioning
accuracy, or proof of satellite identity. No catalogue matching, randomized TLE
evaluation, or position fit was run in this pilot. The selected-dwell relative
phase stage was not rerun or changed.

This scan was selected after viewing strong tracks. One 30-second development
excerpt cannot establish population accuracy, uncertainty intervals, or the
proposed confirmation acceptance gate. The eight-recording confirmation panel,
other sample rates and real 240/360 ms dwells remain untested scientifically;
synthetic schedule checks cover all supported rate/dwell combinations.

## Artifacts and checks

- `comparison.html`: standalone local comparison page.
- `glrt-response.png`: identical axes, winning candidate per probe/RX.
- `cfo-tracks.png`: all passing candidates and production lane tracklets.
- `heldout-rms.png`: paired errors and prediction availability.
- `summary.json`, `scores.json`, `per-track-rms.csv`: measured outcomes.
- `runtime.json`: measured replay resources and explicitly extrapolated costs.
- `validation.json`: shared-window checks and live production PNG HTTP/digest checks.
- `artifact-manifest.json`: PNG hashes bound to specification and reference hashes.
- `dense-control-equivalence.json`: 10/20 ms track-value comparison.

The research page is local, not registered as a completed full-scan WebUI product.
Existing production GLRT, phase, and tracking PNG routes are checked separately;
this avoids misrepresenting a 30-second research excerpt as full-scan analysis.

The `local/` directory contains resumable visit products, fit outputs and timings
and is ignored by Git. Source IQ stays in its existing read-only store. All
hand-written research code is confined to this directory. Thirteen protocol and
pinned-runtime tests cover schedules, configuration routing, overlap selection,
source-span separation, reference ambiguity, aliases, matching, and empty tracks.

Run scripts with the pinned release's `.venv/bin/python`, using read permission
for `/srv/bulk/leo`, and `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
MKL_NUM_THREADS=1`. `run.py run --limit 50 --seconds 250` resumes a bounded dense
batch; it must have an outer 295-second timeout. Never rerun `freeze` or `prepare`
over the existing frozen tables. `evaluate.py fit --arm STRIDE --partition
training|operational` refuses to overwrite frozen models. `validate.py`,
`evaluate.py score`, and `render.py` produce the verification and report outputs.
The initial pilot has a 20-minute compute budget; do not automatically expand it
to full recordings or the confirmation panel.

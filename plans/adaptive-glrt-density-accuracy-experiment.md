# Does denser GLRT improve tracks and held-out Doppler agreement?

Status: bounded 30-second development pilot completed, 2026-09-29. Results,
execution receipts and the compute-driven scope amendment are in
`reports/2026_09_29_glrt_density/README.md`. Paired held-out RMS was 547.52 Hz at
120 ms stride versus 552.34 Hz at both 10/20 ms; lane tracklets increased from
9 to 13. The unchanged production projector discards overlapping probes, making
the 10/20 ms scientific inputs identical. The broader confirmation experiment
below remains proposed; no production deployment has been launched.
Use existing saved IQ only. The experiment does not change automatic acquisition,
production analysis, dataset membership or scientific golden fixtures.

## Question and hypotheses

Compare the deployed main analysis (20 ms windows / 120 ms stride) with 20 ms
windows / 10 ms stride on identical recordings. Determine whether denser
observations improve track availability and prediction of unseen frequency
measurements, and quantify the compute cost. Lower training residual alone is
not evidence of better accuracy.

Denser analysis may recover signals missed by sparse probes, reduce fragmentation
and stabilize frequency/trajectory estimates. It can also admit more false
candidates, overweight correlated overlapping windows and make model selection
look better without improving prediction. A 20 ms probe's intrinsic information
does not increase merely because neighboring probes are added.

## Three frozen arms

| Arm | Probe length | Stride | Probes per RX in 120/240/360 ms dwell |
|---|---:|---:|---|
| A: current production | 20 ms | 120 ms | 1 / 2 / 3 |
| B: proposed dense | 20 ms | 10 ms | 11 / 23 / 35 |
| C: coverage control | 20 ms | 20 ms | 6 / 12 / 18 |

A versus B is primary. C tests whether any improvement comes mainly from
covering more recorded IQ, or specifically from overlapping windows. B versus C
is secondary; do not pick the headline comparison after looking at results.

Freeze one detector implementation, candidate limit, score threshold, frequency
search, receiver treatment, time authority, LNB convention, tracking configuration,
catalogue snapshot and position reference for all arms. Use the same source and
calibration digests. Keep the selected-dwell phase replay out of the primary
comparison: it is a separate operation, already using 20 ms stride, and does not
produce the main trajectory input. If exercised for compatibility, leave it
unchanged in all arms and report its cost separately.

## Start with the scan already discussed

`scan-fw-2fab8e56185dc020` is the development example: 5 MS/s, two receivers,
2,216 actual 120 ms visits over approximately five minutes, upper edges CH1–4.
The existing main analysis contains 4,432 receiver-probes. B schedules 48,752;
C schedules 26,592. These are scheduled windows, not independent measurements.
The dense count is eleven times the baseline; elapsed cost must be measured.

This scan was chosen after seeing strong tracks. It is suitable for an
illustrative comparison and debugging, not an unbiased population claim.

First profile a fixed chronological excerpt containing all channel visits and
enough elapsed time to support the normal track-span gates. Freeze a 60-second
excerpt starting at recording time zero before running the dense arm. Do not
select only its strong channels or expand it because an outcome is attractive.

For confirmation, freeze a separate metadata-selected panel before reading dense
results: target two recordings from each of 2.5/5/7.5/10 MS/s, across distinct
time blocks and both edges where available. Stratify by *actual* dwell lengths,
not the configured active dwell maximum. If the available corpus lacks 240/360 ms
visits, explicitly restrict the scientific claim and cover those schedules with
synthetic/component tests; do not claim real-data coverage of absent strata.
Record exact sessions, source digests and selection seed in a sealed manifest.
Eight recordings are a small confirmation panel, not proof of generalization.

## Two complementary evaluations

### Operational comparison: what would the standard pipeline display?

Run the unchanged tracking/association logic on each arm's full observations.
Verify that it consumes the requested metrics digest: the current adaptive
tracking reader hard-codes 120 ms and must receive an explicit configuration
through a narrow input port for this experiment. Do not point the ordinary CLI
at dense outputs and assume it reads them. Reuse the same algorithm, not a
separately tuned dense tracker. Keep output namespaces separate by arm.

Report tracks, span, coverage by target/RX, fragmentation, gaps, ambiguous or
duplicate associations, support and abstentions. Distinguish overview plot
associations from production tracking/TLE groups. The overview fitter selects
only the strongest passed candidate per visit/RX, whereas its scatter plot shows
all passing candidates; more dots do not automatically mean more track evidence.
Audit and report the production tracker's observation selection too.

Freeze a deterministic one-to-one track matching rule on same target, edge and
receiver, using training-time overlap and compatible training frequency branches.
Never join RXs/channels/edges to improve counts. Retain splits, merges, unmatched
tracks and ambiguous matches as outcomes; a union of baseline/dense discoveries
is not independent truth. A higher raw track count alone is not a win.

Keep the production randomized-evaluation RMS as a compatibility diagnostic,
clearly separated from the more stringent paired evaluation below. Different
observation identities and overlapping windows make its values insufficient as
the primary cross-arm accuracy metric.

### Paired evaluation: do the tracks predict unseen measurements better?

Before fitting, reserve 20% of whole visits with a frozen seeded assignment,
stratified by target and actual dwell duration. Put both receivers and **every
window from each visit in the same partition**. Include source byte/sample spans
in the partition receipt and assert zero shared training/evaluation IQ. All arms
use exactly the same visit partition. Do not split alternating 10 ms probes.

Discover tracks, choose satellite candidates, choose alias branches, and fit
frequency offsets/time corrections using training visits only. Then freeze all
model outputs before scoring. Track identity numbers are not stable across arms;
match using the predeclared training-only rule. No held-out refit, candidate
reranking, degree selection or alias optimization is permitted.

Build one reference observation set for the withheld visits: 20 ms probe at the
start of each visit, identical for every arm, using a pinned detector and a
predeclared quality/uniqueness rule independent of the fitted arms. Preserve all
candidate hypotheses and abstain on ambiguous reference identity rather than
choosing whichever held-out candidate minimizes an arm's residual. Freeze this
reference table before opening the arm predictions. This is an independently
processed measurement of held-out IQ, not noiseless frequency ground truth.

Compare each arm's frozen trajectory prediction with these same reference
observations in Hz. Fix frequency normalization and alias convention before
scoring; do not use modulo wrapping to hide a wrong predicted branch. Report
branch failures explicitly. Where unwrapped identity is not established, label
the comparison as alias-conditional and report its restricted coverage.

For TLE-based Doppler, compute measured-minus-predicted residual using the same
site/time/orbit inputs and only training-fitted constant frequency offset per
track. Keep higher-order residual corrections out of the primary metric. Report
both matched tracks with agreeing candidate identity and the full operational
result, including identity disagreements. Catalogue predictions and the
unsurveyed receiver site are imperfect references, not absolute Doppler truth.

Primary error statistic per matched track is:

`RMS_Hz = sqrt(mean((heldout_frequency_Hz - frozen_prediction_Hz)^2))`.

Use the identical held-out measurement panel for paired error comparisons.
Alongside common-support RMS, report prediction availability over **all** frozen
eligible references. An arm must not obtain a lower headline RMS by dropping
difficult observations. Missing tracks, failures, ambiguous matches and loss of
qualification remain in the ledger, with counts and reasons.

Compute paired per-track changes, then give equal weight to recordings when
summarizing. Report median and upper-tail errors and wins/losses by recording;
do not let a dense arm dominate by contributing more correlated points. For the
confirmation panel, cluster uncertainty by recording/time block, not individual
probe. The development scan alone supports descriptive results only.

## Interpretation and decision rule

Before confirmation, freeze practical acceptance thresholds. Proposed defaults:
at least 10% improvement in the recording-balanced held-out RMS statistic,
no more than a two-percentage-point loss of reference prediction availability,
and no more than 10% deterioration in the recording-balanced upper-tail RMS.
Require the paired uncertainty interval to favor an improvement; otherwise
report inconclusive, rather than promoting the favorable point estimate.
Inspect false/ambiguous tracks and unmatched failures even if the RMS gate passes.

Report RMS change in Hz as well as percentage, and compute seconds per scan,
CPU seconds, peak memory, bytes read/written and time until plots are ready.
Whether a measured scientific gain justifies elevenfold probe density is a
separate engineering decision. If C performs comparably to B at lower cost,
report that directly rather than recommending overlap automatically.

This experiment can establish better held-out CFO/Doppler agreement and track
availability under the stated reference assumptions. It cannot by itself prove
better geographic positioning, surveyed accuracy, or correct satellite identity.
A position claim needs a separately specified position evaluation.

## Bounded execution and outputs

Use separate report-local analysis/output roots and public read-only IQ readers.
Reuse baseline metrics only after matching source, implementation and all
configuration fields. Match shared windows by absolute source sample span,
target and RX, not probe index. Verify shared-window candidate scores agree
within predeclared numerical tolerances before comparing downstream results.

Limit each compute batch to five minutes, one job at a time, at most two CPU
workers, with an outer wall-time/resource cap covering rendering too. Limit the
initial profile and excerpt study to 20 minutes total. At that point report
measured results and projected full-scan/panel cost. If further work would turn
into a multi-hour campaign, stop expansion and propose a smaller defensible
panel; do not launch all dense full scans or wait on production queue completion.
No new RF collection is part of this experiment.

Required artifacts:

- Frozen experiment specification, input/partition/reference manifests and hashes.
- All-arm GLRT and CFO plots with identical axes and shared-window overlays.
- Track correspondence table including unmatched/split/merged/failed cases.
- Paired held-out residual plots and per-track/per-recording RMS/coverage tables.
- Runtime/resource report and explicit limitations/decision gate results.
- Correctly bound PNG manifests and HTTP checks for any published comparison page;
  display research comparisons separately from standard production artifacts.

Component tests must cover configuration routing, shared-window equivalence,
zero-overlap partitions, frozen scoring, alias/identity ambiguity, empty tracks,
and failure-denominator preservation. Production compatibility tests must ensure
the existing 120 ms pipeline and historical PNG URLs remain intact.

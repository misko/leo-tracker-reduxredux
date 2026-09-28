# DS7 third chronological group and prior-only context

The predeclared `group8-03` achieves 507.90 m with lowest-training-RMS 75%
averaging, 602.57 m with inverse-RMS-squared averaging, 687.64 m with the joint
Doppler fit, and 984.89 m with equal averaging. All eight independent fits and
the joint fit converge with interior solutions and no eligibility exclusions.
These results extend evaluation coverage to 32 of 88 recordings and four of
eleven chronological groups. The full88 result remains untested.

An important coordinator-only context check found that the inherited DS6
starting coordinate is already **809.03 m** from the DS7 reference without
using observations. Consequently, crossing 1 km alone does not demonstrate
improvement beyond prior site knowledge. Three methods in this new group
improve on that fixed-coordinate distance; equal averaging does not. This
check did not alter model parameters, membership, starts, preparation or weights.
[Diagnostic specification](coordinator-prior-check.md) and
[source-bound result](coordinator/prior-center-diagnostic.json).

| Frozen method | Group 1 | Group 2 | Group 3 (new) | Group 11 |
|---|---:|---:|---:|---:|
| Equal independent-position mean | 1,930.07 m | 628.67 m | 984.89 m | 443.02 m |
| Inverse training-RMS-squared mean | 2,152.44 m | 601.07 m | 602.57 m | 602.41 m |
| Mean of lowest-RMS 75% | 2,532.71 m | 836.50 m | 507.90 m | 446.91 m |
| Joint static-site Doppler fit | 2,541.48 m | 887.79 m | 687.64 m | 1,322.09 m |
| Fixed inherited coordinate (no observations) | 809.03 m | 809.03 m | 809.03 m | 809.03 m |

The fixed-coordinate row is a post hoc diagnostic of existing prior knowledge,
not another fitted model or a substitute for full88. These are four temporal
groups at one exposed site; they cannot establish a population model ranking.
The original first-group failure remains part of the evidence.

## Complete new panel

All chronological singles 017–024 were retained. Errors in order are
1,334.34, 4,195.01, 3,523.74, 402.81, 1,391.72, 5,625.68, 2,873.12 and
2,627.19 metres. One of these eight singles is below 1 km; three of the 32
distinct singles evaluated so far are below 1 km. There are 474 eligible tracks
in the complete new group, with no excluded tracks.

The group was selected by the next missing chronological partition before
prediction or scoring. All three controls used the same eight qualified source
fits and the unchanged training-only RMS definition. The 75% rule retained six
according to its original RMS policy. Root checked every control input against
its sealed request, response and source-run inventory before aggregation.
No member or weight was selected from geographic error.

Evidence: [joint and final single](coordinator/group03-completion-score-v1/scores.json),
[equal mean](coordinator/controls-equal-group03-score-v1/scores.json),
[inverse RMS](coordinator/controls-inverse_rms2-group03-score-v1/scores.json),
[lowest RMS 75%](coordinator/controls-lowest_rms75-group03-score-v1/scores.json),
[source audit](coordinator/controls-group03-source-audit.json),
[panel terminal receipt](solver/group8-03-terminal-receipt.json).

## Execution and integrity

The unchanged scientific model ran through the optional batched adapter whose
wave-4 first-eight response was byte identical to the original. The new panel
used 267.752 of 900 adapter seconds; the group fit used 140.558 seconds of its
300-second cap. No new model code or scientific configuration changed here.

Preparation completed all eight captures within its original lease: 917.17
seconds controller wall time, versus 884.538 seconds summed recording reports.
All eight operations exited zero. An initial index copied from a frozen-input
document was rejected for the wrong schema before publication; it remains as
an explicitly superseded draft, and a valid input index supplied every final
snapshot. No scientific output or failed attempt was overwritten.

The [independent input audit](inputs/INPUT-INTEGRITY.md) verifies all 96 ready
artifact hashes, all 88 ordered source identities, exact preservation of the
previous 24 ready records, and the new bank coverage and timing grids. All 258
wave-4 closeout bindings remain unchanged, retaining its 91-test validation
baseline. The new report-local resource script passes Ruff; no model-code
changes required another scientific regression run.

## Full88 resource evidence and remaining work

A separately bounded measurement loaded 24 real captures and evaluated one
unfitted donor objective. It used 1.648 GiB peak RSS and 5.056 seconds for the
objective/gradient call. Linear full88 projections are roughly 6 GiB peak RSS
and 18.54 seconds per call. A separately bounded 8 GiB/1,800-second attempt
appears plausible near 63 evaluations, but a 95-evaluation path leaves no
credible overhead margin. Neither projection establishes convergence for the
90-parameter full problem. [Resource evidence](resource-readiness/REPORT.md).

The [full88 specification](../2026_09_27_ds7_full88/FULL88-SPEC.md) fixes complete
membership, the four observation-based estimators, resource gates, sealing and
scoring before that evaluation. At this wave's final input, 32 recordings are
ready and 56 remain unprepared. Separately bounded wave-6 workers are preparing
groups 4 and 5 in parallel; their later results do not change this sealed wave.
The [cumulative control input](coordinator/controls-cumulative32-inputs.json)
also preserves all 32 available independent estimates and all 56 missing
members explicitly. No pooled partial-32 estimate was evaluated as full88.

All distances use the unchanged great-circle metric against an unsurveyed
operator reference at one already exposed site. The fixed-coordinate baseline
must accompany any eventual sub-kilometre claim. The full-DS7 goal remains open.

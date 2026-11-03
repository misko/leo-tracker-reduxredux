# Recency alone does not consistently predict the later window

The newer middle-eight source fit outpredicts the early-eight source fit on
late scans only in DS7. Pooling early and middle into 16 scans improves reference
error in all datasets, but improves later prediction over early-only in DS7
and DS8, not DS9. Do not promote a universal recent-window or cumulative-data
rule from this comparison.

| Dataset | Middle8 minus early8 late score | Middle wins / 8 | Cumulative16 minus early8 | Cumulative wins / 8 | Cumulative16 minus middle8 |
|---|---:|---:|---:|---:|---:|
| DS7 | +1,107.399 | 5 | +668.000 | 6 | −439.399 |
| DS8 | −9.291 | 3 | +211.158 | 8 | +220.449 |
| DS9 | −155.296 | 4 | −90.149 | 3 | +65.147 |

Scores are summed predictive log likelihoods over the same eight late scans
within each dataset. Positive differences are better. The aggregate winning
arm differs: middle-only in DS7, cumulative in DS8, early-only in DS9. These
outcomes are descriptive; choosing that winner separately after seeing targets
would not be a validated source-only policy.

## Geographic diagnostic remains distinct

| Dataset | Early8 reference error | Middle8 reference error | Cumulative16 reference error |
|---|---:|---:|---:|
| DS7 | 2,286.0 m | 1,201.8 m | **643.8 m** |
| DS8 | 1,435.7 m | 2,130.8 m | 1,091.7 m |
| DS9 | 639.5 m | 841.8 m | **382.4 m** |

These are individual fitted estimates against the inherited exposed, unsurveyed
reference, not blind absolute accuracy measurements. Cumulative16 has smaller
reference error than either eight-scan source in every dataset, yet does not
win every predictive comparison. DS9 is the clearest example: lower reference
error accompanies lower late score than early-only. Neither metric should be
silently substituted for the other.

## Design and checks

The [protocol](PROTOCOL.md) predates execution. Source membership is the existing
early8 and middle8 blocks of the frozen 24-scan source pool. All source scans
finish before the first late target begins, and source/target session IDs are
disjoint. These are sparse windows across a day, not contiguous acquisitions.
The late recordings have appeared in other research; this temporal holdout is
not a previously unseen validation corpus.

The early and middle controls reuse their qualified six-start original q020
fits after session-ID and training-score replay checks. The new cumulative16
fit uses three cold E starts (−2,0,+2 km) and three matching training-only
timing-grid starts. Choose the highest qualified training likelihood, without
late scores or the reference. Cumulative source fits are saved before target
evaluation.

Evaluate all three fixed locations on every late scan under the same original
q020 retained-bank model. Integrate one shared timing offset per target scan
over −5 to +5 seconds; no timing or frequency correction is transferred from
source scans. No target is omitted or used to refit a location.

All 18 new source starts qualify. All 72 target integrals qualify without
refinement; maximum 16/32-order quadrature difference is 0.004912 log units.
Source bindings and training replay checks pass. A partition test verifies
rejection of source/target temporal overlap. Ruff passes. All three workers
exit zero in 178–196 seconds, under 300-second caps.

## Consequence for the sub-km effort

The present evidence does not support treating cross-time disagreement as a
single monotonic calibration drift that can be handled by always using the
latest window. More data can improve geographic agreement without consistently
improving prediction, and recency itself can help or hurt. The comparison also
changes satellite geometry and measurement populations, so it does not isolate
a physical cause of the temporal differences.

Retain the cumulative-source results as an evaluated method, but do not turn
the dataset-specific winners into a deployment rule. A useful next policy would
need source-only validation to choose its history length, followed by genuinely
reserved later data; success on repeatedly examined targets would remain
exploratory. Independent position and clock evidence are still needed for
calibrated absolute accuracy.

See [summary](summary.json), [runner](run.py), cumulative source checkpoints and
per-dataset raw target comparisons. No RF collection, production changes or
publication occurred. Artifacts are local. Reproduce with `batch.py prepare`,
`batch.py run` and `summarize.py` under NumPy/SciPy in a fresh output context.

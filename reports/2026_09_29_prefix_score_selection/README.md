# Earlier 12-scan scouting preserves compression, not consistent sub-km accuracy

The unchanged score-balanced selector compresses each earlier 12-scan source
fit to eight scans within 36–54 metres. However, the selected-eight fits are
below 1 km against the inherited reference in only DS9. Later-scan prediction
improves against the earliest-eight baseline only in DS7. Do not interpret the
preceding 24-to-eight compression result as evidence that eight independently
acquired scans suffice for reliable sub-km positioning.

| Dataset | Earliest-eight error | Prefix12 error | Selected-eight error | Shift from prefix12 | Source span |
|---|---:|---:|---:|---:|---:|
| DS7 | 2,286.0 m | 985.8 m | 1,038.0 m | 54.2 m | 5.07 h |
| DS8 | 1,435.7 m | 1,266.0 m | 1,231.6 m | 35.5 m | 3.89 h |
| DS9 | 639.5 m | 505.9 m | 534.2 m | 38.5 m | 6.13 h |

These are individual multi-scan fits, not medians. Reference errors use the
exposed, unsurveyed position and do not establish absolute accuracy. Source
membership is the earliest 12 scans in each existing sparse 24-scan pool, not
the first 12 scans of the full dataset or 12 consecutive acquisitions. All
12 are used in scouting and selection. The eight-scan refit is a compressed
representation of that source fit.

## Later-scan prediction

| Dataset | Later target scans | Selected8 minus earliest8 | Prefix12 minus earliest8 | Selected8 minus prefix12 |
|---|---:|---:|---:|---:|
| DS7 | 2 | +188.307 | +192.328 | −4.021 |
| DS8 | 3 | −3.723 | −4.630 | +0.907 |
| DS9 | 3 | −18.967 | −16.169 | −2.798 |

Values are summed predictive log-score differences; positive is better. Each
position is evaluated under the same original q020 model, integrating one
shared timing offset per target scan. Targets start strictly after the last
source scan ends, using its known 300-second duration, and are disjoint from
the entire 24-scan pool. Membership was frozen by timestamps before fitting.
These recordings have been examined in earlier research, so temporal exclusion
does not make this a new blind test.

The selected fits have smaller reference errors than the earliest-eight fits
in all three datasets, yet target prediction worsens for DS8 and DS9. This
continues the distinction between agreement with an exposed reference and
predictive generalization. The positive aggregate is dominated by DS7; it does
not justify declaring a consistent improvement across datasets.

## Frozen method

The [protocol](PROTOCOL.md) and [manifest](manifest.json) precede fitting.
The prefix12 receives the original six-start procedure: three cold geographic
starts and three matching training-only timing-grid starts. The highest
qualified training likelihood selects its endpoint. Its geometry matrices,
observed curvature and training score gradients feed the unchanged selector
from the [24-scan compression prototype](../2026_09_29_score_balanced_selection/README.md).
No larger-pool fitted location supplies this expansion point.

Enumerate all 495 eight-of-twelve subsets and maximize the same log-information
determinant minus local score-disagreement penalty with coefficient one. No
hyperparameter or target/reference tuning occurs. Refit the chosen eight using
the same six starts; the prefix12 fit is not a warm start. The earliest-eight
control reuses its existing matched six-start fit after source-ID and score
replay checks.

The selected zero-based prefix indices are 0,2,3,4,6,7,10,11 for DS7 and DS8,
and 0,2,3,5,6,8,9,10 for DS9. All 495 subsets have positive summed observed
curvature in each dataset. Exact sessions, source cutoff and target membership
are retained in the manifest.

## Validation

All 36 new optimization starts qualify. Maximum gradient-audit discrepancy is
8.06e−6. All 36 source Hessian audits pass, maximum relative half-step difference
0.000170; geometry-matrix discrepancy is below 1.79e−9. Halving geometry steps
preserves selection membership in all datasets. All 24 target integrals qualify
without refinement; maximum quadrature difference is 0.003952 log units and
scalar replay discrepancy 1.82e−11.

A partition test confirms chronological sorting, exact prefix size and exclusion
of targets at or before the source end. The reused selector and numerical
helpers retain their preceding tests. Ruff and frozen source-hash checks pass.
Workers complete in 120–145 seconds under 300-second caps. Scouting fits and
derivative audits are saved independently before later work so failures would
remain reviewable; no cases failed in this run.

## Decision

Keep score-balanced selection as a compression technique, with explicit scouting
cost. It preserves both good and less accurate source solutions; it is not a
remedy for the source model's systematic errors. This limited prefix experiment
does not rule out other 12-scan strategies, but it does not support reliable
sub-km performance from this one.

Further accuracy work should address why fitted solutions change across time
and predict later scans inconsistently, rather than treating subset agreement
as truth. Any uncertainty or stopping rule must account for that observed
cross-scan disagreement. Independent surveyed position and historical clock
calibration remain absent from the evidence used here.

See [summary](summary.json), [runner](run.py), per-dataset scouting/derivative
checkpoints and final results. No RF collection, production edits or publication
occurred. Artifacts are local. Reproduction uses `batch.py prepare`, `batch.py run`
and `summarize.py` under a NumPy/SciPy interpreter in a fresh output context.

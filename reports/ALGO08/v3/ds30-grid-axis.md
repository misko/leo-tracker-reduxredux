# Weak axes explain part of the DS30 build-to-build shift

The candidate’s weak grid axis aligned with the displacement to installed ALGO08v3 more than expected under shuffled pairings that preserve every observed bearing. The alignment persisted after removing the cohort’s mean displacement. Installed weak axes showed similar alignment and differed from the candidate axes by a median **4.8° / 4.9°**. Candidate axes showed no corresponding alignment with the error direction to survey. This distinguishes sensitivity shared by both estimators from a useful direction for an accuracy-preserving one-dimensional receiver refinement. [Frozen design](ds30-grid-axis-protocol.md) · [Sealed candidate-only axes](measurements/ds30-grid-axis-prediction.json.gz) · [Scored alignment and full nulls](measurements/ds30-grid-axis-scored.json.gz)

## Displacement to installed v3

The first 24 official pairs include the verified DS30-0452 relocation. The 23 pairs after reserving the DS30-0049 development case had 20 candidate fixes, 19 common fixes and three joint withholds. The one candidate-only fix was DS30-0397, where installed failed in its solver. All returned candidate and installed grids had finite stencils and resolved axes under the frozen 10% eigengap rule. Fixed-zero DS30-0086 moved only **37.7 m**, so its bearing falls below the 50 m reporting floor. The fitted arm has all 19 shared bearings.

| Calibration | Eligible | Candidate mean cos(2θ) | Bearing-preserving null mean and middle 95% | Null upper-tail rank | Candidate median angle | Within 30° | Median displacement / perpendicular remainder |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| Fixed `c = 0` | 18 | +0.317 | −0.026 [−0.283, +0.248] | 0.0061 | 30.1° | 9/18 | 872 / 406 m |
| Fitted `c` | 19 | +0.253 | −0.026 [−0.299, +0.249] | 0.0238 | 34.2° | 8/19 | 834 / 355 m |

The signless statistic is +1 for parallel and −1 for perpendicular. The two values put **65.9% / 62.6%** of normalized squared displacement along the weak line, averaging one contribution per capture. The perpendicular remainder is the distance an ideal line-only displacement would still miss the installed endpoint by, even if it knew the exact displacement along that line.

On the same pairs the installed weak axes gave **+0.344 / +0.289** compared with their own null means **−0.028 / −0.033**, and median acute angles **31.5° / 32.7°**. Removing the two previously examined cases, DS30-0086 and DS30-0220, leaves 17 estimable bearings per arm. The candidate statistic becomes **+0.394 / +0.330**, against null means **+0.005 / −0.032**. All of this is development evidence from the same site.

The common displacement had magnitude **252 / 214 m** after transport into the original offer centre’s tangent frame. Subtracting that vector left all 18 / 19 directions estimable. The candidate statistic remained **+0.248 / +0.234**, against recentered null means **−0.081 / −0.087** and upper-tail ranks **0.0070 / 0.0080**. The bearing-preserving null already allows a common geographic bearing. Recentring also tests whether individual deviations from the mean still align. Neither establishes statistical independence across recordings or between calibrations.

## Separately scored displacement to survey

On 20 scored candidate fixes, the alignment to survey was **+0.026 / +0.038**, below the corresponding bearing-preserving null means **+0.110 / +0.077**. Upper-tail ranks were **0.734 / 0.614**. Median acute angles were **45.0° / 40.3°**, and median perpendicular remainders were **391 / 349 m**. Subtracting the cohort mean displacement to survey gave **+0.148 / +0.164** against null means **+0.100 / +0.077** and upper-tail ranks **0.358 / 0.260**. One fitted remainder shorter than 50 m left 19 fitted directions after centering. These are descriptive permutation ranks, with the observed bearing distributions held fixed.

The verified grid describes a local quadratic on the released fit’s fixed owners and phase linearization. Acquisition changes can move that support. The observed direction describes differences between these two builds, while the survey results give no evidence to select a one-dimensional correction toward the receiver.

## Scope and reproducibility

The axis protocol froze at `7eec3c9de` and reused the exact first24 combined export SHA-256 `db3e4869a95d2f8279873723158c4bd0e8ee93cbc228f5123ec58317712babc9`. The candidate-only seal is `e4397efede379db5231ef7e8256dee918e6691a1ba1a3aaa886c01f386d0c757` and the independent score is `e838a83c6acc6bda91b113dd915f3ae5eea64413c232a6306f716e9e038a30fa` before compression. Both score arms verify original raw/offer custody and signed grid provenance. The prospective DS30-0010, DS30-0444 and DS30-0073 block remains unsealed. Thirteen component and adjacent tests passed. No coordinate is exported, and the readout opened no waveform or orbit body and launched no solver. [Pending prospective receipt](measurements/ds30-grid-axis-pending.json.gz) · [Analysis source](ds30_grid_axis.py) · [Tests](../../../tests/pipeline_eval/test_ds30_grid_axis.py)

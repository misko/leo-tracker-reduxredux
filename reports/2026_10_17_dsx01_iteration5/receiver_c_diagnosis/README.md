# Receiver RF-coefficient contrast: training-only diagnostic

The receivers have weak opposing raw pulls on their shared RF coefficient, but
the independent receiver contrast is sensitive to the frozen band constants.
Its positive-information normalized score is +0.776 directly, +0.902 after old
frequency directions, and −2.904 after also profiling both new band constants.
The sign change is evidence of confounding, not a significant difference between
receiver hardware calibrations. No coefficient, position or other state was fit;
no held measurements, held evaluations or station references were opened.

## Actual RF column and units

The inspected public `PositionObjective` definition is:

```
raw.design[:, 4] = (actual_rf_hz - observations.rf_center_hz) / 1e9
observations.rf_center_hz = mean(unique actual_rf_hz)
```

The coefficient c is in Hz/GHz. The reconstructed training RF center is
11,584,687,500 Hz and the saved shared c is −1204.235686 Hz/GHz. The diagnostic
basis is the **existing** RF column multiplied by +1 for contract RX0 and −1 for
RX1. A new parameter β would therefore give `c_RX0 = c + β` and `c_RX1 = c - β`;
the receiver coefficient difference is `2β`. The predeclared reporting scale is
1000 Hz/GHz, not a prior width or inferred amplitude. `diagnosis.json` preserves
the actual public constructor source and verifies column equality exactly.

## Exact local likelihood derivatives

Use the sealed blocked-training context: 2,073 TRAIN observations, 45 selected
satellites, unchanged physical state, clocks, visibility, detection q, noise
width and classifier. Generic derivative code is imported read-only from the
sealed `band_drift_diagnosis/score.py`. It uses every candidate responsibility,
including competing assignments and clutter dilution, without selecting a
winner. The common row frequency shift leaves the likelihood normalizer fixed.

| Receiver | TRAIN rows | Common-c data gradient | Contrast contribution | Positive RF information |
|---|---:|---:|---:|---:|
| RX0 | 1424 | +0.05895462 | +0.05895462 | 0.01837054 |
| RX1 | 649 | −0.05895465 | +0.05895465 | 0.00472096 |

The common-c gradients cancel to −3.02e−8, exactly replaying its existing full
objective gradient. The new raw contrast data gradient is +0.11790926 per Hz/GHz;
its observed curvature is 0.01750410 and responsibility-frozen positive Gaussian
information is 0.02309149. The normalized score is +0.77593. Receiver-wise raw
scores relative to each receiver's information are only about +0.44 and −0.86.
Thus opposite signs alone do not establish meaningful calibration disagreement.

The observed curvature includes the changing mixture responsibilities; the
positive Gaussian information freezes those responsibilities. There are 814
TRAIN rows with negative observed row curvature, although the aggregate contrast
curvature is positive. Neither matrix is reported as parameter variance,
calibrated uncertainty or an identity-confidence measure.

## Independence from existing frequency directions

The local frequency-tangent projection includes all existing point, shared
calibration, common/relative timing and residual-clock columns. It uses every
candidate and weights p_ik/sigma_i², normalizes columns, and applies a fixed
1e−9 least-squares rank threshold. A second projection appends the two new
receiver-high constant columns, so the contrast is not merely a high/low offset
correction.

| Projection | Contrast gradient | Positive information | Gradient / sqrt(information) |
|---|---:|---:|---:|
| None | +0.1179093 | 0.02309149 | +0.776 |
| All old frequency directions (rank70) | +0.0691180 | 0.00587677 | +0.902 |
| Old directions + both band constants (rank72) | −0.1171491 | 0.00162746 | −2.904 |

The last information is only 7.05% of the raw information. Projected scores are
descriptive Gaussian tangent calculations, not full efficient-score statistics,
p-values or likelihood-ratio tests. q/visibility derivatives, existing priors
and active feasible-boundary constraints are omitted. In particular, some old
parameters have active bounds; unconstrained frequency-tangent projection is
not an optimization over their actual feasible tangent cone. No significance
threshold or inferred hardware cause is justified by the magnitude −2.904.

## Within-band RF and responsibility support

Every receiver/band lane contains four distinct actual RFs, separated by 250 MHz.
Low RFs are 10.7096875, 10.9596875, 11.2096875 and 11.4596875 GHz; high RFs are
11.7096875, 11.9596875, 12.2096875 and 12.4596875 GHz. There is genuine metadata
variation within each band, so this is not an exactly unidentifiable two-band
constant parametrization. Signal support remains unequal:

| Receiver / band | Rows | Summed signal responsibilities | Kish signal rows | Weighted within-band RF std GHz |
|---|---:|---:|---:|---:|
| RX0 low | 728 | 442.87 | 458.55 | 0.2988 |
| RX0 high | 696 | 440.74 | 458.57 | 0.3020 |
| RX1 low | 416 | 121.45 | 131.99 | 0.2683 |
| RX1 high | 233 | 50.51 | 55.16 | 0.2262 |

Whole-receiver summed signal responsibilities are 883.61/171.96, with Kish
counts 917.12/187.15. Weighting by RF information instead gives Kish counts
486.61/128.00; these are descriptive weighted support counts, not independent
verified emitters. The smaller RX1 high support limits interpretation of any
receiver-specific slope claim.

## Recommendation and boundaries

This is a possible secondary calibration sensitivity, with less direct local
support than the band-constant direction. The sign reversal after controlling
constants argues for checking a general joint calibration model rather than
treating raw opposing gradients as evidence of receiver RF mismatch. No model
is promoted and no learned receiver slopes are reported. If a contrast is later
implemented, give it a declared proper zero-centered prior, include the band
constants under a declared policy, preserve total signal normalization and
coherent evidence, freeze training before prediction, and keep matched budgets.
A later controlled c=0 arm must fix **both** the common coefficient and the
receiver contrast to zero. This diagnostic itself is not a fitted-c versus c=0
performance comparison.

Three hardware-free tests pass: exact all-candidate gradient/curvature match
full-density finite differences, invalid/changed held CFO leaves every TRAIN
score array exactly invariant, and the natural contrast has the intended
opposite Hz/GHz signs and factor-two receiver difference. The single bounded
execution took 15.31 seconds, with one explicit mixture evaluation and one
additional frequency-Jacobian projection beyond public-loader replay/audits.
Inputs and code hashes are recorded. No optimization, RF, production change or
sealed-artifact edits were performed.

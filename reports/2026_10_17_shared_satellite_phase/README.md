# Shared satellite phase and scan-local RX/band calibration

Shared orbital phase improves frequency-compatible coverage in these two pilots,
but worsens blind position error. The <0.5-km objective remains unmet. Satellite
labels are candidates; no authenticated identity truth is available.

## Explicit hardware model

For a point i on component j and candidate satellite s:

```
f_i + k_i P = q_i D_s(t_i; position, phase_s)
            + a_scan,RX,band + d_scan,RX,band (t_i-150s)
            + c (RF_i/GHz-11.5) + b_j + noise
```

Here P=227272.727 Hz, q=RF/11.5 GHz. Each scan has four independent intercepts
and four independent drifts: RX1 low/high and RX2 low/high. Their differences
give cross-receiver and cross-band offsets and relative drifts, including an
RX-by-band interaction. No dataset-wide offset or drift is imposed. Intercepts
and contrasts are alias-branch quantities, reported at 150 s and 11.5 GHz.
The optional c coefficient accounts for within-band RF dependence; every
comparison includes matched c=0/fitted-c arms. Component constants have a
1000-Hz Gaussian penalty, but no free component slope. One phase is shared by
all components assigned to a NORAD; per-component phases only propose seeds.

The original sensitivity model uses drift σ=2 Hz/s and bounds ±5 Hz/s. The new
tight setting uses σ=0.5 Hz/s and bounds ±1 Hz/s, enforced on initial states,
all proposals and retained fits. These are declared assumptions, not independently
measured LNB specifications. Zero drift is also supported. The historical five-scan
[drift ablation](../2026_10_17_ds22_search_revision/README.md) compares zero/tight/baseline
policies without orbital phase, and is a separate experiment.

Only original fragments with measured active curvature calibrate hardware or
position. A polynomial degree alone is insufficient: span and departure from an
affine fit are required. Linear fragments can associate afterward when their
hardware group has qualified curved support. Nonzero phases additionally need
qualified curved satellite support. Final association checks mean, slope,
quadratic structure, steps and lag-one correlation, with RMS ≤450 Hz.

## Completed blind searches

Same original points, causal candidate bank, regional grid, basins and seed
budgets within each c pair; no points withheld. Reference GPS enters after fit
sealing. Two DSX shared-phase searches exceeded their first ten-minute process
budgets during finalist evaluation and completed by verified cache replay with
the unchanged search path and budget. Original interrupted artifacts remain.

| Case | Model | Points (%) | Merged tracks | Points/track | Error (km) |
| --- | --- | --- | --- | --- | --- |
| DS22-001 | shared_c0 | 1108 (31.6%) | 38 | 29.2 | 13.615 |
| DS22-001 | shared_fitted_c | 1108 (31.6%) | 39 | 28.4 | 13.615 |
| DS22-001 | zero_c0 | 136 (3.9%) | 5 | 27.2 | 11.698 |
| DS22-001 | zero_fitted_c | 144 (4.1%) | 6 | 24.0 | 11.760 |
| DSX01-S01 | zero_c0 | 190 (4.2%) | 10 | 19.0 | 5.734 |
| DSX01-S01 | zero_fitted_c | 207 (4.6%) | 14 | 14.8 | 5.616 |
| DSX01-S01 | shared_c0 | 2237 (49.9%) | 73 | 30.6 | 13.434 |
| DSX01-S01 | shared_fitted_c | 2186 (48.7%) | 69 | 31.7 | 13.434 |

![Coverage and blind position](association-vs-position.png)

Consolidation uses exact phased geometry, common hardware, a common penalized
component constant and residual gates. All admitted point IDs and candidate
identities are preserved; eight blind consolidation arms drop zero points.

## Small drift check at supplied GPS

These are diagnostic fits, not blind geographic estimates. Tight c=0 gives
1,383/3,510 compatible DS22-001 points and 1,975/4,487 DSX01-S01 points.
Tight fitted-c gives 1,150 and 1,975 points respectively. The previous blind
endpoint still scores better than GPS under the tight model in both cases.
Thus constraining LNB drift alone does not fix position preference.

| Case | Hardware | Offset (Hz) | Drift (Hz/s) | Curved fragments | Bound active |
| --- | --- | --- | --- | --- | --- |
| DS22-001 | RX1 low | -14404.9 | 0.990 | 9 | False |
| DS22-001 | RX1 high | -42138.3 | 1.000 | 3 | True |
| DS22-001 | RX2 low | 7172.6 | 0.660 | 7 | False |
| DS22-001 | RX2 high | 46111.6 | -0.265 | 4 | False |
| DSX01-S01 | RX1 low | -8851.9 | 1.000 | 13 | True |
| DSX01-S01 | RX1 high | -26835.8 | 1.000 | 12 | True |
| DSX01-S01 | RX2 low | -17327.3 | 0.236 | 5 | False |
| DSX01-S01 | RX2 high | 21515.1 | -1.000 | 10 | True |

![Independent hardware groups](hardware-drift-offsets.png)

Bound hits, sparse support and sensitivity to model choice flag weak calibration.
Curved-support counts are not confidence intervals. The information audit conditions
on candidate identities and assumed priors: GPS shared-phase weak-axis scales are
about 0.94 km for DS22 and 0.65 km for DSX with priors. These are optimistic local
sensitivity scales, not calibrated coverage intervals. Different phase variants
admit different anchor sets, so their information difference is not a controlled
same-anchor nuisance ablation. Exact values remain in identifiability/results.json.

## Existing-IQ measurement check

The stored pair-autocorrelation GLRT selects a 512-point FFT bin at a 4.4-µs
symbol interval, spacing 443.892 Hz. Fractional epoch refinement does not by
itself refine that CFO bin. A response-only panel selects two longest measured-
curved tracks per RX/band and two points per track, independent of GPS and labels.
The existing reviewed known-pilot frame estimator qualifies 14/16 DS22 and 15/16
DSX points. Median conditional frequency uncertainties are 16.6
and 18.4 Hz. These are estimator-internal
uncertainties, not an independent calibration or demonstrated position accuracy.
All original detections, times, populations and fits remain unchanged. The small
panel is a measurement feasibility result; it has not been used for localization.
Legacy DSX graph timestamps differ from source-counter times by up to 0.503 ms;
matching requires unique support within 0.51 ms plus exact reproduction of a gated
CFO peak. Actual differences and rejected estimates are retained. No new RF was collected.

## Reproduction and next decision

Tables are also CSV: blind-searches, fixed-site-comparisons, hardware-groups,
hardware-contrasts and pilot-panel-summary. Original search sources are archived
in code_snapshot; the configurable drift version and tests in drift_code_snapshot.
Input orbit-bank receipts bind causal TLEs and original Graph files. Successive
causal TLE disagreement sets the phase sensitivity scale, not a truth covariance.

Next, test continuous qualified measurements on complete tracks and compare
matched c arms, with the same original-point denominator and explicit unsupported
measurements. A stationary multi-scan position fit would retain independent
hardware for every scan. More associated points alone cannot establish location
accuracy. No production calibration or scientific golden fixture was replaced.

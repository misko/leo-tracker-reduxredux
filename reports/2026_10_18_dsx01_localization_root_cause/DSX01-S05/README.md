# DSX01-S05: localization root cause

[All-scan report](../README.md)

## Finding and smallest defensible correction

Refreshing the inaccurate phase tangent worsens GPS error from 1.406 to 1.887 km while improving RF loss. The earlier apparent accuracy partly relied on cancellation with a numerical approximation error. No one-family deletion resolves the remaining bias (best 1.582 km), no archived multi-piece join exists, and hard RF-gate rejection worsens error to 3.118 km. Allowing more orbital flexibility also worsens position. The strongest demonstrated simple lever is the independent fragment-constant prior.

Learning one common scale from RF evidence selects 100 Hz and reaches 0.998 / 1.010 km while retaining all points and identities. Treat this as approximately 1 km, not a robust pass of a sharp 1 km threshold. The same scale-learning policy fails to improve S03, so it is a promising candidate rather than a validated universal correction.

## Controlled position results

Errors below are **c0 / fitted c**, km. GPS is evaluation only.

| Intervention | Position error (km) | Interpretation |
|---|---:|---|
| Fixed zero phase expansion | 1.406 / 1.395 | Earlier joint-descent model |
| Phase refresh, same labels and priors | 1.887 / 1.870 | Numerical correction only |
| Best single-family deletion by GPS | 1.582 (c0) | ORACLE diagnostic: delete 58359, 40 points |
| Best single-track deletion by GPS | 1.582 (c0) | ORACLE diagnostic: delete S05-RX2-CH6-T002 |
| Expanded RF pool, retaining incumbent | 1.887 / 1.870 | RF-selected phase-refreshed incumbent; atlas adds 18 hypotheses |
| RF-learned independent offset σ=100 Hz | 0.998 / 1.010 | One learned scalar; no GPS selection |

Deletion experiments preserve the original nuisance prior support for all remaining observations. Their losses cannot be compared across different observation masks. A deletion improving GPS error is evidence of influence, not authentication that a satellite identity is wrong.

## Satellite and track evidence

![Satellite identity and deletion controls](association_hypotheses.png)

![Leave-family/track/receiver-band/time-block positions](ablation_positions.png)

![Influence and residual reliability](family_and_track_influence.png)

Largest family movements are listed below, selected without GPS. Several influential constraints can pull toward the correct position.

| Deleted family | Points | Position movement (km) | GPS error after deletion (km) |
|---|---:|---:|---:|
| 68102 | 58 | 0.753 | 2.244 |
| 61922 | 478 | 0.565 | 2.060 |
| 66854 | 77 | 0.350 | 2.207 |
| 56693 | 182 | 0.329 | 2.171 |
| 58359 | 40 | 0.305 | 1.582 |
| 66575 | 187 | 0.232 | 2.118 |
| 66508 | 158 | 0.211 | 2.098 |
| 68045 | 65 | 0.193 | 2.004 |

## Why frequency fit prefers the displaced endpoint

![Objective pressure at GPS versus blind endpoint](objective_pressure.png)

Positive bars mean a term penalizes the GPS coordinate more than the blind minimum after re-profiling nuisance coefficients at both positions. The right-hand plot omits shared calibration, Gamma penalties and log-volume; it is a partial family decomposition, not a satellite probability.

![Fitted receiver calibration and satellite prior pulls](nuisance_calibration.png)

These are conditional fitted coefficients under engineering priors. Their size does not establish actual hardware drift or actual orbit error. Each receiver has a mean linear drift and band contrast; offsets are separate for the four receiver/band groups. Smooth terms can absorb position-dependent Doppler. A large prior pull identifies model pressure, not an authenticated bad identity.

## General model controls

All rows below preserve the same points, candidate identities and aliases. Only the declared nuisance model or prior changes. The score change is c0 relative to phase refresh; smaller loss does not establish better position.

| Model | Error c0 / fitted c (km) | RMS c0 / fitted c (Hz) | c0 Δ loss | fitted-c Δ loss |
|---|---:|---:|---:|---:|
| zero phase expansion | 1.406 / 1.395 | 175.53 / 175.53 | +13.208 | +13.208 |
| phase refresh | 1.887 / 1.870 | 174.99 / 174.99 | +0.000 | +0.000 |
| drift_1 | 1.413 / 1.393 | 175.93 / 175.94 | +76.860 | +76.820 |
| phase_3 | 1.690 / 1.670 | 174.92 / 174.92 | +30.704 | +30.732 |
| bias_3 | 2.224 / 2.222 | 174.86 / 174.86 | +105.303 | +103.835 |
| orbit_3 | 2.504 / 2.503 | 174.73 / 174.73 | +6.542 | +6.337 |
| eccentric | 2.048 / 2.035 | 174.91 / 174.91 | +1.454 | +1.404 |
| native_band | 1.554 / 1.542 | 173.87 / 173.88 | -36.726 | -36.563 |
| colored | 2.337 / 2.322 | 179.34 / 179.47 | -158.660 | -158.962 |
| independent_bias_300 | 1.231 / 1.226 | 176.29 / 176.21 | -65.820 | -66.926 |
| smooth_20 | 2.940 / 2.943 | 184.77 / 184.76 | +252.078 | +251.964 |
| linear_radio_only | 2.798 / 2.806 | 188.03 / 188.01 | +323.998 | +323.762 |
| independent_band_drift_2 | 1.581 / 1.562 | 175.54 / 175.54 | +55.672 | +55.662 |
| phase_orbit_3 | 2.127 / 2.120 | 174.66 / 174.66 | +38.070 | +37.915 |
| smooth20_independent2 | 2.861 / 2.863 | 184.80 / 184.79 | +275.731 | +275.711 |
| hierarchical_clock_300 | 2.093 / 2.081 | 175.34 / 175.34 | -68.370 | -66.819 |
| orbit_floor_0.1_0.05 | 1.902 / 1.886 | 174.98 / 174.97 | +0.145 | +0.129 |
| orbit_floor_0.5_0.25 | 2.162 / 2.185 | 174.60 / 174.59 | +1.355 | +1.197 |
| orbit_floor_1.0_0.5 | 2.926 / 2.933 | 174.34 / 174.32 | +4.407 | +4.001 |

The RF-selected common fragment-offset scale is an additional one-scalar empirical-Bayes experiment, shown in the all-scan scale figure. All physical orbit-floor experiments leave the nominal causal TLE unchanged and add no coefficients. The expanded eccentricity control does add two supported-satellite physical modes; its Gaussian integration includes a volume penalty.

## Multiple-family and receiver/time controls

The three most influential families were selected by position movement, not GPS improvement. All three pairs and their triple were then removed. This is a bounded influence probe, not exhaustive multi-satellite subset search.

| Deleted families | Points removed | Error c0 / fitted c (km) |
|---|---:|---:|
| 68102, 61922 | 536 | 2.087 / 2.083 |
| 68102, 66854 | 135 | 2.461 / 2.470 |
| 61922, 66854 | 555 | 2.401 / 2.408 |
| 68102, 61922, 66854 | 613 | 2.317 / 2.314 |

| Deleted receiver/band or time group | Points removed | Error c0 / fitted c (km) |
|---|---:|---:|
| RX1_B0 | 979 | 2.100 / 2.062 |
| RX1_B1 | 738 | 2.100 / 2.098 |
| RX2_B0 | 420 | 1.530 / 1.477 |
| RX2_B1 | 222 | 1.815 / 1.807 |
| time_0_100 | 958 | 2.090 / 2.060 |
| time_100_200 | 687 | 1.867 / 1.873 |
| time_200_300 | 714 | 2.096 / 2.027 |

## Calibration membership and joins

| RF-only calibration policy | Calibrating points | Error c0 / fitted c (km) |
|---|---:|---:|
| remeasured_curvature | 2359 | 1.887 / 1.870 |
| endpoint_stable_curvature | 2268 | 2.035 / 2.019 |
| all_RF_association_gates | 1934 | 3.118 / 3.126 |
| stable_curvature_and_gates | 1869 | 3.334 / 3.326 |

There are **0 archived multi-piece calibration tracks** in this scan. A single polynomial can still contain a misclustered point; zero archived joins does not prove every original point assignment correct. Split probes test the three strongest residual-step candidates and every archived join. A residual step can also indicate orbit mismatch. Each new calibration piece must retain at least 20 s and 250 Hz RMS departure from an affine line, so a split cannot introduce linear-only offset calibrators.

| Split target | Cut | Result |
|---|---:|---|
| S05-RX2-CH1-T006 | point 8 | Ineligible: each calibration piece must retain active curvature |
| S05-RX2-CH7-T003 | point 8 | Ineligible: each calibration piece must retain active curvature |
| S05-RX1-CH2-T002 | point 14 | Ineligible: each calibration piece must retain active curvature |

The split comparison uses the full normalized variational bound and an additional `3 log(n)` cut-search penalty because splitting changes the noise-group normalization. No original point is dropped or duplicated.

## Original GLRT evidence and 20-second views

Tracks below were chosen by largest deletion influence, largest residual-step evidence, and archived join membership—not by GPS improvement. The blue/orange model curves include orbit and fitted calibration; the nominal causal-orbit curve uses the same conditional calibration for display. GPS curves are post-fit diagnostics. A polynomial and an orbital model test different things.

### S05-RX2-CH1-T002

![Track evidence](track_S05-RX2-CH1-T002.png)

[Original CFO in 20-second segments](zoom20_S05-RX2-CH1-T002.png)

### S05-RX2-CH6-T002

![Track evidence](track_S05-RX2-CH6-T002.png)

[Original CFO in 20-second segments](zoom20_S05-RX2-CH6-T002.png)

### S05-RX2-CH1-T006

![Track evidence](track_S05-RX2-CH1-T006.png)

[Original CFO in 20-second segments](zoom20_S05-RX2-CH1-T006.png)

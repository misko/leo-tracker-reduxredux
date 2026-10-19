# DSX01-S03: localization root cause

[All-scan report](../README.md)

## Finding and smallest defensible correction

The original 5.500 km error was largely numerical: phase refresh reaches 1.571 km. The remaining displacement is not explained solely by any one tested satellite family: the best single-family deletion still has 1.051 km error. Removing the largest-influence pair/triple does not resolve it either. The only archived join, RX1 CH4 T002, can be separated into actively curved pieces, but the point-preserving refit worsens error to 1.649 km. Rechecking active curvature excludes one 19-point track and barely changes error (1.554 km). At GPS the weighted frequency-data cost is actually lower, while the total prior/Gamma/log-volume objective prefers the displaced endpoint. This directly implicates model regularization/calibration ambiguity in addition to the corrected phase approximation.

A 20 Hz receiver-smooth prior reaches 0.438 km without adding coefficients, but worsens the RF objective by about 183; selecting it because of GPS would be oracle tuning. The RF-selected offset scale and a lower-loss alternate identity both worsen position. Keep the numerical correction; obtain independent receiver stability constraints before claiming a remaining sub-km solution.

## Controlled position results

Errors below are **c0 / fitted c**, km. GPS is evaluation only.

| Intervention | Position error (km) | Interpretation |
|---|---:|---|
| Fixed zero phase expansion | 5.500 / 5.542 | Earlier joint-descent model |
| Phase refresh, same labels and priors | 1.571 / 1.630 | Numerical correction only |
| Best single-family deletion by GPS | 1.051 (c0) | ORACLE diagnostic: delete 100548, 76 points |
| Best single-track deletion by GPS | 1.147 (c0) | ORACLE diagnostic: delete S03-RX1-CH5-T000 |
| Expanded RF pool, retaining incumbent | 1.809 / 1.878 | RF-selected hypotheses:3; atlas adds 14 hypotheses |
| RF-learned independent offset σ=300 Hz | 1.818 / 1.857 | One learned scalar; no GPS selection |

Deletion experiments preserve the original nuisance prior support for all remaining observations. Their losses cannot be compared across different observation masks. A deletion improving GPS error is evidence of influence, not authentication that a satellite identity is wrong.

## Satellite and track evidence

![Satellite identity and deletion controls](association_hypotheses.png)

![Leave-family/track/receiver-band/time-block positions](ablation_positions.png)

![Influence and residual reliability](family_and_track_influence.png)

Largest family movements are listed below, selected without GPS. Several influential constraints can pull toward the correct position.

| Deleted family | Points | Position movement (km) | GPS error after deletion (km) |
|---|---:|---:|---:|
| 66584 | 42 | 0.789 | 2.297 |
| 62602 | 125 | 0.689 | 2.256 |
| 63450 | 60 | 0.628 | 1.147 |
| 66435 | 222 | 0.538 | 2.089 |
| 100548 | 76 | 0.521 | 1.051 |
| 63562 | 206 | 0.357 | 1.334 |
| 60127 | 103 | 0.333 | 1.719 |
| 59547 | 90 | 0.248 | 1.695 |

## Why frequency fit prefers the displaced endpoint

![Objective pressure at GPS versus blind endpoint](objective_pressure.png)

Positive bars mean a term penalizes the GPS coordinate more than the blind minimum after re-profiling nuisance coefficients at both positions. The right-hand plot omits shared calibration, Gamma penalties and log-volume; it is a partial family decomposition, not a satellite probability.

![Fitted receiver calibration and satellite prior pulls](nuisance_calibration.png)

These are conditional fitted coefficients under engineering priors. Their size does not establish actual hardware drift or actual orbit error. Each receiver has a mean linear drift and band contrast; offsets are separate for the four receiver/band groups. Smooth terms can absorb position-dependent Doppler. A large prior pull identifies model pressure, not an authenticated bad identity.

## General model controls

All rows below preserve the same points, candidate identities and aliases. Only the declared nuisance model or prior changes. The score change is c0 relative to phase refresh; smaller loss does not establish better position.

| Model | Error c0 / fitted c (km) | RMS c0 / fitted c (Hz) | c0 Δ loss | fitted-c Δ loss |
|---|---:|---:|---:|---:|
| zero phase expansion | 5.500 / 5.542 | 462.10 / 462.32 | +72.526 | +73.603 |
| phase refresh | 1.571 / 1.630 | 461.00 / 461.25 | +0.000 | +0.000 |
| drift_1 | 1.778 / 1.836 | 462.23 / 462.46 | -1.560 | -2.034 |
| phase_3 | 1.459 / 1.521 | 461.40 / 461.66 | +45.691 | +45.719 |
| bias_3 | 1.380 / 1.390 | 452.34 / 452.48 | +130.041 | +131.520 |
| orbit_3 | 1.258 / 1.274 | 461.07 / 461.33 | +9.181 | +9.171 |
| eccentric | 1.392 / 1.430 | 460.99 / 461.24 | +1.946 | +1.819 |
| native_band | 1.682 / 1.750 | 460.24 / 460.53 | +42.548 | +42.332 |
| colored | 2.018 / 2.095 | 496.25 / 496.46 | -34.081 | -34.275 |
| independent_bias_300 | 1.818 / 1.857 | 462.93 / 462.83 | -75.597 | -112.334 |
| smooth_20 | 0.438 / 0.391 | 473.47 / 473.64 | +182.736 | +183.374 |
| linear_radio_only | 1.147 / 1.091 | 475.34 / 475.49 | +264.151 | +265.778 |
| independent_band_drift_2 | 1.702 / 1.761 | 461.95 / 462.19 | +0.287 | -0.032 |
| phase_orbit_3 | 1.073 / 1.088 | 461.59 / 461.85 | +54.559 | +54.561 |
| smooth20_independent2 | 0.434 / 0.399 | 474.10 / 474.26 | +180.594 | +181.232 |
| hierarchical_clock_300 | 1.807 / 1.749 | 462.50 / 462.75 | -64.859 | -86.491 |
| orbit_floor_0.1_0.05 | 1.555 / 1.613 | 461.00 / 461.25 | -0.035 | -0.033 |
| orbit_floor_0.5_0.25 | 1.238 / 1.264 | 460.66 / 460.91 | -0.202 | -0.155 |
| orbit_floor_1.0_0.5 | 1.170 / 1.158 | 460.35 / 460.65 | +6.535 | +6.784 |

The RF-selected common fragment-offset scale is an additional one-scalar empirical-Bayes experiment, shown in the all-scan scale figure. All physical orbit-floor experiments leave the nominal causal TLE unchanged and add no coefficients. The expanded eccentricity control does add two supported-satellite physical modes; its Gaussian integration includes a volume penalty.

## Multiple-family and receiver/time controls

The three most influential families were selected by position movement, not GPS improvement. All three pairs and their triple were then removed. This is a bounded influence probe, not exhaustive multi-satellite subset search.

| Deleted families | Points removed | Error c0 / fitted c (km) |
|---|---:|---:|
| 66584, 62602 | 167 | 2.885 / 3.019 |
| 66584, 63450 | 102 | 1.825 / 1.896 |
| 62602, 63450 | 185 | 1.814 / 1.939 |
| 66584, 62602, 63450 | 227 | 2.572 / 2.709 |

| Deleted receiver/band or time group | Points removed | Error c0 / fitted c (km) |
|---|---:|---:|
| RX1_B0 | 880 | 2.151 / 2.221 |
| RX1_B1 | 1033 | 1.968 / 2.102 |
| RX2_B0 | 398 | 2.417 / 2.527 |
| RX2_B1 | 298 | 2.222 / 2.272 |
| time_0_100 | 833 | 1.161 / 1.189 |
| time_100_200 | 878 | 1.989 / 2.084 |
| time_200_300 | 898 | 3.425 / 3.468 |

## Calibration membership and joins

| RF-only calibration policy | Calibrating points | Error c0 / fitted c (km) |
|---|---:|---:|
| remeasured_curvature | 2590 | 1.554 / 1.618 |
| endpoint_stable_curvature | 2405 | 2.413 / 2.492 |
| all_RF_association_gates | 2287 | 1.626 / 1.726 |
| stable_curvature_and_gates | 2083 | 2.230 / 2.329 |

There are **1 archived multi-piece calibration tracks** in this scan. A single polynomial can still contain a misclustered point; zero archived joins does not prove every original point assignment correct. Split probes test the three strongest residual-step candidates and every archived join. A residual step can also indicate orbit mismatch. Each new calibration piece must retain at least 20 s and 250 Hz RMS departure from an affine line, so a split cannot introduce linear-only offset calibrators.

| Split target | Cut | Result |
|---|---:|---|
| S03-RX1-CH3-T000 | point 36 | Ineligible: each calibration piece must retain active curvature |
| S03-RX1-CH2-T003 | point 18 | Ineligible: each calibration piece must retain active curvature |
| S03-RX1-CH7-T003 | point 22 | Ineligible: each calibration piece must retain active curvature |
| S03-RX1-CH4-T002 | point 38 | Ineligible: each calibration piece must retain active curvature |
| S03-RX1-CH4-T002 | 231.61 s | 1.649 / 1.711 km; Δ full bound + cut penalty +16.964 |

The split comparison uses the full normalized variational bound and an additional `3 log(n)` cut-search penalty because splitting changes the noise-group normalization. No original point is dropped or duplicated.

## Original GLRT evidence and 20-second views

Tracks below were chosen by largest deletion influence, largest residual-step evidence, and archived join membership—not by GPS improvement. The blue/orange model curves include orbit and fitted calibration; the nominal causal-orbit curve uses the same conditional calibration for display. GPS curves are post-fit diagnostics. A polynomial and an orbital model test different things.

### S03-RX2-CH3-T000

![Track evidence](track_S03-RX2-CH3-T000.png)

[Original CFO in 20-second segments](zoom20_S03-RX2-CH3-T000.png)

### S03-RX1-CH5-T000

![Track evidence](track_S03-RX1-CH5-T000.png)

[Original CFO in 20-second segments](zoom20_S03-RX1-CH5-T000.png)

### S03-RX1-CH3-T000

![Track evidence](track_S03-RX1-CH3-T000.png)

[Original CFO in 20-second segments](zoom20_S03-RX1-CH3-T000.png)

### S03-RX1-CH4-T002

![Track evidence](track_S03-RX1-CH4-T002.png)

[Original CFO in 20-second segments](zoom20_S03-RX1-CH4-T002.png)

# DSX01-S04: localization root cause

[All-scan report](../README.md)

## Finding and smallest defensible correction

This is the clearest unresolved case. Phase refresh leaves approximately the same 1.85 km displacement. No single family deletion reaches 1 km, no archived multi-piece calibration join exists, and the most influential individual track moves the fit by less than 0.41 km. Removing the large 59540 family (415 points) worsens error to 2.860 km. The full-box atlas contributes 23 distinct hypotheses; its own best candidate has 2.702 km error and worse RF loss than the retained incumbent. Thus expanding this finite pool is not a solution. These experiments cannot rule out an untested joint identity combination or actual causal-orbit error.

A linear-only receiver calibration reaches 1.124 km, RF-gated calibrators reach 1.376 km, and an RF-selected 300 Hz track-offset scale reaches 1.647 / 1.878 km. None is a demonstrated sub-km correction. Do not force a TLE adjustment or discard the strongest family to manufacture agreement. The next discriminating evidence is independently measured calibration stability or a better validated causal orbital covariance, followed by broader joint identity search.

## Controlled position results

Errors below are **c0 / fitted c**, km. GPS is evaluation only.

| Intervention | Position error (km) | Interpretation |
|---|---:|---|
| Fixed zero phase expansion | 1.835 / 1.820 | Earlier joint-descent model |
| Phase refresh, same labels and priors | 1.848 / 1.877 | Numerical correction only |
| Best single-family deletion by GPS | 1.563 (c0) | ORACLE diagnostic: delete 57460, 92 points |
| Best single-track deletion by GPS | 1.455 (c0) | ORACLE diagnostic: delete S04-RX1-CH3-T003 |
| Expanded RF pool, retaining incumbent | 1.854 / 1.887 | RF-selected identity coordinate moves; atlas adds 23 hypotheses |
| RF-learned independent offset σ=300 Hz | 1.647 / 1.878 | One learned scalar; no GPS selection |

Deletion experiments preserve the original nuisance prior support for all remaining observations. Their losses cannot be compared across different observation masks. A deletion improving GPS error is evidence of influence, not authentication that a satellite identity is wrong.

## Satellite and track evidence

![Satellite identity and deletion controls](association_hypotheses.png)

![Leave-family/track/receiver-band/time-block positions](ablation_positions.png)

![Influence and residual reliability](family_and_track_influence.png)

Largest family movements are listed below, selected without GPS. Several influential constraints can pull toward the correct position.

| Deleted family | Points | Position movement (km) | GPS error after deletion (km) |
|---|---:|---:|---:|
| 59540 | 415 | 1.546 | 2.860 |
| 66488 | 132 | 1.090 | 2.245 |
| 66519 | 227 | 0.687 | 2.053 |
| 60111 | 88 | 0.414 | 1.954 |
| 66580 | 120 | 0.345 | 1.957 |
| 57460 | 92 | 0.309 | 1.563 |
| 66134 | 172 | 0.251 | 1.896 |
| 61912 | 88 | 0.221 | 1.722 |

## Why frequency fit prefers the displaced endpoint

![Objective pressure at GPS versus blind endpoint](objective_pressure.png)

Positive bars mean a term penalizes the GPS coordinate more than the blind minimum after re-profiling nuisance coefficients at both positions. The right-hand plot omits shared calibration, Gamma penalties and log-volume; it is a partial family decomposition, not a satellite probability.

![Fitted receiver calibration and satellite prior pulls](nuisance_calibration.png)

These are conditional fitted coefficients under engineering priors. Their size does not establish actual hardware drift or actual orbit error. Each receiver has a mean linear drift and band contrast; offsets are separate for the four receiver/band groups. Smooth terms can absorb position-dependent Doppler. A large prior pull identifies model pressure, not an authenticated bad identity.

## General model controls

All rows below preserve the same points, candidate identities and aliases. Only the declared nuisance model or prior changes. The score change is c0 relative to phase refresh; smaller loss does not establish better position.

| Model | Error c0 / fitted c (km) | RMS c0 / fitted c (Hz) | c0 Δ loss | fitted-c Δ loss |
|---|---:|---:|---:|---:|
| zero phase expansion | 1.835 / 1.820 | 209.84 / 209.78 | +59.147 | +58.674 |
| phase refresh | 1.848 / 1.877 | 210.20 / 210.18 | +0.000 | +0.000 |
| drift_1 | 1.433 / 1.483 | 211.66 / 211.63 | +54.494 | +54.474 |
| phase_3 | 1.971 / 2.013 | 210.15 / 210.13 | +29.708 | +29.651 |
| bias_3 | 1.946 / 1.948 | 209.61 / 209.60 | +107.790 | +108.581 |
| orbit_3 | 2.079 / 2.080 | 210.07 / 210.05 | -4.214 | -3.328 |
| eccentric | 1.996 / 2.012 | 210.14 / 210.11 | -2.749 | -2.475 |
| native_band | 1.914 / 1.961 | 209.99 / 209.96 | +38.257 | +37.980 |
| colored | 2.904 / 3.019 | 238.62 / 240.27 | -144.870 | -145.132 |
| independent_bias_300 | 1.647 / 1.878 | 212.16 / 211.81 | -76.456 | -99.690 |
| smooth_20 | 1.452 / 1.464 | 212.35 / 212.35 | +59.886 | +59.661 |
| linear_radio_only | 1.124 / 1.130 | 213.62 / 213.62 | +85.726 | +85.455 |
| independent_band_drift_2 | 1.537 / 1.577 | 211.00 / 210.98 | +36.824 | +36.807 |
| phase_orbit_3 | 1.666 / 1.699 | 209.98 / 209.96 | +27.750 | +28.554 |
| smooth20_independent2 | 1.431 / 1.440 | 212.94 / 212.94 | +85.036 | +84.808 |
| hierarchical_clock_300 | 1.433 / 1.537 | 211.08 / 211.12 | -61.396 | -81.004 |
| orbit_floor_0.1_0.05 | 1.958 / 1.983 | 210.25 / 210.24 | -1.375 | -1.326 |
| orbit_floor_0.5_0.25 | 2.368 / 2.411 | 210.31 / 210.29 | -3.029 | -2.675 |
| orbit_floor_1.0_0.5 | 2.360 / 2.403 | 210.30 / 210.28 | +1.121 | +1.943 |

The RF-selected common fragment-offset scale is an additional one-scalar empirical-Bayes experiment, shown in the all-scan scale figure. All physical orbit-floor experiments leave the nominal causal TLE unchanged and add no coefficients. The expanded eccentricity control does add two supported-satellite physical modes; its Gaussian integration includes a volume penalty.

## Multiple-family and receiver/time controls

The three most influential families were selected by position movement, not GPS improvement. All three pairs and their triple were then removed. This is a bounded influence probe, not exhaustive multi-satellite subset search.

| Deleted families | Points removed | Error c0 / fitted c (km) |
|---|---:|---:|
| 59540, 66488 | 547 | 2.466 / 2.530 |
| 59540, 66519 | 642 | 2.634 / 2.696 |
| 66488, 66519 | 359 | 2.120 / 2.120 |
| 59540, 66488, 66519 | 774 | 2.122 / 2.211 |

| Deleted receiver/band or time group | Points removed | Error c0 / fitted c (km) |
|---|---:|---:|
| RX1_B0 | 1039 | 1.157 / 1.170 |
| RX1_B1 | 780 | 2.268 / 2.338 |
| RX2_B0 | 524 | 4.201 / 4.322 |
| RX2_B1 | 187 | 1.837 / 1.878 |
| time_0_100 | 797 | 2.181 / 2.246 |
| time_100_200 | 928 | 2.210 / 2.160 |
| time_200_300 | 805 | 1.925 / 1.920 |

## Calibration membership and joins

| RF-only calibration policy | Calibrating points | Error c0 / fitted c (km) |
|---|---:|---:|
| remeasured_curvature | 2530 | 1.848 / 1.877 |
| endpoint_stable_curvature | 2409 | 1.928 / 1.956 |
| all_RF_association_gates | 2330 | 1.376 / 1.414 |
| stable_curvature_and_gates | 2225 | 1.529 / 1.544 |

There are **0 archived multi-piece calibration tracks** in this scan. A single polynomial can still contain a misclustered point; zero archived joins does not prove every original point assignment correct. Split probes test the three strongest residual-step candidates and every archived join. A residual step can also indicate orbit mismatch. Each new calibration piece must retain at least 20 s and 250 Hz RMS departure from an affine line, so a split cannot introduce linear-only offset calibrators.

| Split target | Cut | Result |
|---|---:|---|
| S04-RX1-CH2-T000 | point 33 | Ineligible: each calibration piece must retain active curvature |
| S04-RX2-CH1-T001 | point 16 | Ineligible: each calibration piece must retain active curvature |
| S04-RX1-CH7-T002 | point 8 | Ineligible: each calibration piece must retain active curvature |

The split comparison uses the full normalized variational bound and an additional `3 log(n)` cut-search penalty because splitting changes the noise-group normalization. No original point is dropped or duplicated.

## Original GLRT evidence and 20-second views

Tracks below were chosen by largest deletion influence, largest residual-step evidence, and archived join membership—not by GPS improvement. The blue/orange model curves include orbit and fitted calibration; the nominal causal-orbit curve uses the same conditional calibration for display. GPS curves are post-fit diagnostics. A polynomial and an orbital model test different things.

### S04-RX1-CH1-T004

![Track evidence](track_S04-RX1-CH1-T004.png)

[Original CFO in 20-second segments](zoom20_S04-RX1-CH1-T004.png)

### S04-RX1-CH3-T003

![Track evidence](track_S04-RX1-CH3-T003.png)

[Original CFO in 20-second segments](zoom20_S04-RX1-CH3-T003.png)

### S04-RX1-CH2-T000

![Track evidence](track_S04-RX1-CH2-T000.png)

[Original CFO in 20-second segments](zoom20_S04-RX1-CH2-T000.png)

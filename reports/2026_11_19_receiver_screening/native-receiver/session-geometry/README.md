# Static position across whole visits

We tested whether a shared receiver position across captures could recover a second real site's location with a small Doppler solver. On one Prague rooftop, the profiled model lowered its training objective on both visits. Its forced position was 5.33 km from the survey using May captures and 4.08 km using April captures. The Prague city centre was 4.41 km from the survey. The model released zero of the two containing-offer estimates and none of the 16 disjoint-offer estimates. The Prague result gives no basis for claiming the 5–10% v5 target. CTU released author-selected spectral peaks and paired ECEF with unaudited availability. A same-input v5 endpoint is unavailable. [Geographic scores](geographic-scores.csv) · [Position charts](charts/index.html) · [Prior CTU input qualification](../../original-schedule/prague-transfer/README.md)

## Geographic and held frequency scores

Each row below is one position from a single training visit. The frequency values are medians across the captures on the opposite visit. The April holdout uses future May captures and supplies a retrospective check. The May holdout uses April captures. Errors are horizontal distance to the survey. `Phase + clock` is the pooled estimate that fits both orbit phase and an affine frequency clock.

| Held visit | Method | Forced error (km) | Training objective (Hz RMS) | Whole-capture curvature (Hz RMS) | Prefix-conditioned tail (Hz RMS) |
| --- | --- | ---: | ---: | ---: | ---: |
| April 24 | Fixed phase, intercept | 3.62 | 2,692 | 2,639 | 3,106 |
| April 24 | Fixed phase, affine clock | 3.62 | 2,623 | 2,639 | 3,106 |
| April 24 | Profiled phase, intercept | 3.13 | 2,599 | 2,637 | 3,084 |
| April 24 | Phase + clock | 5.33 | 2,566 | 2,644 | 3,221 |
| April 24 | Median of capture fits | 9.78 | 2,570 | 2,655 | 3,422 |
| April 24 | Offer centre | 4.41 | 2,567 | 2,644 | 3,208 |
| May 7 | Fixed phase, intercept | 4.08 | 2,725 | 2,604 | 2,597 |
| May 7 | Fixed phase, affine clock | 4.08 | 2,637 | 2,604 | 2,597 |
| May 7 | Profiled phase, intercept | 4.08 | 2,646 | 2,604 | 2,597 |
| May 7 | Phase + clock | 4.08 | 2,605 | 2,604 | 2,597 |
| May 7 | Median of capture fits | 4.08 | 2,605 | 2,604 | 2,597 |
| May 7 | Offer centre | 4.41 | 2,661 | 2,586 | 2,432 |

The 11 Prague captures contain 19 author-selected tracks and 7,161 measured frequency rows at one physical rooftop. The independent, whole-capture frequency score removes the constant and linear components of measured and nominal-phase predicted frequency using the same fixed linear operator. It uses zero fitted parameters from the held capture. The tail score calibrates intercept, drift, and phase on the first 40% of each held track while holding the predicted receiver position fixed. It scores the last 60%. The table uses the same tail calibration for every position. Method-specific tail forecasts are also in the full score table. Individual same-capture fit errors had medians of 4.08 km in April and 9.62 km in May. Those fits used the entire capture. The group median uses individual estimates from the training visit only. [Frequency scores](frequency-scores.csv) · [Frequency chart and exact plotted medians](session-geometry-held-frequency.pdf) · [Stage CSV](session-geometry-held-frequency-visit-medians.csv) · [Individual fits](per-capture-scores.csv)

### Orbit and search controls

- Shuffling training CFO order raised training RMS from 2.57 and 2.61 kHz to 86.48 and 68.32 kHz. Both shuffled positions had 9.50 km error. Rotating all training orbits by 90° about the city's radial axis gave nearly the same training RMS as the tied orbits and forced errors of 6.89 and 9.50 km. This rotation preserves much of the local range-rate geometry under a corresponding rotation of the receiver position. [Geographic scores](geographic-scores.csv)
- A post-release control reassigned each track to a real trajectory from the next capture on the same date. Both variants used the same central 32 seconds and the same coordinate and phase grids. The swapped trajectories raised training RMS from 2.31–2.49 kHz to 6.92–6.98 kHz and forced error from 3.76–4.54 km to 12.89 km. The whole-capture curvature medians changed by less than 1 Hz on the correctly paired opposite visit. That narrow-window score had little power to distinguish the geographically different estimates. [Cross-orbit control](cross-orbit-scores.json)
- The offers were 12 km squares based on the public city centre. The four near offers moved 12.5 km along the cardinal bearings. The four far offers moved 45 km along each axis of the diagonal bearings. The scorer checked that all nine rectangles were pairwise disjoint. Near offers omitted the survey by 3.32–9.68 km at the closest separating face. Far offers omitted it by 35.95–42.58 km. Every pooled method reached the face on every omitted offer. All four training methods withheld both containing fits. [Offer and survey release](survey-release.json) · [Prague position charts](charts/index.html)

### Simulation recovered the grid cell with nominal timing

The first experiment simulated 20 circular LEO arcs across two visits near Montevideo. It added phase errors of 0.5–1.0 s in either direction, independent frequency offsets and drift, and FFT-bin quantization. Phase + clock missed the sealed 1 km criterion with forced errors of 3.27 and 2.89 km. The rotated-orbit control gave nearly the same training RMS. [Shifted-orbit simulation](positive-simulation.json)

A separate Montevideo check used independently generated longer arcs with nominal ephemeris timing. The simulator measured Doppler by finite differences of slant range and added frequency offsets, drift, noise, and bin quantization. All four pooled models found the survey's 0.5 km grid cell on both directions. The grid-aligned survey gives a recorded horizontal error of 0 km. The fixed model published both positions. Phase + clock withheld both because its training gains relative to the fixed centre were below the 244 Hz publication threshold. With Phase + clock, the curvature medians were 79 and 83 Hz at the recovered position and 492 and 519 Hz at the offer centre. This check covers nominal ephemeris timing and a wider observation interval than the shifted-orbit experiment. [Nominal-orbit simulation](nominal-score.json) · [Nominal predictions](nominal-predictions.json)

## Search and input boundary

The trial converts WGS84 coordinates at 250 m to ECEF. For a candidate position it predicts measured frequency from minus the slant range rate times the nominal RF divided by the speed of light. All four training modes evaluate the same 625 receiver grid points. They share the same per-track intercept model. The objective weights each capture equally and each track equally within a capture. Phase profiling interpolates the supplied ECEF position and velocity over a ±2 s range at 0.25 s intervals. The penalty adds one squared export-bin at a 0.5 s shift, roughly 4 km along a LEO trajectory. The optional clock rate clips at ±20 Hz/s. The training-only publication guard withholds a point within half a grid spacing of a face or with less than 244.14 Hz gain in its penalized training RMS over the offer centre. [Study plan](study-plan.json) · [Trial lock](trial-lock.json)

The sealed input loader passes raw measured CFO, relative sample time, and unshifted ECEF to the solver from one export per distinct timestamp. The solver also receives the public search offer and fixed nominal height. The CTU extraction used the survey upstream to select tracks and peak windows. The 11.325 GHz nominal RF gives any additive RF calibration coefficient `c` a constant regressor. A free track intercept absorbs any change in that regressor exactly. Every `fitted_c` endpoint is explicitly unavailable. [CTU thesis and deposit](https://hdl.handle.net/10467/184304) · [Prediction lock](prediction-lock.json) · [Pre-survey score plan](score-plan-lock.json) · [Score lock](score-lock.json)

One host run pinned to logical CPUs 20–21 with one BLAS thread used 36.05 CPU seconds and 36.31 wall seconds for Prague across all nine offers. The simulation took 7.59 CPU and wall seconds for the same nine offers. Scoring held captures took another 1.51 CPU seconds across both sites. Lattice time includes all four training modes and both nulls. It measures the replay after inputs were decoded and excludes author-side track extraction. These times describe the recorded run. [Lattice timing](resources.json) · [Held scoring timing](predictions.json)

## Reproduce from the authenticated archive

Put the CTU `outputs.zip` under `LOCAL_SOURCES` with the SHA-256 recorded in `study-plan.json`. Use a fresh `NEW_REPORT` directory and run these commands from the repository root. The source archive stays outside the repository.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
taskset -c 20-21 .venv/bin/python -m tools.pipeline_eval.qualification.session_geometry_trial LOCAL_SOURCES --out NEW_REPORT
taskset -c 20-21 .venv/bin/python -m tools.pipeline_eval.qualification.session_geometry_results LOCAL_SOURCES --out NEW_REPORT
taskset -c 20-21 .venv/bin/python -m tools.pipeline_eval.qualification.session_geometry_stage_values --out NEW_REPORT
taskset -c 20-21 .venv/bin/python -m tools.pipeline_eval.qualification.session_geometry_nominal_check --out NEW_REPORT
taskset -c 20-21 .venv/bin/python -m tools.pipeline_eval.qualification.session_geometry_cross_orbit LOCAL_SOURCES --out NEW_REPORT
```

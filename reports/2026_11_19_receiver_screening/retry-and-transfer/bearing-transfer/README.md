# Relative phase on the measured StarLoc array

The joint phase-and-Doppler solver withheld on all **22 anonymous offers** from eleven recordings over eight GNSS sites. On the first capture at each site, its median forced error in the containing square was **14.09 km**, compared with **14.74 km** for matched Doppler and **7.95 km** for the tile centres. The phase changes carried evidence about direction and orbit assignment. Across the eight first captures, the best held horizontal conditioning estimate was **33.11 km**, above the **5 km** gate. [Held phase and conditioning](measured-phase-support.png) · [Position charts](charts/README.md) · [Scores](scores.csv)

## Observable

The staged StarLoc data retain the three complex FFT values measured in the same beacon bin. We form two cross-products on the orthogonal 13.25 cm baselines and difference their circular phases over about three seconds. This cancels transmitter phase, constant relative channel phase and a constant spatial ambiguity integer. The forward model uses the two changes in horizontal line-of-sight direction in the local level plane, rotated by one unknown yaw and scaled by the published antenna spacing and wavelength. A whole-array polarity reversal is equivalent to adding 180° to yaw. Reflecting one baseline changes the handedness and gives a distinct test. The receiver uses no measured or site-calibrated attitude or phase. [Release and calibration audit](SOURCE.md) · [Frozen protocol](PROTOCOL.md)

The eleven captures contain **371,441** complex FFT rows in 81 author-prepared arcs. The observation-only duplicate test rejected one possible harmonic copy. There were **234** local phase and Doppler pairs before requiring two training and two held pairs per arc. The eight first captures then supplied **45 training and 45 held pairs over 22 arcs**. Three repeat captures supplied another 16 pairs in each split. The solver saw two to four qualifying arcs per capture. The candidate shortlist combined the two relevant screens so that the blind baseline and joint fit used the same candidates and search budgets. [Source and support inventory](measurement-inventory.json) · [Forecast receipts](positions.jsonl.gz)

The nominal RF is 11.325 GHz throughout. The short Doppler-frequency difference cancels any fixed additive RF calibration coefficient before fitting. Both model comparisons therefore have one numerical `c=0` arm and an unavailable fitted `c` arm. Phase RMS in radians and Doppler-rate RMS in Hz/s measure conditional held residuals. Position error comes from the independent GNSS evaluation.

## Held phase and causal identities

Across the eight first containing captures, the joint fit had median held phase vector RMS of **0.135 rad**. The one-step shuffle of held paired phase changes within each arc gave **0.145 rad** and the reflected-baseline control gave **1.442 rad**. The real phase fit beat those controls in **6/8** and **8/8** captures respectively. The small separation from the time shuffle is consistent with phase increments changing slowly on the short arc segments. Median held Doppler-rate RMS was **66.49 Hz/s** in the joint blind fit and **68.72 Hz/s** in the matched blind Doppler fit. [Per-site residuals and nulls](scores.csv)

The blind joint fit agreed with the author-supplied identities on **21/22** first-capture containing arcs. The Doppler-only fit agreed on **19/22**. The authors derived those IDs using site information, so this comparison measures agreement with their assignments. At site 05 the blind phase fit agreed on all four arcs, reduced conditional held phase RMS from **0.542 to 0.133 rad** and changed forced error from **11.88 to 6.75 km**. At site 08 the blind joint model still selected an alternative NORAD. Its held phase RMS was **0.122 rad** compared with **0.130 rad** using the author ID, while held Doppler-rate RMS was **124.35 versus 57.36 Hz/s**. That conflict leaves the identity unresolved. [Orbit alternatives and held margins](orbit-comparisons.csv)

## Geographic evaluation

| First physical capture | Anonymous joint forced km | Matched Doppler forced km | Author-ID joint / Doppler forced km | Anonymous joint held phase RMS, rad | Anonymous joint near-missing forced km |
| --- | ---: | ---: | ---: | ---: | ---: |
| Site 01 | 25.15 | 27.07 | 25.15 / 27.07 | 0.083 | 29.05 |
| Site 02 | 11.25 | 11.31 | 11.25 / 11.31 | 0.140 | 16.98 |
| Site 03 | 24.64 | 24.47 | 24.64 / 24.47 | 0.212 | 47.05 |
| Site 04 | 8.59 | 7.88 | 8.59 / 7.88 | 0.224 | 25.99 |
| Site 05 | 6.75 | 11.88 | 6.75 / 7.54 | 0.133 | 19.33 |
| Site 06 | 3.58 | 4.21 | 3.58 / 4.21 | 0.073 | 17.37 |
| Site 07 | 19.92 | 19.33 | 19.92 / 19.33 | 0.138 | 26.27 |
| Site 08 | 16.92 | 17.60 | 12.26 / 9.98 | 0.122 | 19.73 |

The joint blind fit improved on the containing centre at **2/8** sites. With the authors’ orbit IDs, median forced error was **11.75 km** for the joint fit and **10.65 km** for Doppler alone. The three repeat captures produced blind joint forced errors of **13.14, 5.53 and 9.30 km** in their containing squares. For the primary blind joint fits, the weakest-axis conditional scale was **33.11–266.37 km** after eliminating yaw. It derives from the fixed-assignment held Jacobian and residual scales. It supplies a local diagnostic rather than a calibrated geographic error bound.

Every displaced offer put the actual receiver outside the nearest edge by **13.94–22.42 km**. The first-capture near-missing forced median was **22.86 km** for the blind joint fit and **23.86 km** for blind Doppler. On matched first-capture offers, held score favored the containing square on **5/8** blind joint fits and **6/8** blind Doppler fits. The geometric ambiguity survives the extra observable and the author-ID ceiling. These captures use a separate shared-clock phased array. The evidence applies to that instrument configuration.

All 44 sandbox workers completed. Across them, median CPU time was **1.24 s**, median elapsed time including handoff was **1.85 s**, and maximum RSS was **154.84 MiB**. Three component tests cover raw complex phase cancellation, the common-yaw polarity symmetry and assignment across distinct tracks. The source and decision lock bind all measured requests before GNSS scoring. [Prediction seal](prediction-lock.json) · [Scoring seal](score-lock.json)

## Reproduce

```bash
nice -n 10 taskset -c 18,19 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.bearing_transfer_trial \
  "$STARLOC_MAT_ROOT" --calibration "$STARLOC_CALIBRATION_AUDIT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.bearing_transfer_results
.venv/bin/python -B -m tools.pipeline_eval benchmark --study \
  reports/2026_11_19_receiver_screening/retry-and-transfer/bearing-transfer --pack
```

`STARLOC_MAT_ROOT` is the directory with the eleven original timestamp subdirectories. The optional calibration audit directory holds the same release's small MAT files as `<timestamp>-calibration.mat`. The calibration check can be omitted without changing the solver input.

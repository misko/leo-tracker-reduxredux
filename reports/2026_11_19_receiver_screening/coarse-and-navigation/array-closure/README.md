# Cross-satellite phase closure on StarLoc

Absolute phase differences between satellite tracks beat both held shams at every site with usable support. They also improved the local geometry diagnostic. Across the five first-capture sites with exact overlap, the forced position had a **12.30 km median error**, compared with **10.88 km** from matched Doppler and **8.79 km** from the offered tile centres. The wire-stable extension reached all eight sites, with a **13.01 km** forced median against **12.69 km** for Doppler and **7.95 km** for the centres. All anonymous offers withheld. [Support and phase controls](array-closure-evidence.png) · [Position charts](charts/README.md) · [Scores](scores.csv)

## Measurements and calibration

Each released beacon observation carries complex FFT coefficients for the three receivers in the same spectral bin. We take the two unit baseline cross-products and then subtract **absolute baseline phase between two distinct tracks** at each endpoint of a measurement interval. The causal model predicts the difference of the two horizontal line-of-sight vectors, projected onto the two 13.25 cm baselines with one unknown yaw. Its circular likelihood accounts for integer phase cycles directly. The two control solvers use the same four endpoint observations and the same shortlist, with either within-track phase changes and Doppler or Doppler alone. [Frozen protocol](PROTOCOL.md) · [Source and calibration authority](../../retry-and-transfer/bearing-transfer/SOURCE.md)

The exact calculation cancels any additive channel phase common to both measurements at a native timestamp. It retains phase from the angular separation of the sources. The second calculation uses independently timed visits and subtracts interpolated phase from injected hardware references. Those samples verify the downstream SDR path. Phase changes upstream of the injection point, differential receiver phase across beacon frequencies and deviations from the level-array approximation remain potential confounders. The solve never receives the auxiliary orientation or the survey-assisted on-air phase calibration. [Published receiver and calibration design](https://arxiv.org/html/2604.21147v1#S4.SS2) · [Pinned baseline and phase processing](https://github.com/GiddaZhang/Starloc/blob/fc010f950dfac5ac6d7a345db24513217fbb81d5/Starloc_generate_results.py#L69-L151)

Exact, non-harmonic overlap appeared in **8/11** captures across six sites, totaling **10,684** native pair-epochs before applying the stencil gates. Train and held support survived for **eight disjoint pairs from six captures**, including first captures at five sites. Sites 04 and 06 each furnished two independent exact measurement pairs. The wire-stable scope retained **24 disjoint pairs** from all eleven captures, with 35 training and 39 held stencils. Its endpoint separation median was **28.74 s**, with a maximum of **59.10 s**. Of the 74 stencils, 73 had noncoincident mean endpoint times. Maximum downstream reference excursion within the admitted brackets was **0.084 rad**. [Native endpoint and reference inventory](paired-support.json)

## Held phase and identity

| First capture at each site | Fitted sites | Held phase RMS, rad | Time shuffle / orbit swap, rad | Matched closure / temporal / Doppler rate RMS, Hz/s |
| --- | ---: | ---: | ---: | ---: |
| Exact containing | 5 | 0.243 | 1.264 / 2.837 | 66.57 / 78.88 / 78.38 |
| Wire-stable containing | 8 | 0.205 | 1.901 / 2.415 | 52.25 / 48.82 / 63.19 |

Rates and phase entries are medians of conditional held RMS. The holdout fixes each training-selected orbit tuple and yaw. The time sham moves the two-baseline phase vectors within the held pair. The identity sham swaps the orbits while preserving the original measurement times. Both controls lose at **5/5** exact sites and **8/8** wire-stable sites. The exact solver retained just **one** pair that cleared the training and held identity gates per fitted first capture.

The separately label-aided ceiling reproduced the blind closure's containing endpoints. The blind selections agreed with the author ID tuples on **7/7** exact pairs and **18/18** wire-stable pairs in first containing captures. These author labels are site-assisted and supply a corroborating assignment comparison. A residual diagnostic permitting one phase bias per pair reduces the median exact held RMS from **0.243 to 0.160 rad** and the wire-stable RMS from **0.205 to 0.146 rad**. This indicates phase mismatch beyond the modeled angular difference, with contributions from array and orbit errors left unresolved. [Pair-level assignments and residuals](pair-diagnostics.csv)

## Geography

| First captures and offers | Sites with forced estimates | Tile centre median km | Closure forced km | Temporal phase forced km | Doppler forced km |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact containing | 5/8 | 8.79 | 12.30 | 11.54 | 10.88 |
| Exact near-missing | 5/8 | 33.36 | 23.70 | 25.44 | 20.05 |
| Wire-stable containing | 8/8 | 7.95 | 13.01 | 10.93 | 12.69 |
| Wire-stable near-missing | 8/8 | 32.22 | 21.05 | 21.72 | 25.30 |

The exact closure containing errors spanned **3.25–14.61 km** on the five fitted sites and improved on the centre at two of them. The wire-stable range was **6.88–19.98 km**, with an improvement at one of eight. Site 03 was the closest exact forced result at **3.25 km** and the wire-stable fit on that recording was **16.99 km** from the survey. Each near-missing square excluded the receiver by **13.94–22.42 km** from its closest edge. Matched held score favored the containing offer on **5/5** exact and **7/8** wire-stable captures for closure. Doppler alone achieved the same counts. All estimates in the table are forced diagnostics.

With one shared yaw, the median weakest-axis conditional scale was **36.72 km** for exact closure and **24.14 km** with wire-stable measurements, compared with **46.93 km** and **29.38 km** for matched Doppler. Giving each data pair an additional fixed phase bias increased those closure scales to **45.98 km** and **31.67 km**. The best first-containing closure scales were **25.76 km** exact and **15.21 km** wire-stable. Both exceed the **5 km** publication gate. These are held local sensitivity diagnostics conditional on the selected orbit tuples, noise scales and calibration model. The experiment measures one shared-clock phased array at eight nearby physical locations.

The single nominal RF makes the static fitted `c` term a constant within each track. The Doppler differencing annihilates that column in both phase fits and the matched control. The fitted arm is unavailable. All **44** workers completed under the 40 s deadline at a median **1.63 s CPU**, **3.23 s elapsed** including handoff and **155.14 MiB** maximum RSS. The deadline replay reproduced all 264 fit decisions and numerical outputs. Four component tests cover exact cancellation, rejection of staggered timestamps as simultaneity, wire-reference gates and circular cycle invariance. [Locked blind predictions](prediction-lock.json) · [Scoring seal](score-lock.json)

## Reproduce

```bash
nice -n 10 taskset -c 18,19 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.array_closure_trial \
  "$STARLOC_MAT_ROOT" "$STARLOC_CALIBRATION_AUDIT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.array_closure_results
.venv/bin/python -B -m tools.pipeline_eval benchmark --study \
  reports/2026_11_19_receiver_screening/coarse-and-navigation/array-closure --pack
```

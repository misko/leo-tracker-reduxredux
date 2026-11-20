# What the measured field arcs say about receiver clock calibration

No new compatible wideband source was found in the bounded primary-source search. On measured StarLoc field arcs, using an effective clock correction transferred from seven other sites improved held RF RMS at only **two of eight** primary sites and none of the three repeats. At the known survey point, the median conditional worst-axis position scale was **6.15 km** with fixed UTC, **15.21 km** with free common UTC and **55.25 km** with free per-orbit epochs. The supplied identities and GNSS geometry make this an information diagnostic on measured RF. [Source inventory](source-inventory.md) · [Held measurements and chart](field-clock-evidence.png)

## Held frequency and geographic discrimination

The eleven acquisitions cover eight physical sites using the same instrument, with a second capture at three sites. Author-supplied satellite identities and GNSS latitude, longitude and height are evaluator aids. The test uses all suitable measured arcs, including the two sites where the earlier simultaneous-frequency experiment found zero contrast. Each arc contributes one actual timestamp per 2 s bin. The early half determines the arc level and a common linear frequency drift. The late half evaluates exact causal SGP4 predictions with those early terms fixed. The donor shift and residual scale exclude the target site and every repeat at that site. [Protocol and site exclusions](PROTOCOL.md) · [Prior simultaneous-frequency boundary](../../streamlined/measured-transfer/README.md)

| UTC applied in exact late propagation | Primary median held RF RMS | Primary improvement over reported UTC | Repeat median held RF RMS | Repeat improvement |
| --- | ---: | ---: | ---: | ---: |
| Reported UTC | 183.8 Hz | — | 228.3 Hz | — |
| Effective shift from early local arcs | 311.0 Hz | 3/8 | 276.6 Hz | 0/3 |
| Effective shift from other primary sites | 224.1 Hz | 2/8 | 344.7 Hz | 0/3 |

The early local estimates ranged from −1.520 s to +1.523 s over all eleven acquisitions and stayed within the prespecified ±2 s interval. They combine receiver timing, orbit phase and model error. The shifted late forecasts use actual propagated states. The linear approximation estimates only the proposed shift. Fitting carrier levels and a drift early at each alternative location, the survey point beat all four 5 km axial alternatives at 3/8 primary sites and 1/3 repeats using reported UTC, and at 1/8 primary sites and 0/3 repeats using the donor shift. This directly tests measured discrimination at 5 km with labelled orbits. [Per-capture residuals and alternatives](results.json)

## Conditional information in the measured geometry

After removing the arc levels and one affine frequency drift, a common UTC shift is proportional to the vector of per-sample Doppler time derivatives. The derivative for each orbit’s effective prediction timestamp is the same vector restricted to that orbit. Their sum is the common UTC column. In all eleven captures, projecting that column against the per-orbit timestamp span left at most `1.61e-15` of its original norm. This exact local gauge applies to effective prediction timestamps, which include Earth rotation. A dynamical along-track phase model evaluated at fixed Earth orientation gives a different nuisance column. A constant `c` at this single nominal RF is also absorbed by the arc levels, and the two calibration arms coincide.

| Timing assumption | Primary median worst horizontal scale using site-excluded residuals | Median with FFT quantization scale only |
| --- | ---: | ---: |
| Fixed UTC and fixed orbit epochs | 6.15 km | 0.70 km |
| 50 ms UTC prior, fixed orbit epochs | 6.16 km | 0.76 km |
| 500 ms UTC prior, fixed orbit epochs | 6.63 km | 1.60 km |
| Free common UTC, fixed orbit epochs | 15.21 km | 1.80 km |
| Free per-orbit epochs | 55.25 km | 6.19 km |

These scales divide a site-excluded RF RMS by the weakest horizontal singular value after profiling clock and carrier terms. They assume independent residuals and a fixed height. The 50 and 500 ms assumptions are sensitivity cases, with no measured external reference at those precisions in this archive. Even using fixed UTC and orbit epochs, all eight primary scales exceeded 5 km at the measured residual level. Quantization-only calculations give considerably smaller values, leaving orbit and receiver model residuals material. The diagnostic produces no new location estimates. Numerical work on CPU 2 took 0.75 s for 1,309 retained samples across the eleven acquisitions, after loading the released MAT arrays. [Frozen sources and input authority](source-lock.json) · [Sealed numerical results](results-lock.json)

## Reproduce

For a new run, copy `PROTOCOL.md` into an unused output directory. The figure reader works directly on the existing sealed result files.

```sh
cp reports/2026_11_19_receiver_screening/detector-origins/field-clock/PROTOCOL.md "$OUTPUT/"
nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 2 .venv/bin/python -B -m tools.pipeline_eval.qualification.external_clock_trial \
  --raw "$STARLOC_MAT_ROOT" --out "$OUTPUT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.external_clock_figure --out "$OUTPUT"
```

# Compiled scalar Doppler noise filter

Both complete receivers returned 14 of the same 18 measured roof fixes and withheld all three omitted offers. Across 42 calibration results, their largest forced-position difference was 10.95 micrometres and their largest conditional RF RMS difference was 0.0000000185 Hz. All dense controls reproduced their archived decisions and coordinates. Six additional roof recordings were selected by hash after the first scalar-filter trial and before this comparison ran. [Roster and source hashes](plan.json) · [Position and frequency errors](scores.csv)

The compiled version applies the existing scalar white-plus-correlated noise model directly to the time samples. A C11 loop handles batches and strided columns without assembling or factorizing a dense matrix. The library was compiled before timing. Each pair rebuilt the complete tracks and causal orbital bank from the same GLRT factors and ran the same geographic solver. The methods alternated which ran first on one host CPU. [C recurrence](../../../../tools/pipeline_eval/variants/innovation_filter.c) · [Original filter experiment](../innovation-noise/README.md) · [Trial conditions](PROTOCOL.md)

| Measurement on 18 roof recordings | Dense covariance | Compiled scalar filter |
| --- | ---: | ---: |
| Median stored noise-operator bytes per recording | 1,150,836 | 177,488 |
| Median complete receiver CPU, seconds | 3.472 | 3.505 |
| Median position-fit time, seconds | 0.380 | 0.419 |

The stored noise representation was 6.48 times smaller. Median paired cost rose by 27 ms of complete worker CPU, 28 ms in the fit and 428 KiB of process peak RSS. The host measurements support the algorithm’s smaller storage requirement. They provide no measured full-worker speed or memory gain. In the fitted-calibration arm, RF RMS decreased on all 18 roof cases and geographic error improved on nine of 14 shared published fixes. [Paired resources](resources.csv) · [Calibration ablation](summary.json)

[Fitted-calibration roof chart](../charts/fitted_c/compiled_innovation-roof.png) · [Zero-calibration roof chart](../charts/c0/compiled_innovation-roof.png) · [Omitted-region chart](../charts/fitted_c/compiled_innovation-omitted.png)

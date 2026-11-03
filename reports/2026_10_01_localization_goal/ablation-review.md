# Complexity ablation of the current joint baseline

The strongest simplification supported by this study is one acquisition-ranked starting location instead of three. Timing flexibility remains important; receiver drift has a smaller benefit. This is an ablation study of the original fully benchmarked robust joint model, not of the newer satellite-balanced alternative.

## Search complexity: all64regression scans

Replay exactly the original selection rule over the first one, two, or three independently fitted seeds. Every seed starts with zero nuisance coordinates at its acquisition-proposed position; no previous-scan state or GPS enters inference. Select the lowest objective even if that seed is unresolved, preserving the original failure rule rather than falling back to a worse score. All prefixes happen to yield64accepted scans.

| Starting locations | Accepted | Median error | p90 error | Within1km | Within3km | Median recorded fitting work omitted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 64/64 | 1,914.98 m | 5,329.72 m | 11/64 | 46/64 | 7.70 s |
| 2 | 64/64 | 2,001.79 m | 5,850.75 m | 10/64 | 48/64 | 3.43 s |
| 3, baseline | 64/64 | 2,059.90 m | 5,850.75 m | 10/64 | 47/64 | 0 s |

The first seed is chosen by the acquisition score, not by geographic error. Extra starts can locate a better optimum of a misspecified objective while worsening geography. These results support reducing search work on this corpus; they do not prove other location modes cannot matter on new recordings.

After inspecting the regression, evaluate the fixed one-start versus three-start comparison on16previously reserved DS12 recordings, without tuning the rule:

| DS12 starting locations | Accepted | Median error | p90 error | Within1km | Within3km | Median recorded fitting work omitted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 16/16 | 2,101.58 m | 4,125.48 m | 3/16 | 13/16 | 5.63 s |
| 3 | 16/16 | 2,101.58 m | 4,138.23 m | 3/16 | 13/16 | 0 s |

This uses sealed saved seed fits, not a newly timed acquisition-and-fit run. Omitted fitting work is an accounting estimate. No new cold CPU/runtime claim is made. DS12 is temporally related, at the same unsurveyed reference site, and was previously evaluated for the baseline; it is not independent site validation or an untouched final test set for future tuning.

## Parameter complexity: matched12scan conditional ablations

Hold original baseline satellite assignments fixed and use identical observations, robust Student-t4 residuals, surviving Gaussian priors, uniform Sacramento support and30.48mMSLheight. Remove designated coordinates by fixing them exactly to zero, then jointly optimize position and all surviving nuisance coordinates. This isolates continuous-model flexibility conditional on the full model's identities. It does not test acquiring and associating from scratch under each reduced model.

| Conditional model | Accepted | Median error | p90 error | Median warm wall / CPU |
| --- | ---: | ---: | ---: | ---: |
| Full control | 12/12 | 1,892.15 m | 3,998.11 m | 1.861 / 1.802 s |
| Shared clock fixed zero | 12/12 | 3,268.88 m | 7,585.96 m | 3.026 / 2.869 s |
| Both receiver drifts fixed zero | 12/12 | 2,055.82 m | 4,093.63 m | 2.395 / 2.289 s |
| All satellite epoch corrections fixed zero | 12/12 | 3,710.52 m | 6,467.96 m | 2.387 / 2.316 s |
| Position only; all nuisance coordinates zero | 12/12 | 7,807.57 m | 12,532.67 m | 2.550 / 2.473 s |

Controls start at their existing stationary solution and return without a step; the reduced models must refit after parameters are zeroed. Consequently these timings do not measure the cold computational saving of removing parameters. All60results pass independent source/input/height/assignment checks, exact zero-fixed coordinates, reconstructed objective/metric, monotonicity and finite-difference stationarity. The coordinate-removal invariant test passed. At most2fitting processes,64iterations,25sinternal/30sexternal caps, no retries or newRF.

![Separate search and parameter ablations](ablation-v1.png)

## Where complexity is warranted

- **Multiple optimizer starts:** not justified as the default by these regression and DS12 results. One start is the leading simplification candidate; measure a fresh cold pipeline before claiming its wall-time improvement or changing the published baseline.
- **Shared and per-satellite timing flexibility:** strongly supported by conditional error degradation when removed. This does not identify physical hardware-clock or orbit errors; the parameters can absorb other mismatch.
- **Receiver drift:** modest benefit on the development panel; retaining two scalars is inexpensive. There is insufficient evidence to remove it for accuracy, and cold runtime savings have not been measured.
- **Position-only fitting:** inadequate in this comparison.

Clock and satellite epochs have an important modeling redundancy: predictions depend on total satellite time correction d_s=c+e_s. With c~N(0,1s²) and independent e_s~N(0,0.25s²), the same Gaussian model can be represented directly as d~N(0,0.25I+11ᵀ) for fixed identities. Thus common timing correlation is supported here, but a separate explicit clock coordinate need not be essential to the implementation. Fixing c=0 changes that correlation; it is not equivalent to algebraically collapsing the original prior. Earlier gauge analysis already verified this distinction.

This study does not isolate robustness, covariance structure, or hard versus soft association under the current exact pipeline. Earlier soft-association and residual-family experiments are relevant context but are not substituted into these matched tables. Nominal curvature remains uncalibrated; no uncertainty-coverage success follows from simplification.

Artifacts: `seed-count-ablation-v1.json`, `seed-count-heldout-ablation-v1.json`, and `ablation-v1-evaluation.json`, with SHA seals; source/receipt freeze in `ablation-v1/`. The3seed replay exactly reproduces original regression and DS12 median errors. The figure was visually inspected. Existing baseline reports and golden fixtures remain unchanged.

Next: validate the one-start policy with fresh bounded acquisition-and-fit timing, then consider exact clock/epoch prior collapse as an implementation simplification rather than a new geographic model. The1kmmedian/3kmp90goal remains unmet.

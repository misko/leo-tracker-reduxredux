# Shared clock and marginal track offsets

The combined clock and offset model with white-plus-OU noise passed the locked challenge criterion. On the six reserved recordings it improved paired median geographic error and held predictive deviance against both single-term controls in both calibration arms. The diagonal model had smaller median paired geographic errors on the shared reserved fixes and substantially higher held deviance. All four models withheld all three investigated wrong offers.

## Evidence and model

One anonymous native Graph and unchanged joint receiver run selects the training tracks, initial held gate, final owners, aliases and weights. Every model uses those same data and starts in both arms. The three exact geometry updates fit position, orbit phases and receiver calibration. The full smooth clock adds 22 pinned RF-fractional columns across both receivers, shared between the low and high RF groups within each receiver. A 1000 Hz Gaussian constant per Graph track is integrated with a rank-one whitened update, adding zero dense fit columns. The original white-plus-OU noise is 150 Hz independent noise plus a 200 Hz correlated component with 4 s decay. The diagonal arm keeps only the 150 Hz term during refinement and held scoring. Source parameters and the small test roster were fixed before geographic results.

Held prediction trains the shared model on disjoint tracks. The target track's first two thirds nominate its orbit and CFO alias once for all four models; the rest of the data scores a conditional Gaussian forecast. The prefix conditions the track constant and any OU noise state. The score includes the suffix covariance determinant. This is a whole-capture training split with a forward suffix within each held track, using plug-in shared states. The original publication gate retains its native first-fit forecast. Final geographic publication also uses each model's geometry under the same thresholds.

The first four were DS26-0211, DS26-0187, DS26-0052 and DS26-0074. The reserved six were DS26-0257, DS26-0068, DS26-0271, DS26-0146, DS26-0120 and DS26-0098. Locked wrong offers placed the site 41.80 km, 22.87 km and 1.24 km beyond a tile edge. Both single-term controls reproduced independent archived forced endpoints exactly on twelve eligible requests with matched native input and Graph digests.

## Reserved challenge

| Model | Published of 6 | Median error c=0 / fitted c (km) | Median conditional held RF RMS (Hz) | Median held deviance per point |
| --- | ---: | ---: | ---: | ---: |
| Clock and offset, OU | 5 / 5 | 1.037 / 0.970 | 1,127.4 / 1,127.0 | 22.126 / 22.121 |
| Clock and offset, diagonal | 5 / 5 | 1.128 / 1.122 | 1,300.0 / 1,300.0 | 64.569 / 64.569 |
| Clock only, OU | 5 / 5 | 1.696 / 1.250 | 1,747.8 / 1,683.2 | 35.071 / 35.288 |
| Offset only, OU | 5 / 5 | 1.426 / 1.412 | 1,129.2 / 1,128.9 | 22.106 / 22.102 |
| Original no repair | 6 / 6 | 0.708 / 0.625 | — | — |

On common fixes, adding the offset to the OU clock model reduced geographic error by paired medians of 659 m and 288 m. Adding the clock to the OU offset model reduced it by 421 m and 423 m. The combined OU model lowered held deviance per point by paired medians of 14.44 and 14.66 versus clock-only, and 0.04694 and 0.04677 versus offset-only. Paired and separately aggregated medians answer different questions and are reported separately.

Replacing OU with diagonal noise in the combined model improved paired geographic errors by 241 m and 249 m on the reserve. Conditional fit RMS fell by about 10 Hz in each arm. Conditional held RMS rose by 119.5 Hz and 120.2 Hz, and deviance rose by 43.37 per point in each arm. On the first four, the diagonal and OU versions both returned all fixes and their geographic medians were 1.274/1.293 km and 1.612/1.612 km, respectively. The full replay was triggered by the reserved OU result under the test plan.

The 13-query paired challenge completed in 27.9 s. Median worker wall, holding all four fits and forecasts, was 7.67 s. Median peak resident memory was 140.7 MiB under a 512 MiB address-space cap. The corrected measured run followed an infrastructure preflight in which the rank-one whitening wrapper lacked the scalar interface used by the existing optimizer. That preflight produced no predictions. Its failed receipts remain in the preflight folder. The same formulas and roster were used after the interface correction.

The [standard figures](figures.json) and per-recording scores preserve both arms and separate forced diagnostics. Held RMS is the suffix prediction error after prefix conditioning. Final fit RF RMS after estimating a component constant is an in-sample statistic.

## Complete native panel

The promoted run measured all 135 true roof and nine omitted offers on the unchanged combined and single-term models. Each query yields four paired results from one authenticated native factor read and Graph pass. The final, training and held-prefix assignment digests and held suffix sizes matched across all four models and both calibration arms. Every model withheld all nine wrong offers. The two single-term controls independently reproduced their archived request, Graph, training and final owner receipts, publication status and forced endpoints on all 144 queries. The [archive reproduction receipt](full/archived-control-reproduction.json) identifies both historical locks.

| Model | Published of 135 | Median geographic error c=0 / fitted c (km) | P90 error (km) | Within 1 km |
| --- | ---: | ---: | ---: | ---: |
| Clock and offset, OU | 114 / 114 | 1.293 / 1.291 | 3.294 / 3.268 | 38 / 41 |
| Clock and offset, diagonal | 113 / 113 | 1.324 / 1.318 | 3.181 / 3.160 | 41 / 41 |
| Clock only, OU | 119 / 119 | 1.530 / 1.284 | 3.461 / 3.629 | 35 / 41 |
| Offset only, OU | 118 / 118 | 1.451 / 1.450 | 3.452 / 3.513 | 36 / 37 |
| Original no repair | 135 / 135 | 0.982 / 0.988 | 2.284 / 2.155 | 72 / 69 |

On 112 shared fixes, the combined OU model reduced paired median error by 169 m and 5 m against clock-only. Its held suffix RMS fell by 204 Hz and 208 Hz, and held deviance per point fell by 3.051 and 3.073. On 113 fixes shared with offset-only, paired geography improved by 102 m and 130 m, held RF by 5.74 Hz and 5.72 Hz, and held deviance per point by 0.01305 and 0.01311. The full-panel paired predictive gains against offset-only were smaller than the gains against clock-only.

On the 111 common fixes, the diagonal model increased error by 70 m and 93 m relative to the combined OU model. On all 135 roofs it increased paired held RF RMS by 70.46 Hz and 70.91 Hz and held deviance by 18.386 and 18.385 per point. The diagonal arm returned 41 fixes within 1 km in each calibration arm. Its smaller P90 error describes the distinct set of points it published.

Within the combined OU model, fitting c changed median paired geographic error by −0.58 m across 114 published fixes. Across all 135 roofs, fitted c reduced raw final RF RMS before track offsets by 15.65 Hz at the median. The conditional final RMS changed by −0.019 Hz and conditional held RMS by −0.117 Hz. These are separate calibration outcomes on matched owners, aliases, observations and geometry budgets.

The full batch finished in 294.0 s. The shared four-model roof worker had median wall time 7.196 s, median CPU time 5.017 s and median peak resident memory 140.9 MiB under the 512 MiB cap. The median final stage per model, including both calibration arms, took 0.263 s for combined OU, 0.248 s for combined diagonal, 0.302 s for clock-only, and 0.214 s for offset-only. The separate held stage took 0.788 s at the median for all four models. The rank-one fit update adds a vector operation to the existing whitening. The held scorer directly factors each track covariance to compute its conditional determinant and innovations.

The [full-panel figures](full/figures.json), [paired summary](full/summary.json) and [model evidence lock](full/prediction-lock.json) retain both calibration arms and all original controls.

The full roof manifest includes the four-model overlay and a dedicated chart for each modification against all four original v5 controls on the same 135 recordings. The dedicated chart IDs are `native_clock_offset_ou-full-roof`, `native_clock_offset_diag-full-roof`, `native_clock_only_ou-full-roof` and `native_offset_only_ou-full-roof`. The plots are collected in the [zero-calibration PDF](full/model-figures/c0/modifications.pdf) and the [fitted-calibration PDF](full/model-figures/fitted_c/modifications.pdf). This command regenerates the manifest from the sealed evidence.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.clock_offset_results \
  --figures-only \
  --output reports/2026_11_19_receiver_screening/recovery/clock-offset/full
```

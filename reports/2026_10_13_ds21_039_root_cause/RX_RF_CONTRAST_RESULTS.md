# DS21-039 receiver RF contrast: completed negative control

The extra receiver RF coefficient **does not improve localization**. The selected contrast result is **4.085344 km**, compared with **4.072515 km** for the matched shared-`c` baseline: a **12.829 m regression**. Both miss the user’s 0.5 km target. The training objective improves by 0.656914, which is separate from position accuracy. Do not promote this parameter or call it measured hardware calibration.

This report uses the sealed training receipts and root’s post-seal development evaluation. The independent audit performed no model/predictor/optimizer calls or held scoring. Compact bindings and meaningful values are in [RX_RF_CONTRAST_RESULTS.json](RX_RF_CONTRAST_RESULTS.json); complete states remain in the immutable local receipts.

## Matched comparison and outcome

The [predeclared sensitivity](RX_RF_CONTRAST_PROTOCOL.md) retains the common fitted coefficient `c` and adds one nuisance `d`, with effective receiver coefficients `c+d` and `c−d`. Its column is receiver sign times recorded RF minus the **original** RF center, divided by `1e9`. The fixed contrast box is ±5,000 Hz/GHz, scale 200 Hz/GHz, and no extra Gaussian prior. The original physical priors, group frame, native receive times/evidence, 43-satellite bank, two physical starts and seed-5 25 km disk remain matched. Both conditions fit common `c`; no new zero-`c` arm was run.

Four new calls used 20-second/600-iteration limits, and all four were stationary. The baseline selector includes both sealed stationary source incumbents, as declared before execution; the contrast selector uses its two new stationary outcomes only. The baseline continuation from the refinement state exactly reproduces its incumbent cost, and the declared tie rule retains the source incumbent.

| Selected condition | Training objective | Training likelihood NLL | Position error, km | Selected origin |
|---|---:|---:|---:|---|
| Shared fitted `c` | 32380.954535 | 32225.181022 | 4.072514870 | Sealed refinement incumbent |
| Shared fitted `c` + receiver contrast | 32380.297621 | 32224.519006 | 4.085343838 | New fit from same refinement state |

The selected contrast has common `c=−622.826245` and `d=+17.471440` Hz/GHz, hence RX0 **−605.354805** and RX1 **−640.297685** Hz/GHz. Its contrast bound is inactive. The fitted contrast from the other original-all start is **+53.733542** Hz/GHz and has a much worse objective, preserving the original start dependence rather than establishing a stable hardware coefficient.

| New attempt | Objective | NLL | Contrast d, Hz/GHz | Stationarity |
|---|---:|---:|---:|---:|
| shared-c-original-all | 33172.423429 | 32969.499770 | 0.000000 | 5.357e-4 |
| shared-c-refinement-free | 32380.954535 | 32225.181022 | 0.000000 | 7.042e-5 |
| receiver-contrast-original-all | 33166.815754 | 32964.704183 | 53.733542 | 4.982e-4 |
| receiver-contrast-refinement-free | 32380.297621 | 32224.519006 | 17.471440 | 6.493e-5 |

The fit runner took **14.260 s**; root reported **38.493 s** for the outer preparation-plus-fit invocation. These are different timing scopes. No attempt consumed its 20-second limit.

## Oracle and prior audit

Both zero-contrast start replays exactly reproduce source objective, NLL, original vector/nuisance gradients, satellite responsibilities and clutter probabilities. The original-all contrast log-score is **+0.208454980675555** (NLL derivative **−0.208454980675555**), matching the previously sealed opposing receiver-score audit within `2.3e−16`. At the refinement start it is **+0.075215718846434**. Central finite differences at the predeclared ±0.01 Hz/GHz agree within **2.06e−9**. The extra degree of freedom therefore has real first-order training-score support; that did not produce better localization.

The selected contrast’s prior ledger is:

| Prior term | Cost |
|---|---:|
| Common timing | 0.130046319 |
| Relative timing | 155.248417101 |
| Original group calibration | 0.400151353 |
| Extra receiver RF contrast | **0** |
| Total | **155.778614774** |

Saved-parameter arithmetic independently reproduces common/relative/group penalties for every attempt. Objective equals NLL plus these original priors once; original frame values and centering match across all four fits. Selected signal plus clutter mass closes to **2,798 original windows**. The private receipt retains the complete three-element nuisance vector, identifies `d` explicitly, reports `c±d`, and leaves `group_clock_coefficients=[]`. No old frozen-calibration export or hardware claim is used.

All **329 live scientific sources and their archived bytes**, parent bindings, four launch/termination/attempt receipts, oracle seal and reference-free selector were verified from receipts. Primary seals are:

- Freeze: `sha256:1fdead636f8a85e9add8590c2befecad9fda5951f3ade9f587e462c5141d06c4`
- Training terminal: `sha256:d3fb16670a666434849ef12e3b50d1e5c8d33193384053304e35c624ea93e5ac`
- Source oracle: `sha256:1ae65c9a261dad373c1d7f2b4142a1f5c811279a5e5add8760f3821f4d0c2da6`
- Root post-seal evaluation: `sha256:70ae14f9196faaf21fb96170e6868d01d9c9d88d03032a133878b75df9604c43`

## Interpretation

Opposing receiver RF scores showed a legitimate limitation of pooled stationarity, and the new coefficient absorbs some remaining training residual structure. This small fit gain does not explain the multi-kilometer error or establish an RF-path fault. Geography, timing and latent assignments remain coupled, and previously measured band/view residual slopes did not establish a stable receiver clock error. Root’s reference is the configured station location, not a survey performed in this work.

Keep the original shared-`c` model for this comparison. The 0.5 km target remains unmet; this result supplies no basis for tuning the contrast box, selecting another calibration prior, repeating simple LO relabels, or generalizing a new hardware correction across DS21.

# C053: satellite frequency offsets do not improve this conditional CV pilot

The completed selected-position comparison worsens opposite-fold native NLL by **18.480512 over 1,870 original training windows** when adding satellite frequency offsets. All three eligible fold/position comparisons worsen predictive NLL, including after visibility normalization. Seven of eight fits pass strict fixed-position KKT; one original-model high-profile fit is retained nonstationary and its pair is excluded. No model is promoted and no free-position or reference evaluation was performed.

This is a bounded negative *pilot outcome*, not proof that transmitter offsets are absent or that the expanded model's best attainable solution is worse. Two accepted offset fits have worse training objectives than their feasible zero-offset baseline endpoints, exposing optimization gaps. The one complete pair with a clear training improvement still predicts worse across folds.

[Complete call states, priors, all predictive scores and receipt hashes](model_a_c053_satellite_offset_cv_results.json) bind the frozen driver `34b594516`, original offset core `ddbba146d`, canonical adapter `22e7d0eb7`, upstream actual-data qualification and scientific seal. The [prespecified protocol](MODEL_C_SATELLITE_OFFSET_CV_PROTOCOL.md) remains unchanged.

## Design and source qualification

Two fitting folds use exactly `floor(original_time_s/20)%2`, with **873/997** windows. Each fold fits two fixed training-derived positions (current second-cycle selected full endpoint and that cycle's high-position full-likelihood profile) under two models: original native-clock C, and the same model plus satellite-common frequency offsets. The two positions differ by **0.701704 km** in the existing regional chart. They are chosen by their training roles, never reference proximity.

All eight starts share the current selected endpoint's non-position physical state and original nuisance state. Only prescribed XY changes between roles; the extension's 58 zero-sum catalogue coefficients start at zero. The same 59-candidate bank, native evidence/receive times/branches, shared fitted `c`, original common/relative satellite timing priors, clock/group priors and **original common 50 km disk** are retained. Both fixed points and all fitted positions remain inside that disk; no B-style 25 km helper, new disk center, alias repair or geography projection is substituted.

The extension uses the reviewed native core: orthonormal zero-sum catalogue basis; coefficient prior σ=50 Hz inherited from existing `hard60_satellite_correction.py`; coefficient bounds ±2000 Hz and scale 50 Hz. Its physical corrections are shared across receivers, channels and native-time rows. They are empirical satellite-associated frequency corrections, not identified transmitter clock measurements.

The upstream zero-fit qualification made 123 objective evaluations and verified full/fold zero-tail closure and every nonzero offset derivative (maximum FD error 2.54e−9). The new driver adds **eight** actual-state objective checks: both original/zero-tail models at both fixed positions on both folds. Every new zero-tail objective, physical/nuisance gradient and posterior difference is **exactly zero**. It completed in **11.147 s**, outer wave144 **13.827 s**, with zero fits.

Five driver component tests and Ruff pass. Tests cover actual native likelihood/prior/normalizer closure, common non-XY starts, disjoint folds, deliberate points outside 25 km but inside 50 km, public eight-outcome serialization, failed-call retention, strict saved/independent KKT agreement, exact fixed XY and rejection of a rehashed extra optimizer launch. Existing numerical-core tests cover all physical/clock/group/offset derivatives and exclusion of withheld native measurements.

## Every prescribed fit

Each call uses the original fitter with **20-second / 600-iteration** limits and strict projected KKT ≤0.001. The driver independently reevaluates the endpoint objective/gradient, physical/nuisance bounds and original fixed-position KKT, and requires saved versus independent KKT agreement within 1e−7. Satellite-tail metadata is separated from the generic fitter's group-clock fields by the reviewed `core.fit` adapter.

| Fitting fold | Fixed position | Model | Training objective | Training NLL | Independent KKT | Accepted |
|---|---|---|---:|---:|---:|---|
| 0 | selected | original | 10308.809379 | 10158.895804 | 6.781e−5 | yes |
| 0 | selected | offset | 10296.484459 | 10145.109249 | 2.951e−4 | yes |
| 0 | high-profile | original | 10244.774201 | 10111.869363 | **1.095742** | **no** |
| 0 | high-profile | offset | 10324.977881 | 10164.455235 | 2.028e−4 | yes |
| 1 | selected | original | 11675.821853 | 11510.382637 | 6.664e−5 | yes |
| 1 | selected | offset | 11711.099271 | 11548.200755 | 6.152e−5 | yes |
| 1 | high-profile | original | 11686.858363 | 11529.811594 | 1.255e−4 | yes |
| 1 | high-profile | offset | 11699.094120 | 11535.999765 | 1.233e−4 | yes |

The rejected high-profile/original fold0 call reached the original time deadline; its saved endpoint, objective, independent KKT and prediction remain explicit diagnostic data. It is not retried or replaced. Other calls report 16.16–18.53 seconds; the deadline call reports 20.079 seconds including the original fitter's final endpoint accounting. No scientific limit or stationarity threshold was changed.

Two fold units ran concurrently, each retaining all four attempted calls. Their whole-unit times were **86.224/81.966 s**, inside 180/195/200 seconds internal/TERM/KILL. Outer wave145 finished in **88.136 s**. Both unit terminals and all eight outcomes were globally sealed before the evaluation launch:

`sha256:7939786e2d609ef97696544ab23ff4816a27966332dcbd193761b067404dd00d`

There is no original-fit fallback, best-by-error choice or cross-position pooling.

## Opposite-fold native prediction after the global seal

Each returned endpoint is evaluated once with the full singleton native objective; the resulting per-window densities are partitioned into fitting/opposite folds and bands/receiver/20-second blocks. Physical satellite offsets are explicitly added to native predictions **before** `singleton_window_nll`. Priors remain outside these predictive likelihood sums. The visibility diagnostic uses `raw_NLL + log(integrated_visible_emission_mass)`, from the existing exact native support-mass helper. It conditions on original detector branch evidence and is not a generative model of top-peak selection.

Only pairs with both independent strict fits accepted enter comparisons. Positive deltas mean offset minus original, hence worse prediction.

| Fitting fold / position | Opposite windows | Raw NLL delta | Visibility-normalized delta | Low-band raw delta | High-band raw delta |
|---|---:|---:|---:|---:|---:|
| 0 / selected | 997 | +12.341844 | +12.341844 | +10.971130 | +1.370714 |
| 1 / selected | 873 | +6.138669 | +6.138669 | +16.787067 | −10.648398 |
| 1 / high-profile | 873 | +3.765575 | +3.791570 | −5.628278 | +9.393853 |

The selected-position comparison has both folds complete: **+18.480512 raw and normalized NLL**, approximately **+0.009883 per opposite-fold window**. Its low-band total worsens 27.758197 while high improves 9.277684; the combined result worsens. The high-profile role has only one eligible fold, so a two-fold aggregate is unavailable. The rejected original fold0 prediction is reported in JSON but does not enter a matched claim.

For the selected fold0 pair, offset fitting improves training objective **12.324920** and training NLL **13.786555**, yet opposite-fold NLL worsens **12.341844**. This is the clearest negative predictive result under the prescribed starts. Selected fold1 and high-profile fold1 offset objectives are worse than their original counterparts by **35.277418/12.235757**. The original endpoints are feasible zero-tail points of the extension, so these gaps demonstrate worse local search outcomes despite strict stationarity. They prevent attributing every predictive regression solely to extra model flexibility.

## Separate physical-prior accounting

These are actual fitting-fold endpoint penalties. None is added to the predictive NLL above.

| Fold / position / model | Common timing | Relative timing | RX clock | Group calibration | Satellite offset |
|---|---:|---:|---:|---:|---:|
| 0 / selected / original | .001387 | 143.468960 | 6.042437 | .400791 | 0 |
| 0 / selected / offset | .015741 | 145.564306 | 4.478621 | .401294 | .915249 |
| 0 / high-profile / original, rejected | .010523 | 126.935156 | 5.557661 | .401497 | 0 |
| 0 / high-profile / offset | .014918 | 152.804104 | 6.208852 | .400732 | 1.094040 |
| 1 / selected / original | .000772 | 163.152176 | 1.886767 | .399501 | 0 |
| 1 / selected / offset | .000509 | 158.926824 | 2.574073 | .399365 | .997745 |
| 1 / high-profile / original | .000033 | 153.814913 | 2.832431 | .399392 | 0 |
| 1 / high-profile / offset | .000572 | 158.730673 | 2.694272 | .399474 | 1.269363 |

Full objective minus raw likelihood closes to the sum of these penalties once. The generic fitter's combined group/tail prior is separately preserved and agrees with group plus offset penalties within 4.5e−16. It is not relabelled as receiver-clock cost.

Physical satellite-offset RMS across all 59 catalogue entries is **8.807/9.629/9.195/10.372 Hz** for offset fold0-selected/fold0-high/fold1-selected/fold1-high. Across these four fits the physical offset extrema are −44.712 to +47.670 Hz; coefficient bounds are inactive and the physical offsets sum to zero. Full per-candidate vectors are retained. Relative timing cost rises in three comparisons and falls in selected fold1; there is no uniform transfer of timing penalty into frequency penalty. Lower timing cost alone is not a position correction.

## Scope and outcome

The new scientific budget is exactly **eight optimizer calls**, plus eight driver qualification objectives, eight independent fit-audit objectives, and eight post-seal full objectives/eight explicit native orbit predictions. The fitter's own evaluations are part of its unchanged original calls; recorded feasible evaluations must not be mistaken for a separate 600-objective cap. The post-seal evaluator took **11.401 s**, outer wave146 **14.130 s**. All failures and source receipts remain immutable.

Only original training windows are split. Discovery, bank, branches, clock nodes, initialization and both fixed positions came from full training, so this is **conditional development CV with leakage through fixed inputs**, not untouched validation. Original held/locked data are not scored or used for selection, and no configured position reference is read. Per-band/block results are descriptive and do not establish statistical significance.

This pilot provides no support for promoting the satellite-offset extension or proceeding directly to free geography. It also does not resolve the external LNB authority or prove the fitted timing represents ephemeris error. A separate numerical control would be required to study the two observed optimization gaps; those calls are not silently appended here. The prescribed eight-call experiment is complete with its one explicit unavailable matched fold.

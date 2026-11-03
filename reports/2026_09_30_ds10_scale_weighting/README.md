# RX-derived relative weighting does not improve DS10 held geographic likelihood

**Do not promote the variable weights.** Both pooled DS10 N24 fits qualify, but variable weighting worsens held likelihood relative to the original model and the matched constant-scale control. Reference distance changes only modestly, from 1091.847 m to 1078.224 m, and remains above one kilometre.

| Model | Reference distance | Position shift from baseline | Native held log-score gain | Original-model held gain at new point |
|---|---:|---:|---:|---:|
| Original q020 baseline | 1091.847 m | — | — | — |
| Matched constant scale | 1089.689 m | 5.703 m | +2.958765 | +0.230160 |
| Track-variable scale | 1078.224 m | 22.104 m | −2.815627 | −1.577144 |

Positive score changes favor the new result. Native scores include the correct density normalization and are evaluated under each model. Original-model scores evaluate each new fitted position/timing vector under the unchanged q020 model. The variable arm trails the constant arm by 5.774392 held log units. Reference-distance improvement is not used for selection or promotion.

## Ablation: likelihood change versus position refit

| Arm | Held gain at frozen original position/timings | Additional held gain from refitting | Total held gain |
|---|---:|---:|---:|
| Matched constant | +2.705519 | +0.253247 | +2.958765 |
| Variable | −1.554663 | −1.260963 | −2.815627 |

The variable model already loses held likelihood before geography or timing changes. Joint optimization adds another held loss. Its training score nevertheless improves by 78.899155 log units, illustrating why training fit or reference distance alone would give a misleading promotion decision.

## Frozen weights and matched control

The [protocol](PROTOCOL.md) begins with the complete fixed DS10 N24_h0 panel, not a selected favorable subset. Every original track, mask and candidate remains. Of 1443 tracks, 707 receive a training-only paired-RX scale estimate; the other 736 retain ratio one.

The previous [individual residual calibration](../2026_09_30_rx_scale_common_transfer/README.md) supplies frozen DS7–DS9 coefficients separately for RX0 and RX1. For each supported track, compute the ratio of its predicted scale to the donor constant-scale fit. If a track appears in multiple accepted pairs, use the median log ratio. Freeze this mapping before the location fit. Ratios range from 0.588654 to 1.707141, giving contrast noise scales from 58.865 to 170.714 Hz.

The control applies one median log ratio per receiver to exactly the same supported tracks, preserving unsupported-track fallback. Its log ratios are −0.038298 for RX0 and −0.054234 for RX1. This matches the population and typical scale without track-specific variation. No clipping, reference-informed tuning or held-data weight selection occurs. Both fits start at the same original N24 solution and use the unchanged optimizer and qualification gates.

## Normalized likelihood implementation

The research-local [scaled_model.py](scaled_model.py) divides observations and candidate predictions by each track's frozen ratio. In transformed units, signal noise stays 100 Hz and the background slope-prior scale becomes `2000/ratio`, preserving its physical value. The implementation restores the `(n_training−1) log(ratio)` training contrast Jacobian and `n_held log(ratio)` conditional held Jacobian. Thus model comparisons use normalized densities rather than unnormalized residual weights.

No residual slope is subtracted. This applies a relative scale hypothesis to both signal and background observation noise. It does not identify actual sensor variance, and transfer from scalar residual scales to the multivariate contrast model remains an empirical hypothesis.

## Qualification and verification

Both runs finish without a boundary hit or retry: 24.21 seconds for constant and 25.07 seconds for variable, within their 180-second caps. Maximum gradients are 0.002280 and 0.006498, below 0.01. Gradient-audit discrepancies are 0.00001401 and 0.00001019, below 0.02. Both optimizers report success.

Two component-owned tests pass, covering exact unity equivalence and direct physical-scale density/Jacobian agreement with finite-difference gradient checks. Unity transformation also exactly replays the complete real baseline score, posterior rows and gradients. Source/input hashes, exact membership and supported-track joins verify. [plan.json](plan.json) freezes all ratios and bindings; [constant.json](constant.json), [variable.json](variable.json) and [summary.json](summary.json) preserve results and ablations. The SHA-256 inventory binds all artifacts.

## Consequence

The paired-RX feature remains a useful conditional residual diagnostic, but its successful scalar likelihood calibration does not translate into a supported geographic weighting method in this pilot. Keep the original geographic estimator. Do not expand this exact weighting recipe to more panels solely because its reference distance decreases by 13.623 m here.

The next uncertainty investigation should distinguish pointwise prediction spread from the temporal covariance and residual modes that drive geographic contrasts. Any replacement must first improve held contrast likelihood with geography fixed, before another location refit. This result does not rule out all RX-derived covariance models; it rejects promotion of this frozen track-scale mapping.

This is exposed-data local fitting from one initialization per arm, not research-blind accuracy validation or a global-optimum claim. Reference uncertainty and DS10 installation continuity remain unresolved. No new RF, export, propagation, production change or remote publication occurred.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_30_ds10_scale_weighting -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_30_ds10_scale_weighting/summarize.py
cd reports/2026_09_30_ds10_scale_weighting
sha256sum -c evidence.sha256
```

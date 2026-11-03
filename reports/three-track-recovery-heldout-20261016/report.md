# Three-trajectory recovery with target-excluded calibration

Scan: `fast8-auto-20261016-161535-99008d35-1-lower`  
Run: `fast-9571943d3dccdf4f327e1346d1bf34b8`

The generic candidate search recovers the same satellite identity in all six temporal tests, without a satellite-specific correction rule. Calibration fitting excludes all 129 original target measurements. Across the two disjoint test halves of each target, 128/129 points fall within a diagnostic 375 Hz tolerance; pooled withheld frequency RMS is 135.13 Hz. This is conditional frequency prediction evidence, not a measurement of position accuracy or a production association count.

| Original target | Automatically selected satellite | Early-half training → late-half test | Late-half training → early-half test |
| --- | ---: | ---: | ---: |
| RX1 CH2, 50–75 s; 29 points | 69433 | 137.08 Hz | 90.91 Hz |
| RX1 CH4, 40–100 s; 73 points | 69333 | 132.64 Hz | 143.10 Hz |
| RX1 CH2, 170–190 s; 27 points | 69522 | 130.53 Hz | 159.49 Hz |

The search uses the same timing-only family for every candidate: 1,035 regional satellites, a total timing domain of ±5 s with a 0.05 s grid, 125 Hz frequency scale, and a 2 s timing prior. Identity and timing are selected using training measurements only. The test values do not select the candidate, timing, calibration endpoint, or gate. The candidate IDs above are outputs.

![Temporal transfer compared with the original frozen calibration](01_temporal_transfer.png)

The earlier comparison also fitted satellite identity and timing on one half, but retained the original full-scan calibration. This figure compares conditional temporal-transfer experiments; its gray bars are not the original production point-association RMS. The new calibration endpoint is selected by its training objective, before evaluating the targets.

## What is withheld, and what remains conditional?

The 29 early CH2, 73 CH4, and 27 late CH2 measurements are removed from the shared calibration likelihood, leaving 4,668 training observations. The fit retains its normal regional position, receiver calibration, common clock, satellite timing and detection-probability parameters. Its relative satellite timing prior is 0.5 s. A measurement-invariance check changes every excluded measurement by 1,234,567 Hz and verifies exactly unchanged training objective, physical gradient, and nuisance gradient.

This is not a fully cold, end-to-end independent evaluation. The 59-satellite background bank, frozen high-band contrast, and saved initialization come from the original full-scan pipeline. The target sets were identified by inspection. The per-track candidate search itself tests the full 1,035-satellite regional bank. The saved initialization can affect a nonconvex fit even when target measurements are absent from its objective. Removing these remaining conditioning assumptions requires a separate training-only discovery experiment.

Each target point is evaluated once using parameters learned from its opposite temporal half. The two folds share the same target-excluded calibration; they are not independent experiments.

![Distribution of withheld frequency residuals](02_withheld_residual_histograms.png)

The sole residual outside ±375 Hz is the already identified late CH2 point at 172.513 s, now approximately +406 Hz. No point was forced into an association. The tolerance is a diagnostic frequency threshold, not a posterior probability or validated false-alarm criterion.

## Negative controls

The same search is applied to eight shuffled training-frequency sequences for each of the six folds, preserving each training set's frequency values while breaking their association with time. All six real sequences pass the declared gate: training RMS ≤375 Hz and a penalized candidate-score gap ≥20. None of the 48 shuffled sequences passes. These exploratory controls demonstrate sensitivity to temporal coherence; they do not establish a global false-alarm rate for scanning all possible tracks.

![Shuffled controls and competing late-CH2 residual models](03_controls_and_residual_models.png)

## Does a frequency model replace the empirical timing correction?

Using the training-selected satellite identity, we compared a constant frequency offset, an offset plus linear frequency drift, an exact orbit-time shift, and a one-parameter frequency term proportional to the predicted Doppler time derivative. Only one temporal half estimates each model; the other half tests it. Calibration remains fixed and excludes all targets.

| Late CH2 correction | Parameters | Early → late test | Late → early test | Guided RX2 RMS for the two RX1-trained corrections |
| --- | ---: | ---: | ---: | ---: |
| Constant frequency offset | 1 | 408.74 Hz | 421.14 Hz | 384.82 / 324.22 Hz |
| Offset + linear drift | 2 | 293.56 Hz | 327.31 Hz | 270.58 / 301.31 Hz |
| Doppler-derivative frequency basis | 1 | 148.34 Hz | 176.29 Hz | 226.42 / 275.89 Hz |
| Exact orbit-time shift | 1 | 146.22 Hz | 174.74 Hz | 228.44 / 276.53 Hz |

The derivative model adds `a × dD/dt` to predicted frequency. It does not change observation timestamps or propagate the orbital state at a shifted time. Its fitted amplitudes are −0.933 and −0.963 seconds; seconds are the coefficient's units because the basis has units Hz/s. They are not measured recording-clock errors. Its similarity to the timing model illustrates a local identifiability problem: a timing-shaped frequency discrepancy can be explained almost equally well without changing timing.

This frequency basis is not uniformly sufficient across all targets. For CH4, it yields 319–350 Hz withheld RMS, versus 158–159 Hz for an exact time shift. The simpler linear frequency drift also transfers poorly there. The evidence supports retaining coherent timing initialization for the first two trajectories and testing a constrained satellite/channel frequency basis for the remaining cross-band disagreement.

The 20 RX2 detections are fixed, previously qualified RX1-guided raw-IQ counterparts. They are not newly selected to favor these models and are not added to the 4,797-observation denominator. They still share calibration, position and RX1-guided detection assumptions; this is receiver transfer, not an independent localization experiment.

## Timing and frequency interpretation

The separate frame-timing follow-up identified a CH6 discontinuity between 209.24 and 211.72 s, modeled by an approximately 18.4-sample phase step plus a small rate change. Carrier residuals remain similar before and after it. This reinforces the need to model frame-clock behavior separately from orbital Doppler and carrier biases.

A recent primary study reports channel-dependent carrier biases, frequency ramps, and groups of channels with synchronized corrections from the same Starlink satellite. This supports a channel/beam-specific emission model as a hypothesis for the present disagreement; it does not identify the physical mechanism for 69522. The simple affine frequency model tested here performs worse than the timing-shaped alternatives. See [Saroufim, Hayek and Kassas, *Mind the Beam* (2026)](https://people.engineering.osu.edu/media/document/2026-10-04/kassas_mind_the_beam_starlink_pnt_challenges_and_mitigation_strategies.pdf) and [Qin et al., *Timing Properties of the Starlink Ku-Band Downlink*](https://arxiv.org/html/2501.05302v1).

## Calibration ablation and optimization audit

The controlled `c = 0` versus fitted-`c` calibration fits use the same 4,668 observations, 59-satellite background bank, other priors, original compressed start and 60 s solver / 65 s total / 5,000-objective allowance. Both pass numerical convergence and replay audits.

| Calibration fit | Training NLL | Training associated observations | Interpretation |
| --- | ---: | ---: | --- |
| Fitted `c`, original compressed start | 56,136.96 | 2,156 | Matched first attempt |
| `c = 0`, original compressed start | 55,683.41 | 2,326 | Matched control; exposes a better local basin |
| Fitted `c`, initialized at accepted zero-`c` training endpoint | 55,079.34 | 2,389 | Additional optimization diagnostic; extra search budget |

The last row supplies the fitted-`c` calibration used in the headline recovery test. It is chosen by the training objective, not target performance. Its additional optimization budget prevents treating the final row as a matched-budget model comparison. The better zero-`c` result in the first pair does not establish a superior physical model: it lies inside the fitted-`c` parameter family, and restarting that family improves the training fit. None of these scores establishes position accuracy.

## Remaining work

Implement and qualify a coherent-track factor in the joint association model, rather than only generating and testing per-track hypotheses. Learn satellite/channel frequency terms through a common rule and ensure they preserve upper-band fits. Test discovery and initialization without the full-scan conditioning above. Audit whether frequency terms absorb position or ephemeris error before drawing localization conclusions. Distinguish a transmitted carrier correction from orbit or identity error using the existing corpus; their present predictive equivalence is not a physical identification.

The adjacent JSON files and scripts preserve the observations used, masks, fit audits, search bounds, controls and model predictions. Reproduction scripts refer to the existing deployment, recorded input and `/tmp` diagnostic context; this is an evidence bundle, not a self-contained raw-IQ dataset. No production model was changed or deployed.

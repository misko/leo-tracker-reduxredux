# DSX01: causal orbital covariance and prior-mean corrections

**The independent all-five sub-1 km goal remains open.** Ten declared variants were evaluated with unchanged curved observations and matched zero/fitted RF calibration arms. No per-scan GPS winner is assembled into a method.

The previous [strict linear-transfer controls](../2026_10_18_dsx01_cut_linear/README.md) showed that apparent S05 sub-1 km gains did not survive residual screening. Here all 12,724 original curved observations remain across the five independent scans. Linear fragments do not calibrate the hardware and are not added to these new localization objectives. No observations are held out and no RF was collected.

Each variant searches the 25 × 25 km Mill Valley box centered at 37.906°, −122.545° with 25 grid nodes plus a blind incumbent, three c0-selected starts, 24 bounded iterations per start/arm and three phase-reference rounds. Labels, aliases, measured point-noise scales and remaining priors match within each c pair. Evaluation GPS enters only the reporter and explicitly labeled postfit diagnostics. These are exploratory tests on the same corpus.

Three remedies are tested:

1. **Correlated orbital priors.** Project the previous/latest causal state difference at 0/150/300 seconds onto standardized phase, mean-motion, inclination and RAAN directions. Velocity differences receive a declared 150-second weight. A rank-one correlation uses fractions 0.5 or 0.9 while preserving every marginal variance. The correlation is a sensitivity hypothesis, not an empirically calibrated covariance.
2. **A fuller physical span.** Add both eccentricity-vector directions, using the existing causal scales. Compare independent and correlated six-coordinate priors to the four-coordinate control.
3. **Causal prior means.** Extrapolate the previous/latest state innovation opposite its observed direction by `clip(age/epoch_gap,0,2)`. Compare phase-only and full four-coordinate means, capped at three standardized units. Fixed unshrunk controls are compared with shrinkage selected using earlier, strictly causal TLE transitions and no radio measurements or GPS.

Past-transition selection considers 0/0.25/0.5/0.75/1, using robust normalized along-track phase-proxy loss. It selects 0.25 for S01/S02/S03/S05 and 0 for S04. Future records are removed into a separate past-only input before fitting. A later causal TLE is a consistency proxy, not independent orbit truth.

![Past-only shrinkage selection](history_shrinkage.png)

| Variant | S01 | S02 | S03 | S04 | S05 |
| --- | ---: | ---: | ---: | ---: | ---: |
| diag_4 | 0.527 / 0.512 | 1.044 / 1.041 | 1.571 / 1.629 | 0.426 / 0.428 | 1.887 / 1.869 |
| corr_4_0p5 | 0.531 / 0.519 | 1.004 / 0.998 | 1.546 / 1.606 | 0.342 / 0.335 | 2.015 / 2.000 |
| corr_4_0p9 | 0.932 / 0.932 | 0.954 / 0.946 | 1.543 / 1.607 | 0.182 / 0.178 | 2.405 / 2.394 |
| diag_6 | 0.458 / 0.443 | 1.169 / 1.171 | 1.392 / 1.432 | 0.287 / 0.285 | 2.048 / 2.035 |
| corr_6_0p5 | 0.374 / 0.357 | 1.135 / 1.136 | 1.399 / 1.443 | 0.339 / 0.328 | 2.103 / 2.090 |
| corr_6_0p9 | 0.330 / 0.312 | 1.098 / 1.097 | 1.408 / 1.455 | 0.346 / 0.329 | 2.190 / 2.179 |
| phase_trend | 0.422 / 0.407 | 1.135 / 1.137 | 1.427 / 1.485 | 1.328 / 1.333 | 1.653 / 1.634 |
| full_trend | 1.001 / 0.985 | 1.158 / 1.164 | 1.184 / 1.238 | 0.719 / 0.698 | 2.198 / 2.181 |
| phase_history | 0.497 / 0.482 | 1.065 / 1.063 | 1.534 / 1.593 | 0.426 / 0.428 | 1.828 / 1.810 |
| full_history | 0.631 / 0.616 | 1.040 / 1.038 | 1.424 / 1.482 | 0.426 / 0.428 | 1.985 / 1.968 |

Position errors are km, **c0 / fitted c**. `diag_4` reproduces the previous normal control.

![Independent position comparisons](position_errors.png)

A common c0 normalized-bound selection rule gives DSX01-S01 phase_history (0.482 km fitted c); DSX01-S02 diag_6 (1.171 km fitted c); DSX01-S03 corr_4_0p9 (1.607 km fitted c); DSX01-S04 diag_6 (0.285 km fitted c); DSX01-S05 phase_history (1.810 km fitted c). It also fails the all-scan target. Variational-bound tightness and uncertain identities limit its interpretation as model evidence.

Correlations improve some scans and worsen S05. Full unshrunk trend means bring S03 closer but worsen other scans. The past-only shrinkage rule generally prefers a modest correction; this does not yield uniform sub-1 km localization.

![Cost drivers at true versus blind position](prior_cost_drivers.png)

| Fitted-c variant | Accepted curved points | % curved | Curves | Points/curve | Common-point RMS c0 / fitted c (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: |
| diag_4 | 10,825 | 85.08% | 296 | 36.57 | 130.762 / 130.751 |
| corr_4_0p5 | 10,825 | 85.08% | 296 | 36.57 | 130.721 / 130.712 |
| corr_4_0p9 | 10,726 | 84.30% | 293 | 36.61 | 130.943 / 130.934 |
| diag_6 | 11,083 | 87.10% | 302 | 36.70 | 131.878 / 131.877 |
| corr_6_0p5 | 11,083 | 87.10% | 302 | 36.70 | 130.933 / 130.934 |
| corr_6_0p9 | 10,883 | 85.53% | 297 | 36.64 | 130.968 / 130.963 |
| phase_trend | 10,825 | 85.08% | 296 | 36.57 | 130.747 / 130.735 |
| full_trend | 11,060 | 86.92% | 302 | 36.62 | 130.790 / 130.788 |
| phase_history | 10,825 | 85.08% | 296 | 36.57 | 130.757 / 130.746 |
| full_history | 10,825 | 85.08% | 296 | 36.57 | 130.765 / 130.755 |

Coverage refers to nominated curved fragments, not all raw GLRT points. Original RMS, offset, residual-structure, elevation and curved-owner gates remain in place. Frequency-fit improvements do not establish better position accuracy. Common-point RMS compares the same accepted population in each c pair.

The late S05 63387 diagnosis holds receiver calibration fixed and fits one phase using only its 98 curved points, with identical phase priors and 150 Hz noise in causal/following comparisons. The first following TLE changes phase by roughly 2.65 seconds, but the late RX2 slope errors persist. They are also not a uniform receiver effect: unrelated late curved candidates have different residual slopes. This does not establish a receiver fault, a TLE maneuver or a correct satellite identity.

![Following TLE as a postfit diagnostic only](late_family/63387_phase_transfer.png)

[Detailed late-family diagnosis](late_family/diagnostic.json). No following TLE enters the new fits.

Exact combined SGP4 conditional-mean checks reach **2.548 Hz RMS** across 100 available final endpoints; **0** are unavailable. These check means, not exact nonlinear marginalization or identity.

Tests independently verify unchanged covariance marginals, positive variance floors, latent-coordinate densities against dense Gaussian calculations, state projections, strict history causality and nonzero-mean variational bounds against numerical quadrature. A [historical-TLE orbit study](https://arxiv.org/abs/1002.2277) motivates looking for information in successive element sets; its batch high-precision orbit method does not validate our simple few-TLE trend extrapolator.

[Evaluation CSV](evaluation_summary.csv), [common-point c controls](c_ablation.csv), [gate/cost details](frequency_details.json), [bindings](evaluation_bindings.json).

The next investigation should test identity/fragment integrity and cross-channel coherent residual structure, rather than assume that another independent prior widening will fix all scans.

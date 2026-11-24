# Offline slope test with elapsed-time Bartlett variance

The installed slope statistic uses marginal residual scatter and an independent-noise variance formula. Its lag-one check is a separate rejection criterion. A fixed elapsed-time Bartlett covariance gave poor finite-sample calibration in the targeted synthetic test, so the standalone prototype stays out of the solver. On DS30-0220, the four curves with 139 lost points also failed the separate profile-noise check. Changing the conditional slope test alone would recover zero points from them. [Frozen protocol](offline-slope-hac-protocol.md) · [Sealed synthetic and original-scalar readout](measurements/offline-slope-hac.json.gz).

## What the installed statistic measures

For centered time $x=t-\bar t$, the installed screen uses $|x^Tr|/(\max(s_r,75)\sqrt{x^Tx})$, where $s_r$ is the sample SD of the observed residual. The numerator has variance $x^T\Sigma x$. The installed denominator corresponds to a white covariance scaled by the marginal SD and floored at 75 Hz. The separate $|\widehat\rho_1|\le4/\sqrt n$ requirement uses adjacent residuals after centering only. It receives neither elapsed lag nor a detrended estimate and does not modify the slope denominator. The full gate also checks mean, quadratic evidence and a change-point statistic. [Pinned installed screen](../../../src/leo/analysis/research/polynomial_satellite_diagnostics.py).

On the actual retained-track path the conditional check sees `conditional_residual_hz` with the 450 Hz RMS cap. The profile gate separately sees the innovations from a Gaussian constant-bias profile. Its `whitening(times)` call uses the default diagonal 150 Hz covariance. The library supports correlated whitening in other callers. This call does not select it. Raw lag-one correlation can contain actual residual slope or the effects of fitted nuisance parameters. It is insufficient to identify the covariance of the slope. [Retained checks](../../../src/leo/analysis/localization_v3/conservative_recovery.py) · [Conditional gate](../../../src/leo/analysis/localization_v3/acceptance.py) · [Profile and covariance](../../../src/leo/analysis/research/retained_track_likelihood.py).

## Ground-truth control

The standalone diagnostic keeps the original slope numerator and cutoff. It forms OLS-detrended residual scores $u_i=x_i e_i$, and estimates the numerator variance by $\max(75^2 x^Tx,\frac{n}{n-2}u^TKu)$, where $K_{ij}=\max(0,1-|t_i-t_j|/h)$. The bandwidth $h$ is one more than the prespecified nominal lag times the median positive gap. On regular sampling this gives the usual Bartlett weights at the original integer lags. The elapsed-time kernel gives zero weight to sufficiently separated observations. Its positive semidefiniteness follows by representing each entry as the normalized overlap of two intervals of length $h$. [Standalone implementation](offline_slope_hac.py).

Each table cell pools 16,384 independent residual trials across four lengths and two cadence patterns. The positive and negative alternatives are paired with the same baseline noise and have a known slope magnitude of four times the white-noise numerator SD. A flag in the true direction counts as a detection. The exact covariance oracle uses simulation truth, which is unavailable on the field residuals. Under independent contamination it knows the covariance but the tail distribution is non-Gaussian.

| Synthetic noise | Slope false flags, stock → Bartlett | False flags at known covariance | Detection at negative slope, stock → Bartlett | Detection at positive slope, stock → Bartlett |
| --- | ---: | ---: | ---: | ---: |
| Independent Gaussian | 0.153% → 2.460% | 0.287% | 66.63% → 88.09% | 65.83% → 87.37% |
| Independent contaminated Gaussian | 0.092% → 1.135% | 0.708% | 73.63% → 87.98% | 72.82% → 87.39% |
| AR(1) `ρ = −0.35` per tick | 0.006% → 0.873% | 0.189% | 68.28% → 97.21% | 68.01% → 97.04% |
| AR(1) `ρ = +0.45` per tick | 2.832% → 5.469% | 0.262% | 66.00% → 70.21% | 65.94% → 70.83% |
| AR(1) `ρ = +0.75` per tick | 14.746% → 13.867% | 0.262% | 68.60% → 63.78% | 67.79% → 63.23% |

The larger independent detection rates came with substantially more false flags. At `ρ = +0.45`, the true slope-numerator variance was **1.78–2.48×** the white assumption across the fixed layouts. That supplies a concrete case in which marginal SD and the lag-one admission do not compensate for autocorrelation. Among zero-slope residuals that passed every other original conditional check, stock rejected **1.655%** in this moderate positive-AR condition and Bartlett rejected **4.592%**. For the strong positive-AR condition the corresponding rates were **4.234% and 7.460%**, even though the unconditional slope-only flag count fell. The existing other tests can reject correlated residuals for reasons beyond slope, so these are conditional slope false flags and not false-association probabilities.

## Exact physical evidence and its limit

| DS30-0220 curve size | Original conditional slope z | Stored lag one / limit | Variance ratio needed for the slope cutoff alone | Separate profile noise |
| --- | ---: | ---: | ---: | --- |
| 21 | 3.006 | 0.261 / 0.873 | 1.004× | Failed |
| 28 | 3.605 | 0.374 / 0.756 | 1.444× | Failed |
| 34 | 3.568 | 0.224 / 0.686 | 1.414× | Failed |
| 56 | 3.528 | 0.175 / 0.535 | 1.383× | Failed |

The ratios are the algebraic values $(z_{\rm old}/3)^2$ with the original numerator fixed. They are neither estimated covariances nor a counterfactual score. Every curve passes the conditional lag-one limit and the other conditional scalar checks, but fails profile noise as well. The DS30-0086 donor has one 38-point conditional slope-only record with the same independent profile-noise block. The archived screens bind ordered observation IDs and scalar conditional diagnostics. They provide no original ordered time and residual vectors for either score and no separate profile slope statistic. An earlier physical timing sample used residuals from a quadratic fit to detector CFO and saved only support lengths and timings. It cannot supply the missing exact retained vectors. Zero physical vectors were rescored. The 17 family-closure removals were also outside this slope calculation. [Earlier gate timing assay](exact-noise-gate-0402-protocol.md).

Protocol commit `2fe071f4e`. The receipt reuses the original unchanged screen source at SHA-256 `8bf7d7935b74bba728d437d2652af636e5532be74d798ed4f56c6641be7352c5`. Original stage and gate digests are saved in the receipt. Eight component tests passed. This was an offline simulation and scalar audit, with no position fit, receiver activity or release change.

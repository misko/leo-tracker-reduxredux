# First random-intercept run: numerical acceptance failed

The full-calibration scalar fit completed in 2.91 seconds with fixed coefficients and unchanged candidate/ratio models. It did not pass the predeclared integration check. No original-run LOSO jobs were launched.

| Arm | Selected sigma, logit units | Maximum candidate-track LL difference, order 128 vs 256 |
|---|---:|---:|
| M0 | 4.076231 | 0.245588 |
| Mean direction | 3.308786 | 0.120523 |
| Candidate mixture | 2.560382 | 0.020778 |

The tolerance is 0.001 natural-log units. None of the fitted scales hits the upper bound of eight. All sigma-zero parity checks pass. The apparent training-score gains must not be interpreted as accepted model performance because the quadrature criterion fails.

The next numerical implementation will center and scale quadrature at the conditional log-integrand mode for each candidate. It must retain the exact normal-prior/proposal-density correction, hence remain an integral, not a profiled per-track free offset. Scientific assumptions, scalar bounds, calibration-only selection, frozen coefficients, candidate priors, ratio model, and the 0.001 accuracy threshold do not change. Original code and this failed artifact remain preserved.

Source: `track-random-intercept-full.json`.

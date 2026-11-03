# Conditional marginal uncertainty improves prediction but fails the geographic pilot

The expanded donor-only calibration resolves the previous10Hz lower boundary:
DS9andDS10select15Hz intrinsic Cauchy noise, DS11selects20Hz; fitted signal
probabilities are .93580,.93640,.93067. All optima are interior to the noise grid
0,.25,.5,1,2.5,5,7.5,10,15,20,35,50,75,100,150Hz. Each target dataset is excluded
from calibration, with continuous probability profiling and equal scan weights.
Predictive density improves over calibrated Cauchy on12/12scans, average
0.17135nats/group. This does not translate into consistent geographic gains.

| Three-scan pilot | All-data baseline error (m) | Calibrated Cauchy refit (m) | Conditional marginal refit (m) |
|---|---:|---:|---:|
| DS9-F025 | 2,224 | 2,767 | 2,712 |
| DS10-F028 | 7,734 | 2,310 | 2,858 |
| DS11-F018 | 1,257 | 1,197 | 1,265 |

All3candidate fits and3controls qualify. Only1/3improves over the immediately
preceding calibrated candidate model. Median candidate error is2712.5m, p90
2829.0m, with0/3within1km. The small pilot is not a representative64scan result.
Do not expand or promote this variant on these outcomes.

## Computation and derivatives

For odd Student degrees of freedom, the characteristic function is an
exponential times a finite polynomial. Cauchy convolution changes the
exponential scale; wrapping onto the alias circle permits evaluation through
rational Fourier sums. The density, residual derivative and offset-scale
derivative are computed directly for521/526tracks (511withdf11,10withdf9).
Five tracks withdf10retain adaptive numerical convolution. Zero intrinsic
noise uses the wrapped Student density directly.

Tests compare the direct result against quadrature across residuals, scales
and noise settings, check normalization/periodicity, and verify derivatives
against finite differences. The extended calibration initially stopped on an
even-degree quadrature discrepancy at .25Hz. The v2 uses adaptive32/64/128/256
orders without weakening tolerance; the original stopped runner remains.
Results reproduce the preceding numerical grid to3.83e-13nats/group. The
even-degree refinement check differs by at most3.52e-13relative density.
Expanded calibration takes1.63seconds; this is an offline diagnostic timing,
not an end-to-end localization speed comparison.

The geographic objective retains derivatives of both the training GLS offset
and its conditional scale. The latter depends on the state-dependent contrast
quadratic q, so treating it as fixed would optimize a different objective.
Full-state finite differences at allthree training-only initial states pass,
with maximum refined gradient discrepancy below0.00037. After fitting, allsix
arms pass source/input/height/assignment checks, objective reproduction,
monotonicity and independent scalar finite-difference stationarity checks.

Candidate warm runtimes are7.15,4.09,7.68seconds, with process CPU7.10,4.04,7.57
seconds. These omit acquisition and preprocessing. Original uniform Sacramento
support,100ftMSLheight, shared nuisance priors and fixed identities are preserved.
No new RF, cold64run, independent-recording result or position-uncertainty claim.

## Decision and next diagnostic

Keep the verified fast density and derivative implementation as research code;
reject this geographic variant. Further marginal noise calibration should not
be treated as a reliable route to location accuracy merely because predictive
scores improve. Review existing geometry-observability and reference-diagnostic
artifacts before another model sweep. The next experiment should distinguish
missing geographic information or wrong identity modes from a frequency
likelihood that rewards improved nuisance prediction. Reference coordinates
may be used only for clearly labeled offline diagnostics, never estimator
initialization or association selection.

Evidence: `offset-marginal-calibration-v2.json`,
`offset-marginal-gradient-v1.json`, `offset-marginal-joint-v1-evaluation.json`,
source freezes, raw receipts and SHA256 sidecars. Reference remains the inherited
operator-provided unsurveyed coordinate; all development scans are exposed.

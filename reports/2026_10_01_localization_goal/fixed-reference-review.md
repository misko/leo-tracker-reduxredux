# Fixed-reference nuisance diagnosis

The three development scans still favor their original fitted locations after nuisance parameters are refitted at the operator reference. All six control/reference fits pass source, input, fixed-height, fixed-assignment, objective, decomposition, and finite-difference stationarity checks. This is a reference-informed diagnosis, not a localization improvement or proof of a globally optimal reference fit.

| Scan | Reference minus fitted objective | Observation contribution | Satellite timing-prior contribution | Shared-prior contribution | Top-three positive group fraction |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS9-F025 | 4.232 | 5.840 | -2.203 | 0.596 | 75.4% |
| DS10-F028 | 21.511 | 3.096 | 18.435 | -0.020 | 71.6% |
| DS11-F018 | 1.431 | 1.199 | 0.480 | -0.248 | 80.0% |

Positive values favor the fitted location. Fractions use the sum of positive group contributions, not the net objective gap. Negative contributions offset positive ones. The DS10 timing-prior contribution is 85.7% of its net gap; this arithmetic attribution does not establish a causal or physical orbit-error explanation. NORAD 68729 contributes 15.590, of which 14.081 is its timing prior.

![Group decomposition](fixed-reference-groups-v1.png)

The existing reference-free deletion-influence ranking overlaps the three largest positive reference-gap groups by 3/3, 1/3, and 2/3 respectively. In DS10, influence ranks two and three have negative reference gaps: those groups favor the reference. Consequently, discarding influential groups would also discard potentially helpful evidence. Neither influence nor this retrospective decomposition establishes which identities are correct.

## Method and verification

Keep original baseline hard satellite assignments, all original observations, fixed 30.48 m MSL height, and original Gaussian nuisance priors. Fix east/north either at the saved fitted location or at the operator reference; optimize clock, receiver drifts, and active satellite epochs using the scaled joint solver. Use one inherited nuisance start, 64 iterations, 25 s internal and 30 s external limits, with at most two fitting processes. These are warm diagnostics, not cold acquisition timings.

All 6/6 converge. Wall times are 2.67–3.29 s, process CPU times 2.28–3.09 s. Maximum finite-difference gradient discrepancy is 2.33e-5 and maximum numerical scaled decrement squared is 8.92e-7. Control objectives reproduce the original saved objectives within 1e-6. Per-group observation scores plus epoch penalties, shared penalties, and unused-epoch penalties reconstruct the complete objective. Group identities and track membership match the separately sealed influence diagnostics.

Authoritative artifacts: `fixed-reference-nuisance-v1-audit.json` and its SHA seal, the six receipts and source freeze in `fixed-reference-nuisance-v1/`, and `fixed-reference-groups-v1.json` with its source digests and seal. `summarize_reference_groups.py` generates the comparison and figure. The figure was visually inspected. No production component or golden fixture changed.

## Next experiment and limits

Do not repeat deletion/restoration, shared residual scales, or causal orbit-revision uncertainty as untested ideas: prior experiments already failed to show consistent geographic gains. The earlier Student-t4 satellite timing prior preserved Gaussian variance but changed central curvature from 4 to 10 per second squared. Its mixed results and one convergence failure therefore do not isolate tail robustness.

A bounded next pilot can compare the original Gaussian penalty `2 e^2` against a Student-t4 penalty `2.5 log(1 + e^2 / 1.25)`, including normalization when evaluating density. Both have curvature 4 at zero. The Student scale squared is 5/16 s², variance 5/8 s²; it deliberately does not match the Gaussian variance. This tests weaker tail shrinkage while preserving local shrinkage. Use exact derivatives and the scaled solver, matched original-Gaussian controls, and the three existing development scans. Require solver audits before viewing errors; no per-satellite exemption, GPS-selected deletion, or tuning the scale to these reference gaps. Any gain requires the full development panel, cold 64-scan regression, and held-out validation before promotion.

This hypothesis is informed by exposed development references and must be labeled accordingly. The reference is an unsurveyed operator position; hard identities may be wrong, and only one local nuisance solution was examined. No new accuracy, uncertainty-calibration, or held-out success is claimed.

The frozen 64-scan baseline remains 2,059.9 m median error, 5,850.8 m p90, 64/64 acceptance, and 37.40 s median runtime including acquisition on prepared tracks. The accuracy targets remain unmet.

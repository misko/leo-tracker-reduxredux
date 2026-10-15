# DS22-019: expanded-propensity band ranking and stopping audit

The accepted no-clock original-source release wins because of lower-band likelihood. The accepted coarse-source release improves upper-band likelihood and the prior, but these gains do not offset its lower-band loss. Separately, the two rejected common-clock fixed profiles are limited by residual timing gradients, not propensity gradients. No fit, reference or held-data evaluation was performed in this diagnostic.

## Accepted no-clock release accounting

| Component | Original-source0 | Coarse-source16 | Coarse minus original |
|---|---:|---:|---:|
| Lower-band NLL, 1875 windows | 22990.706102 | 23819.012113 | +828.306010 |
| Upper-band NLL, 1269 windows | 16604.794373 | 16482.977200 | −121.817173 |
| Total NLL, 3144 windows | 39595.500475 | 40301.989312 | +706.488837 |
| Prior, counted once | 416.572516 | 230.132425 | −186.440090 |
| Total objective | 40012.072991 | 40532.121737 | +520.048747 |
| Lower-band effective signal count | 1148.998605 | 1013.451523 | −135.547081 |
| Upper-band effective signal count | 630.510210 | 649.330191 | +18.819981 |

Six independent full/low/high masked density evaluations close both NLL and signal/clutter accounting. Each mask retains the same full calibration/propensity frame and priors; the prior is counted once in the total. These are fixed-state likelihood decompositions, not separately optimized half-position estimates. Labels describe the prespecified training provenance, not reference-based geography categories.

The largest satellite probability is0.09817/0.09604 for original/coarse states; inverse-square effective satellite counts are19.903/22.142 out of67, with entropy3.46265/3.57968. Propensity-prior contributions are39.47812/30.75838. Concentration is a fitted conditional-selection property, not a hardware or physical visibility measurement.

## Rejected common-clock profiles

| Source | Physical timing KKT | Common-clock block | Group block | Propensity block |
|---|---:|---:|---:|---:|
| Original0 | 0.002337809 | 0.000059875 | 0.000560804 | 0.000078358 |
| Coarse12 | 0.007060624 | 0.000058631 | 0.000835649 | 0.000026761 |

Both source fits reported solver success before their 60-second deadline but remain rejected by the unchanged full KKT≤0.001 gate. Eighteen objective evaluations and eighteen explicit native-time orbit/support evaluations examined the largest centrally feasible nongeographic physical and nuisance coordinates at scaled steps1e-5 and1e-6. No probe was clipped, and no visibility event occurred in any tested direction. The original-source common-timing probes crossed31/9 interpolation segments at the two step sizes; the other tested directions crossed none.

For original0, the dominant common-timing derivative is−0.002337809. Central differences are−0.002329398 and−0.002310117; gradient-difference curvature is approximately899273.43 at both steps. The local one-coordinate quadratic decrease is3.039e-12, approximately0.418 objective ULP. The largest group-coordinate decrease is approximately0.142 ULP.

For coarse12, the dominant relative-timing derivative is0.007060624. Central differences are0.007064591 and0.007068593; curvature is approximately305102.28 at both steps. The local coordinate decrease is8.170e-11, approximately11.228 ULP. The group-coordinate decrease is approximately0.455 ULP.

These calculations support investigating numerical stopping on the existing timing/calibration coordinates. They do not establish a coupled Newton decrease, a minimum, or successful stationarity repair, and they do not relax acceptance. A separate bounded matched repair would be a new experiment with additional cost. No failed profile was retried here. The absence of visibility events in these sampled directions is not a global smoothness certificate.

## Authority

- Source: `dd0b0d136`; nine component/roundoff tests and Ruff passed.
- Frozen namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-propensity-diagnostics-v1`.
- Band unit:6 objectives,0 explicit additional orbits,0 fits,45.952 seconds; report SHA256 `72982c8338c050963a8e3afc9bd1cfe263907e84df9ee67986bdf0a092def413`.
- Stopping unit:18 objectives,18 explicit additional native orbit checks,0 fits,46.678 seconds; report SHA256 `cff0eeeeccf2ec9fe9a3ac6a5930cf38a56da20b44fc5fd215ae246bd9e6c40f`.
- Objective evaluations themselves include their ordinary native prediction calls. Explicit orbit counts are additional support checks.
- All original endpoints, eligibility decisions and selectors remain unchanged. No reference, held or locked data were accessed.

# DS22 C satellite propensity: matched profile/release results

The shared satellite-propensity prototype did not resolve either worst C case. DS22-019 produced accepted conditional and propensity estimates at nearly the same distant geography. DS22-075 produced no accepted propensity profile, so that arm is unavailable; this is an optimization outcome, not evidence about its best achievable geography. The original cohort remains unchanged.

Both cases sealed before the configured-reference comparison. Station continuity for DS22 is unconfirmed; all distances below are configured comparisons, not verified accuracy. The prototype models fit all channels. Historical halves share full-channel discovery/initialization and use the original raw C likelihood; they are context, not matched half versions of the new propensity model.

| Case | Historical raw full | Historical raw low | Historical raw high | Conditional full | Propensity full |
|---|---:|---:|---:|---:|---:|
| 019 | 142.114 | 203.397 | 214.751 | 142.114 | 141.641 |
| 075 | 77.587 | 23.428 | 51.146 | 77.587 | unavailable |

Distances are km. Within each arm, the selector used accepted free-release training objective only. Both 019 arms and 075 conditional selected the all-origin branch. Raw historical endpoints were excluded from the new selectors; no reference-selected candidate or fallback was introduced.

## Qualification and actual cost

Source `0fda79ae2` froze the protocol, driver and component tests. Fifteen tests passed (five driver and ten wrapper), with Ruff clean. Actual qualification used 81 objectives on 019 and 95 on 075, taking 33.188 and 33.645 seconds. All fixed/free seed initializer adjustments were exactly zero. Original wrapper objective/gradients/posterior and zero-tail nesting passed; maximum nonzero-tail finite-difference discrepancies were 1.28e-7 and 1.44e-7. No common receiver clock was added.

The experiment made 20 new optimizer calls: 12 fixed profiles and eight releases. Every original 25 km disk was retained. Fifteen calls met unchanged strict stationarity. There were no retries or releases from rejected profiles. Fits used 20 seconds and 600 iterations, followed by independent replay/domain/KKT auditing; the latter is outside the optimizer time cap. Each case/arm/stage remained within its 180-second internal unit bound.

| Case / arm | Accepted profiles | Accepted releases | Selected training objective | Selected NLL |
|---|---:|---:|---:|---:|
| 019 conditional | 3/3 | 3/3 | 41673.350596 | 41281.479093 |
| 019 propensity | 3/3 | 3/3 | 39974.046627 | 39571.937781 |
| 075 conditional | 2/3 | 1/2 | 39156.371971 | 38900.022418 |
| 075 propensity | 0/3 | 0/0 | unavailable | unavailable |

These total objectives have different propensity priors and are not used to rank models across arms.

## Selected 019 likelihood and concentration

A separate frozen zero-fit audit replayed the two selected 019 states. Both bands improve their training likelihood at the propensity endpoint, but the states also differ in geography and calibration; this is an endpoint comparison, not an isolated causal decomposition.

| Quantity | Conditional endpoint | Propensity endpoint |
|---|---:|---:|
| Low-band NLL, 1875 windows | 24053.040948 | 22979.805872 |
| High-band NLL, 1269 windows | 17228.438145 | 16592.131910 |
| Total prior penalty | 391.871502 | 402.108846 |
| Effective satellites, 1/sum(p²) | 36.000 | 12.585 |
| Largest satellite probability | 0.027778 | 0.125465 |
| Top-five satellite probability mass | 0.138889 | 0.561356 |
| Active propensity-coordinate bounds | 0 | 6 |

Despite substantial training-likelihood gains, the geography remains about 142 km from the configured station. This result does not establish that increasing mixture flexibility fixes discovery/domain or assignment errors.

## Preserved 075 optimization failures

| Call | Initial objective | Returned objective | Optimizer seconds | Evaluations | Saved scaled KKT |
|---|---:|---:|---:|---:|---:|
| Conditional low profile | 50804.786169 | 43960.752852 | 20.063 | 458 | 832.093871 |
| Propensity all profile | 39156.371971 | 37061.025581 | 20.065 | 458 | 0.020513 |
| Propensity low profile | 50804.786169 | 45362.615558 | 20.082 | 478 | 5011.250569 |
| Propensity high profile | 50584.840900 | 42761.719493 | 20.092 | 537 | 28.992932 |
| Conditional high release | 44369.714961 | 44368.784824 | 9.741 | 22 | 0.002138 |

The four rejected profiles reached their 20-second optimizer budgets. Their exact initial/end objective and projected-gradient blocks were replayed without fitting. At the closest-to-stationary propensity all-origin endpoint, the maximum projected components were original group nuisance 0.020513, satellite timing 0.007780, propensity 0.000320 and receiver calibration 0.000466. Five propensity bounds were active. Thus its remaining strict-stationarity failure is dominated by the original nuisance/timing coordinates, not by the added propensity gradient alone. The low/high propensity profiles retain much larger timing/group residuals (5011/1977 and 28.979/28.993 respectively). Conditional low also remains far from stationary, with timing 832 and group nuisance 665. No continuation or threshold relaxation was performed.

## Provenance

Pair evaluator `ec25b18be` recursively validated unit seals before reference access; three evaluator tests passed. Comparison: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-propensity-profile-comparison-v1`, protocol SHA256 `bb55b5496da9ed2b860cfbc746563a18e44459f74e89bfc53a5e6867678c330c`.

The zero-fit audit source `175a17740` passed two component tests including active-bound projection and real wrapper band accounting. It used two objectives on 019 and nine on 075, taking 30.636 and 30.231 seconds, with zero fits/reference/held reads. Reports in `ds22-c-propensity-diagnostic-v1` have SHA256 `89c7d52db8e74d0818ba0411596a4434eaf0cac9f9b7149ec59f2482a0f39dc5` (019) and `ff4e1f9a5acbdb42c814c29093035e2d8450b84ce53891a14d931c274b87cb94` (075).

All experiments are extra-budget development controls. No sub-kilometer result, median target, new-model half comparison or cohort promotion follows.

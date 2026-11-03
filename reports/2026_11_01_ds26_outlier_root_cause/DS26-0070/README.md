# DS26-0070 evidence gallery

Published error: **6.716 km** fitted c; **7.269 km** c=0. Main influence family: **62320**. See the [cross-scan conclusions](../README.md).

## Position and satellite-family influence

![Loss and influence](loss_and_influence.png)

![Family ablations](ablations.png)

| Trial | c=0 error km | Fitted-c error km | Both phase closed | Both optimizer successful | Remaining base gates |
|---|---:|---:|---|---|---|
| continue | 7.627 | 6.453 | False | True | True |
| regional_center | 7.620 | 6.474 | False | True | True |
| phase_sigma_x2 | 11.331 | 10.819 | False | True | False |
| omit_62320 | 1.106 | 1.060 | False | True | True |
| omit_63321 | 12.802 | 12.346 | False | True | False |
| omit_58041 | 15.896 | 15.392 | False | True | False |
| omit_63679 | 5.148 | 4.833 | True | True | True |
| extended_omit_62320 | 1.133 | 1.060 | True | True | True |

Gate results here cover retained curved/predictive base terms. Omissions remove evidence; their raw objective is not comparable to the full-data objective. New-family mixture quadrature and complete published-ownership requalification were not rerun for omissions. These are influence experiments, not automatic deletion recommendations.

## Same-observation identity replacements

| Replacement | c=0 / fitted-c error km | Fitted-c objective | Failed gate inequalities c=0 / fitted c | Both phase closed | Both optimizer successful |
|---|---:|---:|---:|---|---|
| 62320 → 63571 | 4.956 / 4.940 | 22052.17 | 6 / 4 | False | True |
| 62320 → 67047 | 3.482 / 3.299 | 22046.19 | 2 / 2 | True | True |

No ownership was changed in production. These experiments retain the fitted observation mask; they do not claim that every previously postfit-only extension remains accepted. Exact checks cover the replacement family plus all base gate inequalities; full promotion still requires independent identity validation and a complete ownership replay. Candidate sets were selected by causal RF scores, not error at the evaluation site.

## Nuisance and receiver transfer

![Nuisance coefficients](nuisance_pulls.png)

![Family transfer](family_transfer.png)

The transfer shortlist was nominated using an inspected full track. Whole-track train/held diagnostics are conditional on that selection, and alias branches use each whole curve. They are not independent prospective validation. Separate constant/affine minima are diagnostic shape bounds.

## GLRT context

![RX1 context](context_RX1.png)

![RX2 context](context_RX2.png)

![GLRT score](glrt_score.png)

Blue/green/yellow colors and NORAD annotations identify owned satellite points; red dots/lines are unassociated graph evidence; orange crosses are untracked evidence. Lines connect native graph samples. The exported score is fractional GLRT winner margin, not the unavailable raw detector statistic.

## Target-by-target debug skill results

| Target | Role | Original NORAD | Points | Span s | Polynomial degree / RMS Hz | Graph parent pieces |
|---|---|---:|---:|---:|---:|---:|
| 0 | influential_associated | 62320 | 91 | 70.2 | 4 / 94.1 | 1 |
| 1 | influential_associated | 63321 | 51 | 46.4 | 3 / 21.3 | 1 |
| 2 | longest_unassociated | None | 65 | 44.7 | 4 / 99.8 | 1 |

### Target 0: SCAN-RX1-CH6-T000-RF12190312500.000000

![Orbit and residual](target-0-orbit.png)

![Candidate-model comparison](target-0-models.png)

![Polynomial audit](target-0-polynomial.png)

![Twenty-second native views](target-0-20s.png)

### Target 1: SCAN-RX2-CH7-T000-RF12440312500.000000

![Orbit and residual](target-1-orbit.png)

![Candidate-model comparison](target-1-models.png)

![Polynomial audit](target-1-polynomial.png)

![Twenty-second native views](target-1-20s.png)

### Target 2: SCAN-RX1-CH6-T003-RF12190312500.000000

![Orbit and residual](target-2-orbit.png)

![Candidate-model comparison](target-2-models.png)

![Polynomial audit](target-2-polynomial.png)

![Twenty-second native views](target-2-20s.png)

Polynomial BIC assumes independent noise and is descriptive here. Mean/slope removal is automatic for fitted polynomials; acceptance is not inferred from zero fitted mean alone. The target-orbit screen freezes hardware and uses per-source corrections; its failed gate is distinct from a failure of the full production model, which also includes orbital modes.

## Paired TLE swap

| Target / NORAD | Causal RMS Hz | Later TLE, corrections frozen | Later TLE, corrections refitted |
|---|---:|---:|---:|
| 0 / 62320 | 496.3 | 10424.7 | 519.0 |
| 1 / 63321 | 24.4 | 18773.5 | 36.0 |
| 2 / 58065 | 123.9 | 1706.4 | 122.7 |

The frozen swap preserves the causal phase, alias, offset and rate; large changes mostly expose that phase corrections cannot be carried unchanged between element epochs. The refitted comparison is the fairer shape diagnostic, still at the same inferred position. First-post elements are selected by time within a fixed 48-hour horizon, never by best residual. Missing later candidates are not replaced by causal elements.

Machine-readable results: [family ablation plan](fit-plan.json), [exact replay and loss](audit.json), [all gate outcomes](gate_validation.json), [candidate summaries](association_summary.csv), [full candidate predictions](targets.json), [family-transfer fits](family_diagnostic.json), [TLE inventory](tle_inventory.csv), [frozen/refitted TLE swap](frozen_tle_swap.json).

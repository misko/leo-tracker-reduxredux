# DS26-0203 evidence gallery

Published error: **6.858 km** fitted c; **6.681 km** c=0. Main influence family: **67935**. See the [cross-scan conclusions](../README.md).

## Position and satellite-family influence

![Loss and influence](loss_and_influence.png)

![Family ablations](ablations.png)

| Trial | c=0 error km | Fitted-c error km | Both phase closed | Both optimizer successful | Remaining base gates |
|---|---:|---:|---|---|---|
| continue | 6.742 | 6.911 | True | True | True |
| regional_center | 6.724 | 6.911 | True | True | True |
| phase_sigma_x2 | 6.315 | 6.484 | True | True | True |
| omit_67935 | 4.411 | 4.453 | False | True | False |
| omit_63377 | 6.415 | 6.584 | False | True | True |
| omit_68256 | 7.796 | 8.032 | True | True | True |
| omit_59360 | 6.647 | 6.724 | True | True | True |
| extended_omit_67935 | 4.422 | 4.453 | True | True | False |

Gate results here cover retained curved/predictive base terms. Omissions remove evidence; their raw objective is not comparable to the full-data objective. New-family mixture quadrature and complete published-ownership requalification were not rerun for omissions. These are influence experiments, not automatic deletion recommendations.

## Same-observation identity replacements

| Replacement | c=0 / fitted-c error km | Fitted-c objective | Failed gate inequalities c=0 / fitted c | Both phase closed | Both optimizer successful |
|---|---:|---:|---:|---|---|
| 67935 → 59360 | 4.419 / 4.453 | 24645.36 | 39 / 39 | True | True |

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
| 0 | influential_associated | 67935 | 68 | 51.4 | 4 / 39.1 | 1 |
| 1 | influential_associated | 63377 | 57 | 51.0 | 4 / 31.3 | 1 |
| 2 | longest_unassociated | None | 71 | 50.3 | 4 / 19.6 | 1 |

### Target 0: SCAN-RX2-CH8-T000-RF12690312500.000000

![Orbit and residual](target-0-orbit.png)

![Candidate-model comparison](target-0-models.png)

![Polynomial audit](target-0-polynomial.png)

![Twenty-second native views](target-0-20s.png)

### Target 1: SCAN-RX2-CH2-T001-RF11190312500.000000

![Orbit and residual](target-1-orbit.png)

![Candidate-model comparison](target-1-models.png)

![Polynomial audit](target-1-polynomial.png)

![Twenty-second native views](target-1-20s.png)

### Target 2: SCAN-RX2-CH1-T002-RF10940312500.000000

![Orbit and residual](target-2-orbit.png)

![Candidate-model comparison](target-2-models.png)

![Polynomial audit](target-2-polynomial.png)

![Twenty-second native views](target-2-20s.png)

Polynomial BIC assumes independent noise and is descriptive here. Mean/slope removal is automatic for fitted polynomials; acceptance is not inferred from zero fitted mean alone. The target-orbit screen freezes hardware and uses per-source corrections; its failed gate is distinct from a failure of the full production model, which also includes orbital modes.

## Paired TLE swap

| Target / NORAD | Causal RMS Hz | Later TLE, corrections frozen | Later TLE, corrections refitted |
|---|---:|---:|---:|
| 0 / 67935 | 41.0 | 26021.7 | 150.9 |
| 1 / 63377 | 72.2 | 7095.5 | 103.3 |
| 2 / 64133 | 50.7 | 834.1 | 42.0 |

The frozen swap preserves the causal phase, alias, offset and rate; large changes mostly expose that phase corrections cannot be carried unchanged between element epochs. The refitted comparison is the fairer shape diagnostic, still at the same inferred position. First-post elements are selected by time within a fixed 48-hour horizon, never by best residual. Missing later candidates are not replaced by causal elements.

Machine-readable results: [family ablation plan](fit-plan.json), [exact replay and loss](audit.json), [all gate outcomes](gate_validation.json), [candidate summaries](association_summary.csv), [full candidate predictions](targets.json), [family-transfer fits](family_diagnostic.json), [TLE inventory](tle_inventory.csv), [frozen/refitted TLE swap](frozen_tle_swap.json).

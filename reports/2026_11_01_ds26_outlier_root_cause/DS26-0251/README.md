# DS26-0251 evidence gallery

Published error: **6.561 km** fitted c; **6.507 km** c=0. Main influence family: **56548**. See the [cross-scan conclusions](../README.md).

## Position and satellite-family influence

![Loss and influence](loss_and_influence.png)

![Family ablations](ablations.png)

| Trial | c=0 error km | Fitted-c error km | Both phase closed | Both optimizer successful | Remaining base gates |
|---|---:|---:|---|---|---|
| continue | 6.503 | 6.555 | True | True | True |
| regional_center | 6.503 | 6.555 | True | True | True |
| phase_sigma_x2 | 6.540 | 6.599 | True | True | True |
| omit_58729 | 6.761 | 6.842 | True | True | True |
| omit_56548 | 0.317 | 0.360 | True | True | True |
| omit_57407 | 6.528 | 6.588 | True | True | True |
| omit_67106 | 6.545 | 6.602 | True | True | True |
| omit_67352 | 6.702 | 6.795 | True | True | False |

Gate results here cover retained curved/predictive base terms. Omissions remove evidence; their raw objective is not comparable to the full-data objective. New-family mixture quadrature and complete published-ownership requalification were not rerun for omissions. These are influence experiments, not automatic deletion recommendations.

## Same-observation identity replacements

| Replacement | c=0 / fitted-c error km | Fitted-c objective | Failed gate inequalities c=0 / fitted c | Both phase closed | Both optimizer successful |
|---|---:|---:|---:|---|---|
| 56548 → 58787 | 1.956 / 1.948 | 29012.03 | 0 / 0 | True | True |

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
| 0 | influential_associated | 58729 | 58 | 41.8 | 3 / 90.3 | 1 |
| 1 | influential_associated | 56548 | 52 | 44.0 | 3 / 56.1 | 1 |
| 2 | longest_unassociated | None | 102 | 72.7 | 4 / 159.3 | 1 |

### Target 0: SCAN-RX1-CH5-T000-RF11940312500.000000

![Orbit and residual](target-0-orbit.png)

![Candidate-model comparison](target-0-models.png)

![Polynomial audit](target-0-polynomial.png)

![Twenty-second native views](target-0-20s.png)

### Target 1: SCAN-RX2-CH8-T001-RF12690312500.000000

![Orbit and residual](target-1-orbit.png)

![Candidate-model comparison](target-1-models.png)

![Polynomial audit](target-1-polynomial.png)

![Twenty-second native views](target-1-20s.png)

### Target 2: SCAN-RX1-CH4-T000-RF11690312500.000000

![Orbit and residual](target-2-orbit.png)

![Candidate-model comparison](target-2-models.png)

![Polynomial audit](target-2-polynomial.png)

![Twenty-second native views](target-2-20s.png)

Polynomial BIC assumes independent noise and is descriptive here. Mean/slope removal is automatic for fitted polynomials; acceptance is not inferred from zero fitted mean alone. The target-orbit screen freezes hardware and uses per-source corrections; its failed gate is distinct from a failure of the full production model, which also includes orbital modes.

## Paired TLE swap

| Target / NORAD | Causal RMS Hz | Later TLE, corrections frozen | Later TLE, corrections refitted |
|---|---:|---:|---:|
| 0 / 58729 | 137.7 | 55595.1 | 122.7 |
| 1 / 56548 | 184.3 | 6034.6 | 242.1 |
| 2 / 65894 | 230.5 | 2043.1 | 219.2 |

The frozen swap preserves the causal phase, alias, offset and rate; large changes mostly expose that phase corrections cannot be carried unchanged between element epochs. The refitted comparison is the fairer shape diagnostic, still at the same inferred position. First-post elements are selected by time within a fixed 48-hour horizon, never by best residual. Missing later candidates are not replaced by causal elements.

Machine-readable results: [family ablation plan](fit-plan.json), [exact replay and loss](audit.json), [all gate outcomes](gate_validation.json), [candidate summaries](association_summary.csv), [full candidate predictions](targets.json), [family-transfer fits](family_diagnostic.json), [TLE inventory](tle_inventory.csv), [frozen/refitted TLE swap](frozen_tle_swap.json).

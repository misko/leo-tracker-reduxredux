# DS26-0034 evidence gallery

Published error: **4.498 km** fitted c; **4.558 km** c=0. Main influence family: **53852**. See the [cross-scan conclusions](../README.md).

## Position and satellite-family influence

![Loss and influence](loss_and_influence.png)

![Family ablations](ablations.png)

| Trial | c=0 error km | Fitted-c error km | Both phase closed | Both optimizer successful | Remaining base gates |
|---|---:|---:|---|---|---|
| continue | 4.558 | 4.498 | True | False | True |
| regional_center | 4.558 | 4.499 | True | True | True |
| phase_sigma_x2 | 4.616 | 4.555 | True | False | True |
| omit_53852 | 1.328 | 1.138 | True | True | True |
| omit_68681 | 3.556 | 3.454 | True | True | True |
| omit_65604 | 4.030 | 3.993 | True | True | True |
| omit_62994 | 4.854 | 4.785 | True | True | True |
| omit_67632 | 4.896 | 4.860 | True | True | True |

Gate results here cover retained curved/predictive base terms. Omissions remove evidence; their raw objective is not comparable to the full-data objective. New-family mixture quadrature and complete published-ownership requalification were not rerun for omissions. These are influence experiments, not automatic deletion recommendations.

## Same-observation identity replacements

| Replacement | c=0 / fitted-c error km | Fitted-c objective | Failed gate inequalities c=0 / fitted c | Both phase closed | Both optimizer successful |
|---|---:|---:|---:|---|---|
| 53852 → 59188 | 0.829 / 0.872 | 25891.95 | 4 / 4 | True | False |

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
| 0 | influential_associated | 53852 | 42 | 28.7 | 4 / 60.3 | 1 |
| 1 | influential_associated | 68681 | 86 | 58.5 | 4 / 52.6 | 1 |
| 2 | longest_unassociated | None | 52 | 47.8 | 4 / 25.2 | 1 |

### Target 0: SCAN-RX1-CH2-T002-RF11190312500.000000

![Orbit and residual](target-0-orbit.png)

![Candidate-model comparison](target-0-models.png)

![Polynomial audit](target-0-polynomial.png)

![Twenty-second native views](target-0-20s.png)

### Target 1: SCAN-RX2-CH4-T000-RF11690312500.000000

![Orbit and residual](target-1-orbit.png)

![Candidate-model comparison](target-1-models.png)

![Polynomial audit](target-1-polynomial.png)

![Twenty-second native views](target-1-20s.png)

### Target 2: SCAN-RX2-CH8-T001-RF12690312500.000000

![Orbit and residual](target-2-orbit.png)

![Candidate-model comparison](target-2-models.png)

![Polynomial audit](target-2-polynomial.png)

![Twenty-second native views](target-2-20s.png)

Polynomial BIC assumes independent noise and is descriptive here. Mean/slope removal is automatic for fitted polynomials; acceptance is not inferred from zero fitted mean alone. The target-orbit screen freezes hardware and uses per-source corrections; its failed gate is distinct from a failure of the full production model, which also includes orbital modes.

## Paired TLE swap

| Target / NORAD | Causal RMS Hz | Later TLE, corrections frozen | Later TLE, corrections refitted |
|---|---:|---:|---:|
| 0 / 53852 | 75.4 | 1295.0 | 76.1 |
| 1 / 68681 | 57.4 | 10008.8 | 55.2 |
| 2 / 57641 | 162.0 | 82730.6 | 229.3 |

The frozen swap preserves the causal phase, alias, offset and rate; large changes mostly expose that phase corrections cannot be carried unchanged between element epochs. The refitted comparison is the fairer shape diagnostic, still at the same inferred position. First-post elements are selected by time within a fixed 48-hour horizon, never by best residual. Missing later candidates are not replaced by causal elements.

Machine-readable results: [family ablation plan](fit-plan.json), [exact replay and loss](audit.json), [all gate outcomes](gate_validation.json), [candidate summaries](association_summary.csv), [full candidate predictions](targets.json), [family-transfer fits](family_diagnostic.json), [TLE inventory](tle_inventory.csv), [frozen/refitted TLE swap](frozen_tle_swap.json).

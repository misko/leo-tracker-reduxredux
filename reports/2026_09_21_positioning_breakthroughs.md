# What improved positioning, and what has actually been ablated

The largest demonstrated gain came from jointly estimating receiver position
and constrained satellite orbital phase-rate errors. Treating a causal TLE as
exact lets its prediction error bias the fitted receiver location. A correction
shared across observations of the same satellite gives the model another,
physically motivated way to explain that error.

## The matched orbital-error experiment

| Fixed-UTC model | Horizontal error | Randomized held-out RMS |
|---|---:|---:|
| Original strict-causal fit | 4,859 m | 157.09 Hz |
| Frozen correction from pre-capture catalogue history | 3,787 m | 155.04 Hz |
| RF refinement for repeatedly observed satellites | 2,443 m | 122.08 Hz |
| RF refinement for all retained satellites | approximately 275 m | 78.63 Hz |

This is the strongest existing component comparison. The all-satellite variant
has 446 satellite correction parameters, two position parameters, and profiled
frequency offsets. It is constrained by a prior learned before the target
captures; it does not access later orbital elements or receiver truth while
fitting. Identities are fixed from the archived RF analysis.

See the [original matched comparison](2026_09_21_uncertain_position_comparison.md)
for source experiments and sensitivity results. These are archived single-site
measurements, not a general accuracy guarantee.

## What the formal model added

The subsequent formal model reached **328.4 m**, with **86.59 Hz** randomized
held-out RMS. It uses a normalized Student-t likelihood, within-track noise
correlation, an inferred measurement scale, and one constrained rate per NORAD.
Three independent external initial positions reach the full-data solution. A
truth-blind optimizer restart repairs a demonstrated noise-bound trap.

The numerical orbit approximation was checked against exact propagation:
0.0072 Hz RMS and 0.1043 Hz maximum discrepancy over 21,702 observations.
This is numerical verification, not an accuracy ablation.

The 328 m result is not an improvement over the exploratory 275 m point estimate.
Its contribution is a more explicit model and reproducible measurement of
convergence, data-size sensitivity, and uncertainty limitations. The earlier
comparison bundled several statistical changes; it did not establish their
individual contributions.

## Other evidence, including negative results

* Identity uncertainty alone did not improve location: fixed-UTC error changed
  from 4,859 to 4,867 m. A later, separate joint identity/orbit prototype improved
  held-out residual RMS but slightly worsened location; it also failed its
  numerical approximation qualification. Neither is evidence that identity
  mixing caused the 328 m result.
* Equal candidate-pass weighting produced a modest 4,503 to 4,289 m change in a
  separate bounded-clock comparison. Those numbers cannot be substituted for
  the fixed-UTC baseline above.
* Keeping half or a quarter of fitting observations gave median converged
  errors of 373 and 399 m, but only 13/20 and 11/20 runs converged. Keeping a
  quarter of whole tracks gave 896 m median error, with 20/20 converged.
* Simulated unmodelled drift reduced nominal 95% coverage to 82/100 trials.
  The real-data formal uncertainty ellipse also missed truth. Precision is
  overconfident even when the point estimate is promising.

The [formal benchmark](2026_09_21_formal_position_benchmark.md) links the complete
results. The [new factorial and sparse-data report](2026_09_21_position_ablation_report.md)
extends this evidence through 1/32 of fitting data and explicitly isolates four
model factors, including their interactions.

## What these experiments cannot establish

All results use the same known site, 37.84903264307456 N,
122.4856541910174 W, for evaluation after inference. Reduced fits inherit the
full archive's identities: they measure conditional positioning, not blind
satellite identification from the reduced samples. Overlapping seeded subsets
are sensitivity experiments, not independent receiver deployments. The model
still needs independent-site evaluation and calibrated uncertainty.

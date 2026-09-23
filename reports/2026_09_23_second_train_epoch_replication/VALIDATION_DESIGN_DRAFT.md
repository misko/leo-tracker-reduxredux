# Proposed validation design — not frozen, no validation evidence opened

## Questions and model set

The goal is real position error below 300 m over long durations with useful
short/medium generalization. A frequency residual improvement alone is not
success. First finish replication on the second TRAIN group. Then freeze exact
sources, candidate generation, hyperparameters, failure handling and aggregation
before opening either validation group. Do not modify the frozen 151/124/64 split.

Retain these complete estimator families for comparison:

1. Original zero-epoch blind search, as the reference baseline.
2. One global epoch nuisance, as the low-complexity timing model.
3. One epoch nuisance per scan, to represent changes across captures.
4. Alternating catalogue reassignment and per-scan epoch fitting, to test whether
   initial identity errors limit the timing models.

Proposed scale grid remains 0.2/1/5 s. These are regularization parameters,
not timing uncertainties. All other search and solver parameters remain fixed.
Do not introduce per-satellite timing freedom merely because it lowers RMS:
existing curvature controls show strong position confounding. Keep it a
development diagnostic until independent evidence warrants adding it.

## Unit of evaluation

Evaluate the two entire validation groups separately at nested 1/6/16/all scan
views, from both Sacramento 250 km and Reno 500 km. These views and starts are
correlated; there are two validation groups, not sixteen independent trials.
Within each view, preserve original randomized training/complementary masks.
No chronological per-track holdout. Use no true position for association,
candidate visibility, fitting, restart selection or optimization stopping.

Publish every arm, including failure, active bounds, visibility problems and
solver stopping status. Retain the same eligible track support across models.
Report absolute position error, held capped and uncapped frequency RMS,
assignment changes, runtime, and failures. Do not call solver curvature a
calibrated geographic confidence region.

## Proposed selection rule

Use validation reference error only for explicit model selection after all
inferences have been sealed. Give the short (1), medium (6/16 averaged), and
long (all) duration regimes equal weight, each group equal weight, and average
the two initialization errors inside each group/view. Report worst group/start
alongside the mean. Failed arms count as failures and cannot disappear from the
aggregate; a model with incomplete outputs cannot win against a complete one.
Prefer a simpler model only under a predeclared tie rule, not post-hoc judgement.
The exact tie tolerance and treatment of nonstationary-but-finite fits must be
finalized before validation access. This document is deliberately a draft.

Do not select an independent hyperparameter for every duration on two groups.
Select one complete rule, then execute it once on the final 64-scan TEST group
at all duration views. A failed sub-300 m test remains a failure. Any later
development must label that test as exposed and use a new prospectively frozen
cohort for further final claims. With one final test group, even success gives
limited evidence about reliability across days and receiver configurations.

## If replication still misses the goal

Keep the untouched validation/test sets closed while resolving measured model
defects on TRAIN. Candidate directions are causal orbit-error modelling with
identifiability constraints, receiver-specific oscillator drift tied to actual
receiver labels, and robust correlation-aware observation weighting. Each needs
a bounded ablation and held prediction checks. Do not add flexibility solely
because it can move a known coordinate toward the reference. Reusing the
published receiver reference as a location correction would invalidate the
blind localization claim.

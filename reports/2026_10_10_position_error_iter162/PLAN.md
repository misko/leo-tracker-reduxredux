# Conditional geometry discrimination after iteration 161

Preparation only: freeze and publish numerical sources, inputs and runtime
before recording fits. The ongoing goal remains mean standalone error 0.4 km.
Iteration 161 found better held frequency likelihood for fitted-c in 24/24
comparisons but lower position error in only 17/24. Fold-only fitting worsened
aggregate position accuracy. This successor tests geometry preference within
each c arm; it does not propose fold-only deployment.

## Fixed inventory and hypotheses

Retain all twelve consumed members and exact sealed folds from iterations
160/161. For every member, take both ordinary fresh full-data position vectors
from iteration 161, labelled by their source zero-c and fitted-c fits. These
are hypotheses, not a per-scan choice based on reference error. Retain both even
if their coordinates coincide. Do not add reference-derived alternatives,
change membership, tune hyperparameters per scan or inspect reserved outcomes.

The comparison is 12 members × 2 position hypotheses × 2 training folds ×
2 c arms = **96 fixed-position nuisance fits**. Both c arms evaluate both
hypotheses, using identical observations, banks, priors and budgets. All
nuisance starts come from independent copies of the original common zero-c
state used in iteration 161; replace only its two position coordinates with
the relevant hypothesis. Do not import fitted-c nuisance values from the
hypothesis-producing fit. All training folds retain the original full-data
basis definitions and physical metadata.

## Fit and score

Use the unchanged joint fitter with fixed_position=True, 600 maximum
iterations, 90-second soft fit budget, timing half-width 20 seconds and the
existing hard60 slope constraints. Zero-c locks static c and both RF-time
coefficients exactly zero; fitted-c frees those same coefficients starting at
zero. Independently audit returned feasibility, unchanged hypothesis position,
objective parity and projected physical/nuisance stationarity at 0.001. The
fixed-position audit must project out the locked position coordinates rather
than demand an unconstrained spatial gradient of zero.

Evaluate the opposite fold at the returned fixed position and fitted nuisance
state, without further updates. Store training likelihood, prior penalty and
held likelihood separately. No retry or fallback endpoints count as success.
Every fit, audit and held-score failure remains in coverage; scoring failures
do not retroactively change solver qualification.

For each c arm separately, sum the two opposite-fold likelihoods for each
hypothesis, with each observation scored once by the model trained on the
other fold. A preference exists only if all four corresponding fit/score
receipts qualify. A globally fixed absolute summed-NLL tolerance of 1e-6
defines a tie. Report ties and incomplete comparisons explicitly. Never
compare scores across c arms to select the more flexible arm.

## Evaluation boundary and limits

Seal all 96 attempted receipts before any reference-coordinate evaluation.
Then report preference versus evaluation-only geographic error of both
hypotheses, dataset-specific coverage and paired mean/median/p95/worst errors,
regressions and preference accuracy. An incomplete or tied preference remains
unresolved, not replaced by an oracle or fallback. Report each c arm separately.
Always show resolved/evaluable counts out of all twelve members (four per
dataset). Geographic errors within 1e-9 km are evaluation ties: report these as
neutral and exclude them from a binary preference-accuracy denominator, while
retaining them in coverage and position-error summaries. Do not label choosing
either geographically equivalent hypothesis as correct or incorrect.

These hypotheses and model definitions originate from full-data inference;
the test is consumed-data conditional sensitivity, not independent validation.
The two hypotheses may share one local region, so success would not establish
discrimination across distant search regions. Failure would reject this
particular predictive selector, not every form of held-data model selection.
The official 193-member metric and deployed B7 stay unchanged. No new RF
collection. At most two single-thread numerical workers; all closed reserved
recordings remain closed.

# Separate native CFO changes from precision feedback

2026-10-26 UTC. Previous goal turn: **progress**. Complete refinement of 159
fixed native measurements produced raw geographic gains in two development
scans and both c arms, with paired research qualification only in DS24-0010.
DS24-0011 lost 57 postfit-only IDs at small residual-slope gate crossings.
The published result is commit 90816979b639ded7a4bb5c3c76174c55bf381977.
Operational inference remains unchanged and the fast-scan improvement goal
remains active.

The same intervention increased some orbit-conditional residuals and reduced
their Gamma precision. It is therefore unclear whether the position movement
comes principally from changed CFO or changed weighting. This iteration makes
that distinction with an actual nonlinear conditional-Gaussian factorial,
while identifying a feasible later validation cohort from existing metadata.

## Frozen mechanism comparison

Use the prior study's two scans, all original observations, 159 native CFO
corrections, graph ownership, fixed satellite assignments, causal catalogue,
aliases, nominal noise, likelihood powers, prior families, region and budgets.
Both c=0 and fitted-c arms receive the same correction vector. Do not remeasure,
drop points, reselect owners, add sources, alter gates or tune using geography.

For each scan and c arm, run four conditional-Gaussian fits:

| Cell | CFO vector | Fixed precision packet |
| --- | --- | --- |
| 00 | Original | Original endpoint |
| 10 | Refined | Original endpoint |
| 01 | Original | Refined endpoint |
| 11 | Refined | Refined endpoint |

Each packet contains the full original fragment noise_precision and
coefficient_prior_precision, including their order and units. Freeze Gamma
precisions, not nuisance posterior means, covariance, phase references or
position. Reuse existing conditional_gaussian with volume_weight=1 through
the original base-factory port. Preserve the complete predictive factor;
its mean/covariance must follow the conditional curved posterior while its
original sigma*sqrt(2) noise remains fixed. DS24-0010 has 615 predictive IDs;
DS24-0011 has none. The fitted-c mapping must preserve its actual full packet;
the existing helper's automatic unit insertion at index 8 is not permission
to overwrite a nonunit value.

Before inference, compare each diagonal at its saved last phase reference and
endpoint against the previous retained conditional coefficient, frequency
residual and predictive factor. The phase reference is the last fit's input,
not the subsequently updated/clipped posterior phase. Declare tolerances
before checking and distinguish converged VI numerical precision from exact
ID/alias identity. A conditional-Gaussian objective is not the previous VI
ELBO; numerical objective equality is not a valid prerequisite or conclusion.

Use the same zero position/phase initialization, 25 by 25 km regional bounds
centered at 37.906,-122.545, five phase-refresh rounds and 48 inner iterations.
There are exactly 16 planned fits, two workers and BLAS1, at most 30 seconds
per fit and 600 cumulative numerical worker-seconds including preparation.
No alternative start, rescue, scientific retry or budget extension. Preserve
all failed or incomplete slots. The four old VI refits remain separate saved
references and are not rerun. This is not an operational algorithm promotion.

## Outcomes that distinguish mechanisms

For endpoint vector x, report the CFO contrast x10-x00, precision contrast
x01-x00 and interaction x11-x10-x01+x00. Also report each contrast under the
other factor level. Average the two CFO contrasts and the two precision
contrasts to give a symmetric vector decomposition summing to x11-x00.
Report signed east/north vectors and cancellation; do not add displacement
norms or call them unique causal percentages. If fits fail or contrasts change
strongly across arms, retain that ambiguity rather than declaring a mechanism.

Report actual conditional residuals, fixed packet identity, position movement,
original residual/owner/phase checks, postfit compatibility, native membership
and original accepted-ID retention from each cell's own posterior. Do not call
a coverage helper that silently rebuilds the original VI model. No Gamma
convergence claim applies to a frozen-Gamma solve. Check phase-refresh and
optimizer behavior separately. Original acceptance semantics remain visible;
raw endpoints do not become operational improvements when gates fail.

Freeze the evaluator before outputs. Seal inference and pass independent RF
review before root releases the same known-site coordinate for geographic
evaluation. Report distance for all completed endpoints, including failures,
with original operational reference and both c arms. These exposed cases are
mechanism evidence, not validation or physical CFO truth. Precision packets
were learned at different endpoints, so packet effects are not proof that
physical measurement noise is wrong. Objective values across different CFOs
or packet assumptions are not evidence for choosing a better physical model.

## Parallel ownership

- A /root/plan_validation owns solver/: preparation, narrow implementation,
  component-owned fixtures, frozen protocol/evaluator, then the 16 fits only
  after B preflight and root GO. No mutation of earlier artifacts or repository.
- B /root/plan_evidence owns audit/: independent source and saved-artifact
  preflight/terminal checks, at most 120 numerical seconds; no new detector,
  geometry or optimizer runs. Check the actual posterior used in all gates.
- C /root/next_validation owns validation/: metadata-only later fast-scan
  inventory and exposure audit, at most 10 numerical seconds. Identify a
  chronological block without reading GPS errors or ranking outcomes. Describe
  raw authority, prepared parents and feasible bounded measurement coverage;
  do not silently call exposed cases held out or launch a campaign.
- Root owns synthesis, plots review and report publication to remote main.

Use existing helpers and narrow scripts. No generic framework, infrastructure,
new RF collection, production changes, golden changes, postscan TLE or stationary
pooling. All paths beneath /mnt/qnap01 stay read-only. Preserve unrelated root
tracked diff add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b.
Freeze this plan; necessary later clarifications belong in a separate addendum.

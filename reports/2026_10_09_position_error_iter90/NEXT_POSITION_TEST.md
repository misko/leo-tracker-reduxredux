# Next position test: one frozen paired correction, no new nonlinear states

**Recommendation, conditional on the completed iteration90 evidence:** test one
fixed, background-projected receiver-by-satellite contrast followed by one
same-start B7 refit. Prefer the globally specified existing-smooth-clock projection
for this candidate, rather than choosing between backgrounds per recording.
It asks whether residual contrast that cannot be explained by the clock span
already available to B7 matters on uneven receiver observations. This document
does not authorize execution or claim an accuracy improvement.

## Evidence and the missing causal step

[Iteration87](../2026_10_09_position_error_iter87/RESULTS.md) reconstructed all148
B7 endpoints. It found826 eligible satellite groups and30,862 pairs in those
groups;138 recordings support at least2 eligible satellites and10 are explicit
no-ops. The fitted-c median recording absolute group-mean difference is18.001Hz,
versus32.690Hz for c0. These are conditional residual descriptions, not proof
of satellite-specific bias or position information. The same report finds
remaining serial correlation; independent-pair precision is therefore only a
working approximation.

Common receiver offsets, time/channel coverage, association mistakes or different
selected spectral components can explain receiver differences. Iteration90 is
testing these confounders without fitting position. Its outcomes were not read
to prepare this proposal. The diagnostic clock projection is unpenalized: loss
of a contrast direction establishes algebraic confounding, not that B7's
regularized clock could absorb it cheaply or that the implied clock is physical.
If common-clock projection removes the contrast, do not manufacture a satellite
correction from that unidentifiable direction. Surviving contrast justifies a controlled
test; it does not establish that the correction will transfer to unpaired windows.

## Exact candidate

Use the ordinary accepted fitted-B7 endpoint to freeze assignments, eligible
satellites, exact paired joins and the iteration90 smooth-background projected
contrast. Keep its global30Hz prior and explicit pair variance31,250Hz². The
background includes intercept, linear time, channel and the **existing** B7
smooth-clock span; add no knots or RF/satellite nuisance columns. Use zero
correction for ineligible satellites and unsupported modes. No per-recording
choice of prior or background is permitted.

For every observation/candidate prediction, add−d_k/2 on RX0 and+d_k/2 on RX1.
Apply the same frozen d to both c arms and retain every original observation,
including unpaired observations. This is a candidate-component prediction
correction, not reassignment of measured frequencies using a hard satellite label.
Keep the original mixture/clutter likelihood and optimize the existing B7
position, clocks and timing once from its ordinary endpoint. Add no optimizer
variables and do not reestimate d as assignments change. Future operational use
would need the same ordinary-state estimation step, not stored per-scan constants.

The core change is a fixed receiver-sign lookup in the prediction matrix; existing
analytic derivatives remain valid because d is frozen. Validate the altered
likelihood and gradient rather than assuming an unchanged implementation path.
The one-time projected linear solve and one additional refit are measurable
costs. This is simpler than joint contrast fitting, but treating d as exact ignores
its estimation uncertainty and can increase bias.

## Why a position change is possible, and when it is not

For balanced, simultaneous, equal-variance Gaussian pairs with known assignments,
write `m=(y0+y1)/2` and `q=y1-y0`. The residual sum of squares is
`2*(m-g(position))² + (q-d)²/2`. Changing d cannot change the common-mode spatial
gradient. Common/differential coordinates expose this fact cheaply; they create
no new geometric information.

Any improvement in the real mixture problem must therefore arise through uneven
or unpaired receiver support, calibration coupling, or changed associations.
That is the causal hypothesis to test. It is not valid to convert an18Hz receiver
difference into an asserted position benefit. Nor should an association change
automatically be described as physically correct merely because its score improves.

Mandatory synthetic tests include exact balanced-pair spatial-gradient invariance,
receiver-swap sign symmetry, zero-correction B7 equivalence, finite-difference
gradients, and a controlled unbalanced-support example. Demonstrate both a case
where the injected correction helps and a misspecified case where it can hurt.
A wholly clock-confounded contrast must remain zero.

## Controls and acceptance evidence

Freeze a full148 protocol before fitting. Run exactly two same-start configurations:
B7 refit with zero correction and B7 refit with the frozen correction. Match
observations, candidate banks, all other priors, search/fit budgets and convergence
checks. Run both c0 and fitted-c; lock static c and RF-time terms in c0. The shared
fitted-derived correction makes this a conditional c ablation, which must be stated.

Keep the prescribed B7 fallback on independently unqualified attempts, recording
the raw attempt. Do not choose between candidate and control by reference error
or compare raw objectives across their different prediction models as an
operational winner rule. Preserve all no-ops, missing inputs and failures.

Report dataset-specific mean/median/p95/worst, paired regressions, convergence and
fallbacks, frequency fit separately, and added wall time/memory. Also compare
assigned counts and responsibility changes, and describe paired versus unpaired
support using inference-only definitions frozen before outcomes. This separates
a broad correction effect from a few assignment changes or optimizer restarts.

## Generalization and deployment risks

The rule uses simultaneous RF measurements, hypothesis assignments and the
existing receiver model; it contains no reference position, favored direction,
geographic correction or remembered satellite-specific constant. Known coordinates
remain evaluation-only. This makes the construction reference-free, not proof
of generalization across locations or hardware.

Risks include time/channel confounding left outside the chosen clock span,
different spectral components, circular-residual branch effects, correlated pair
noise, and transferring pair-derived estimates to unsupported times/channels.
Another risk is improved in-sample frequency fit with worse position. A second
refit may also be too expensive for the eventual embedded budget despite the
small linear correction itself.

Keep B7 deployed while this consumed-corpus test runs. Require global development
selection followed by frozen randomized whole-recording validation with exposure
auditing before promotion. The post-DS18 reserve remains unopened by this proposal.
If the correction has little accuracy benefit or increases tail risk, retain the
simpler B7 model; do not expand nuisance flexibility merely to reduce residuals.

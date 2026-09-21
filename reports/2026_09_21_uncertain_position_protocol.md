# Archived positioning comparison: experimental protocol

The requested outcome is a more accurate position estimate using orbital
information available before each capture. Lower Doppler RMS alone is not a
success criterion. This protocol is recorded before evaluating the new mixture
and weighting experiments. The existing causal orbital-prior experiment has
already been evaluated and is not claimed as prospectively blinded here.

## Frozen reference and scope

- Reproduce the strict causal comparison's 622 episodes and 21,702 observations.
- Preserve original randomized fitting/evaluation masks for the initial matched
  ablation; explicitly identify correlation across the split as a limitation.
- All target TLE epochs and archive collection times precede capture start.
- Future TLEs may appear only in explicitly labelled oracle diagnostics.
- Use the original geographic prior and acquisition initialization. A local
  refinement is reported as local; it is not another exhaustive regional search.
- Known receiver coordinates are for sealed inference evaluation only, never
  candidate generation, prior learning, tuning, or selecting solver starts.
- No new RF captures, production changes, or automatic deployment of a research
  model. No new queues or orchestration systems.

## Comparisons and ownership

| Stage | Question | Implementation owner |
|---|---|---|
| A | Does the current fixed-identity fit reproduce? | Evaluation agent |
| B | Does balancing source segments or satellite/pass groups help? | Evaluation agent |
| C | Does retaining candidate identity uncertainty improve position refinement? | Mixture agent |
| D | How much information is overstated by correlated measurements? | Evaluation agent |
| E | Can past orbital updates predict useful target corrections? | Orbital-prior agent |
| C+E | Does the frozen causal orbital prior improve the mixture model? | Mixture and orbital agents |
| F | What short-fragment evidence is excluded, and is its safe recovery feasible? | Audit after matched-cohort comparisons |

Implement stages incrementally. Report unavailable stages as incomplete; do not
claim the full hierarchical model from a weighting or covariance diagnostic.
Do not add variations in response to evaluated coordinate error. A follow-up
chosen after seeing results is exploratory and must be labelled accordingly.

## Required inference evidence

For each run retain input hashes, immutable configuration, fitting/evaluation
counts, convergence status, starting modes, candidate support and truncation
diagnostics, timing bounds, fitted nuisance terms and runtime. Preserve the
unassigned hypothesis and catalogue prior mass in mixture scoring. Evaluate
held-out mixture predictions using fitting-conditioned identities and nuisance
parameters; never choose a new identity using evaluation observations.

Keep repeated measurements' physical grouping available. Do not count an RF
observation more than once. A track with an uncertain identity must not silently
become a fully trusted identity because its maximum-likelihood residual is low.
Do not interpret approximate likelihood weights as calibrated probabilities.

## Evaluation

Report horizontal position error, randomized held-out RMS, predictive likelihood
where comparable, uncertainty diagnostics, and runtime. Give baseline and new
results on exactly the same observations before expanding support. Do not compare
likelihood values across incompatible normalizations as though they were equal.

Predefined group-deletion diagnostics use NORAD and recording groups to test
influence. They measure robustness on this dataset, not independent accuracy
trials. Known satellite identities are unavailable, so real-data association
confidence calibration cannot be certified solely from agreement with another
TLE fit. Synthetic controlled tests should check mixture behavior, clock/orbit
separation, held-out isolation, and correlated evidence handling.

All recordings are from one previously examined location. Any accuracy gain is
conditional evidence on this archive, not proof of generalization to arbitrary
locations. A result that lowers RMS but worsens position, collapses onto one
fragile mode, or depends on future orbital data does not meet the requested
operational objective. Preserve and report such negative results.

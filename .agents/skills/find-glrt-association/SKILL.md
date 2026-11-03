---
name: find-glrt-association
description: Investigate which satellites explain GLRT CFO tracks or contiguous unassociated points. Compare causal and later TLEs, alias-aware orbital predictions, polynomial quality, and progressively richer shared nuisance models; render evidence and report the best supported associations with qualified confidence in uniqueness. Use for missing or suspicious associations, long unassociated curves, possible bad track joins, and receiver-versus-orbit model debugging in this repository.
---

# Find GLRT association

Produce a reproducible investigation of satellite identity, model mismatch, and ambiguity. Recover useful evidence without forcing every curve into a satellite hypothesis. A good polynomial, a compatible orbit, a uniquely supported satellite, and a useful localization constraint are separate conclusions.

Read [the experiment protocol](references/experiment-protocol.md) before fitting and [the deliverable specification](references/deliverables.md) before plotting. Use [the repository tool map](references/repository-tools.md) to locate reusable implementations; inspect their current source before execution.

## Establish the investigation

1. Resolve the requested scan, receiver/channel, track or time window from the user's request and available manifests. If unspecified, inventory residual native GLRT and start with the longest contiguous source. State whether ranking uses duration or unique point count. Keep the first investigation bounded to the selected sources.
2. Record repository revision, algorithm/release, scan UTC interval, RF/channel mapping, sample rate, alias period, native observation IDs, graph parents/joins, and the exact published position and ownership artifact. Preserve all input artifacts.
3. Reconcile native GLRT ownership against the **published output**, not a proposed recovery or intermediate fit. Distinguish associated, graph-tracked but unassociated, and untracked points; distinguish missing search results from rejected hypotheses. Split only for a documented gap, alias event, join, or independently evidenced change.
4. Freeze a run specification: input hashes, catalogue selection, candidate universe, position policy, nuisance priors, covariance/noise policy, search bounds/budgets, and comparison rules. Discover these from the versioned pipeline where available. Record any new research assumption rather than presenting it as production behavior.

## Fit and diagnose

1. **Audit the curve first.** Fit polynomial degrees through four with a complexity penalty on the original observations. Examine residual structure, endpoint leverage, graph joins, and independent pieces. Preserve point exclusions as explicit clutter hypotheses. Do not select a higher order merely to bend toward one endpoint.
2. **Build two TLE ledgers.** Use a verifiably causal archive and a separate, time-selected post-observation archive. Preserve timestamps and element hashes. Search the eligible catalogue rather than just previously nominated satellites. Missing later TLEs remain missing; never silently substitute causal elements and call them later.
3. **Replay the baseline.** Reproduce the saved prediction and gates before experimenting. Start at the saved inferred position; disclose any fixed true-site diagnostic separately. Use the experiment protocol's nuisance ladder with the same observations and fair candidate search budgets. Include aliases, phase starts, runner-up candidates, and a no-match alternative.
4. **Diagnose the required correction.** Compare frozen-calibration TLE swaps and separately refitted models. Test whether the discrepancy follows one receiver/band across satellites or one satellite across receivers. Use independent tracks to support shared corrections; report when support is absent or confounded.
5. **Test identity stability.** Compare competitors under the same model and noise assumptions, examine position/phase basins and active curvature, and use independent tracks or randomized whole-group predictive checks where available. Full-data residuals alone do not establish uniqueness. Label analyses without independent evidence accordingly.
6. **Test utility separately.** For a proposed recovery, rerun the exact incumbent acceptance checks and report changes to existing owners. If localization is evaluated, compare matched `c = 0` and fitted-`c` arms and report position error separately from frequency fit. Evaluation truth must not select identities, priors, or model complexity.

## Return an evidence-based decision

Write the report, machine-readable comparisons, and scientific figures defined in the deliverable specification. Give each source a best causal candidate, best retrospective candidate, runner-up, required correction, residual verdict, identity confidence, and next discriminating test. A candidate may be strongly preferred yet still fail the physical model or production gates; show both facts.

Use qualified outcomes: **supported within searched catalogue**, **ambiguous**, **model-sensitive**, **retrospective-only**, **unsupported**, or **not evaluated**. Do not convert an uncalibrated score margin into a satellite-identity probability. If all candidates fail, retain the best diagnostic hypothesis and explain the failure rather than assigning it.

## Boundaries

- Follow repository `AGENTS.md`. QNAP inputs are read-only; use existing recordings and approved archive adapters. Do not initiate RF collection.
- This skill produces research artifacts. It does not itself authorize deployment, changing production ownership, updating golden fixtures, publishing reports, or pushing Git commits. Follow the user's explicit authorization when those actions are requested.
- Later TLEs are diagnostic evidence and remain outside causal inference outputs. Avoid known-site, hand-picked NORAD, or scan-specific constants in reusable inference.
- Do not increase association percentage by counting alias copies, interpolated polynomial samples, repeated peaks from the same opportunity, or silently dropping difficult native points.
- Do not relax a gate merely because a long track looks convincing. Explain its measured failure and test a general, independently supported correction.
- When tools or archives are unavailable, report the missing evidence and complete the parts that remain possible. Do not claim an unrun search or fabricate a curve.

# Deliverables and completion checks

Write to a fresh local research/report directory following repository conventions. Do not overwrite sealed results. Use standard scientific plotting tools, not generated illustrations. Keep detailed per-candidate data local if large; commit or publish only when requested, following existing artifact policy.

## Required figures

1. **Native GLRT context:** CFO versus scan time, receiver/channel panels, selected target highlighted, assigned points colored by satellite, graph-tracked unassociated points in a distinct color, and untracked points with a distinct marker. Include a labeled GLRT-score color panel or separate score panel. State explicitly what gray means if used. Show observation support, gaps, original graph-piece boundaries, and calibration event times where relevant.
2. **Orbit overlays:** native wrapped CFO and a separate alias-lifted view for the same data. Plot physical orbital Doppler translated into the documented CFO reference and the fitted radio-adjusted prediction with different line styles. Label phase and all corrections. Break lines at alias wraps and missing spans. Show causal versus later TLE curves for the winning candidate and competitive alternatives, with uncertainty bands where estimable.
3. **Residual and polynomial audit:** residual versus time with zero/reference-noise bands, block means, residual distribution and time correlation; polynomial degree/complexity comparison and endpoint sensitivity. For long tracks add 20-second zooms. Show both original points and any explicit clutter responsibilities. Do not hide failing ends or joins behind a whole-track RMS.
4. **Candidate/model comparison:** a satellite × nuisance-level score or predictive-margin heatmap, separate causal/later panels with consistent normalization, and residual-gate results. Distinguish missing, not searched, optimizer failure, and gate rejection. Include a parameter/prior-pull table or plot and winner stability across predictive partitions/starts.
5. **Correction attribution:** where multiple tracks exist, compare residuals by receiver, band, and satellite at matched times. Show whether a proposed correction transfers to independent tracks. If evidence is absent, state that the attribution is unresolved rather than manufacturing a panel.

If localization is in scope, add matched before/after estimates and c-arm results. Report coverage and position accuracy separately. Association confidence is not a proxy for position information: quantify the added geometric constraint or position sensitivity when possible.

## Report structure

Lead with the best causal and retrospective conclusions and their limits, followed by the evidence. Include:

- Scope, source inventory, published ownership, algorithm version, and search completeness.
- Polynomial/alias/join verdict and measured residual failures, including the threshold and distance from it.
- Candidate comparison table: rank, NORAD/name, TLE regime/age, nuisance level, native points/span, RMS, predictive score/margin, failed gates, prior pulls, visibility, and uniqueness status.
- Best explanatory correction and the evidence distinguishing receiver, band, clock, TLE, and track-construction hypotheses.
- Recovery impact: native points added/lost/reassigned, unique-point GLRT percentage with denominator, incumbent regressions, and localization results only if actually evaluated.
- Open ambiguity and the next bounded experiment most likely to discriminate alternatives.
- Reproduction commands, inputs/hashes, and links to every figure and machine-readable result.

Each summary row should answer: **Which satellite is best supported? What else fits? What correction is required? Why was it originally missed? What remains unproven?**

## Machine-readable artifacts

Use these as research outputs, not new public persisted contracts:

- `run_manifest.json`: revision and dirty-source hashes, scan/source IDs, observation/ownership/catalogue hashes, TLE cutoff and selection rule, position policy, candidate count/filters, parameter priors, covariance, budgets, seeds, commands, environment, and timing.
- `tle_inventory.csv`: satellite, regime, element epoch, archive availability/collection, provenance status, element hash, pair availability, propagation validity.
- `candidate_fits.csv` or `.json`: source, satellite, TLE hash/regime, model level, c arm, search status, selected basin/alias, parameter estimates/uncertainties, degrees of freedom, full/retained RMS, normalized score, predictive results, gate values/thresholds/margins, and rejection reason.
- `association_summary.csv`: source and native IDs/reference, best causal candidate, best retrospective candidate, runner-up, required model, identity status, model-adequacy status, production-gate status, independent evidence, and remaining ambiguity.
- `predictions` and `residuals` in the repository's usual array/table format: exact native IDs/times, CFO, alias lifts, orbital-only and adjusted prediction, polynomial prediction, residual, uncertainty, ownership, and partition membership. These must permit plot regeneration without rerunning search.
- `report.md` and `figures/` with explicit units, legends, and provenance.

Use null plus an explicit reason for unavailable values; never substitute zero for an unrun fit. Do not output NaN/Infinity as purported JSON numbers. Protect archive credentials and unrelated private metadata.

## Confidence vocabulary

Keep identity confidence and physical-model adequacy in separate columns.

| Status | Meaning |
| --- | --- |
| Supported within searched catalogue | Best candidate survives matched competitors and reasonable model/start perturbations, with adequate residuals and independent evidence; state the searched universe and limits. |
| Ambiguous | Multiple identities/aliases remain competitive or independent evidence is insufficient. Report the alternatives. |
| Model-sensitive | Winner or apparent success depends on flexible corrections, boundary fits, weakly identified parameters, or position assumptions. |
| Retrospective-only | Later orbit information supports a match that causal information cannot establish. Do not relabel it a causal recovery. |
| Unsupported | Completed search found no candidate that meets the declared evidential/model criteria. Retain the diagnostic nearest candidate. |
| Not evaluated | Required search, archive, or fit is missing. This is not a failed satellite match. |

Report numerical score margins and stability counts with their definitions. Posterior masses, if computed, are conditional on declared models/priors and need independent calibration before being called empirical identity probabilities. A clean residual after fitting a flexible model is not a probability of uniqueness.

## Completion review

- Every plotted point traces to a native observation; alias copies and alternative peaks do not inflate counts.
- Causal and retrospective provenance, fixed-position versus refitted results, and orbital versus radio corrections are visible.
- Polynomial and orbital fits show residual structure, not only RMS.
- Best candidates and competitors received comparable treatment; missing coverage and optimizer failures are visible.
- Confidence describes both supporting and contradictory evidence; ambiguous outcomes are allowed.
- Any claimed localization gain has a matched evaluation and c ablation; better frequency fit alone is not labeled better localization.
- The report states what was actually executed and what remains a proposed experiment.

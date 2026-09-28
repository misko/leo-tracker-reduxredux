# Post-unblinding reference score diagnostic

This is an oracle diagnostic, not a deployable estimator or an improvement to the confirmation results. No reference coordinate or fitted identity was supplied to either prior's searches. The frozen models were evaluated after confirmation at the reference and12 fixed cardinal offsets (±1.5625, ±5, ±25km east/north). All16 saved search selections were independently rescored and reproduced to absolute tolerance1e-7. Four diagnostic runs completed; their artifacts bind the source script, search result, audited topology and frozen models.

Lower objective is better. The table shows selected loss minus reference loss; positive means the frozen search failed to return a point as good as the reference under its own objective.

| Scan | Sacramento D | Sacramento joint | Reno D | Reno joint |
|---|---:|---:|---:|---:|
| b5604c3d838fa7ed | −0.04845 | −0.05985 | −0.04689 | −0.05495 |
| f147dd8a5bc99346 | +1.30847 | +0.00097 | +0.00261 | +0.00448 |
| 609d7a8d9861f3db | +0.83265 | +0.93499 | +0.77027 | +1.12129 |
| 40ebc07665464c7d | +1.48770 | +2.10299 | +0.00072 | +0.00451 |

The catastrophic f147 Sacramento D error, both609d Reno errors, and both40eb Sacramento errors are therefore demonstrably coverage/optimization failures, not cases in which the scored objective prefers those distant outputs to the roof reference. This does not prove that the reference is the global optimum or that every wrong region scores poorly. Fine-grid gaps near the reference are not equivalent to catastrophic search failures.

b560 instead exposes local model bias: all its selected scores beat the reference. Among the13 diagnostic points, both models favor5km east. More complete optimization alone cannot make the reference win against an already better-scoring displaced point. For609d both models prefer1.5625km north within this limited stencil. For f147 and40eb the reference is best within the stencil. These discrete diagnostics do not define calibrated error bars or a resolution estimate.

## Consequences for the next experiment

1. Test coverage-preserving, multi-region refinement under identical budgets and independent priors before attributing large geographic wins to improved geometric resolution. Do not initialize either prior from this oracle diagnostic, another prior's winner, or reference coordinates.
2. Retain a separate local bias check: b560 cannot be solved by more search alone.
3. The direction-free reception control was independently fitted on the same six audited calibration scans (`M0_CONTROL.md`). Its likelihood is constant across candidate/location for fixed track observations, so it factors through the shared-identity marginalization and cannot change a correctly implemented D search's ordering. M1 adds direction-dependent information, but the present M1 evidence has not demonstrated reliable fine-position improvement.
4. Five-MHz confirmation recordings use a sample-rate category absent from calibration (2.5/7.5/10MHz). They receive reference-level encoding; this is an explicit calibration limitation, not proof of the observed errors' cause.

These four recordings are now unblinded diagnostic/development data for any changed method. A changed method requires another frozen, outcome-blind evaluation. The full goal remains unproven.

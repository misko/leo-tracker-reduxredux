# Third-stage joint-mode polish protocol

This diagnostic is eligible only when a sealed, successfully launched continuation ends
`unresolved` with an unconverged global-best mode. It does not replace or relabel the
immutable 90-second primary result or the two-stage result.

The polish rebuilds the same full scan, candidate bank, fixed 30.48 m MSL height model,
normalized Student-t likelihood with four degrees of freedom, flat EN disk prior, and
Gaussian clock, receiver-drift, and satellite-epoch priors. It starts only from the saved
global-best continuation state and processes every observation once per objective.

At most 24 additional iterations are allowed. The external budget is 180 seconds minus
the measured primary and continuation launcher wall times. The internal deadline is the
smaller of 85 seconds and that remainder minus a five-second write/seal margin. A run is
ineligible unless both remaining budgets are positive. The reported winner is the lowest
final objective among every primary mode, continuation mode, and the polish mode.

All parent receipts, seals, sources, inputs, budgets, and objective histories are bound in
the new receipt. Results are qualified as a budget-adaptive third-stage diagnostic.

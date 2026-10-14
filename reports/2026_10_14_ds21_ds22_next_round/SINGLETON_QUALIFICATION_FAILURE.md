# Retained singleton acceleration qualification failure

The private fast singleton prototype (47da34514) passed seven component tests,
but its real-corpus gate (0b81cd219) failed on the first original all-band seed
for BOTH DS22-001 and 003. Each qualification made two objective evaluations,
zero optimizers. Objective, complete physical/nuisance gradients, likelihood,
satellite/clutter probabilities and prediction gradients passed; the
per-satellite conditional residual summary failed. No accelerated fits ran.

A separate two-evaluation diagnostic per case retained the failure and
identified floating-point underflow:

| Case | Residual entries outside tolerance | Total entries | Largest responsibility among mismatches |
| --- | ---: | ---: | ---: |
| 001 | 68 | 148534 | 2.488e-317 |
| 003 | 25 | 136650 | 1.603e-317 |

The old log-scaled posterior can retain subnormal probabilities that become
zero when the prototype forms an absolute Gaussian density before dividing by
the clutter floor. Dividing a residual numerator by those tiny probabilities
then yields different conditional residual summaries (maximum difference
4840/4840.75 Hz). These entries have negligible probability, but that does not
justify weakening the promised equivalence gate or treating the prototype as
qualified. This is a numerical prototype defect, not evidence explaining the
original localization error.

Next implementation should preserve the original log-domain arithmetic for
affected tail rows while retaining the faster path for ordinary rows, followed
by the same full-state checks at all six seeds and winner in each view. Do not
change existing frozen source files or rerun either failed namespace. The
original model fits and acceptance rules remain unchanged.

Receipts: `local/ds22-singleton-qualification-v1/DS22-{001,003}` and
`local/ds22-singleton-tail-diagnostic-v1/DS22-{001,003}`. Diagnostic source is
`singleton-tail-diagnostic.py`, commit 11fc761e4; it validates the exact failed
qualification source/input bindings before replay and reads no reference/held.

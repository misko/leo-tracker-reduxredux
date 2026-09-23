# Shared receiver CFO comparison: inconclusive optimizer attempt

Follow-up: the separately frozen [v2 comparison](2026_09_23_shared_cfo_v2_results.md)
improves every training initializer but identifies residual local-optimum
limitations through an explicit nested-model check.

**This attempt does not validate or reject a common receiver phase model.** The
bounded continuous optimizer returned worse training objectives than its
initializers in all four independent fits and three of four shared fits. The
predeclared safeguard retained those initializers. Successful optimizer status
therefore did not establish a useful solution of the comparison problem.

The [protocol](2026_09_23_shared_cfo_protocol.md), executable, and two synthetic
tests were frozen in `ddde4d7b` before this replay. Saved snippet hashes were
checked against the preceding joint-pilot replay; no new RF was collected.
The original seeded random masks were reused. These are already-inspected
development samples, not fresh validation.

## Why this test was attempted

The [joint-pilot replay](2026_09_23_joint_pilot_isolation_results.md) supported
incremental two-component waveform prediction in both receivers at 19.025 s
and 28.200 s. Its independently fitted nominal-plus-residual CFOs imply
receiver-offset closure −266.882 Hz and +143.026 Hz respectively. These produce
−5.338 and +2.861 turns of double-difference phase evolution over 20 ms under
the fitted models. These are model predictions, not measured geometric rates.
The 50 Hz fit grid and absence of an uncertainty model prevent a precision
common-offset test from those numbers alone.

The new constrained arm sets the total RX1-minus-RX0 CFO equal for both sources,
while retaining separate eight-tone complex channel weights per source and
receiver. This is deliberately restrictive: real differential geometric rates
or source-dependent channel evolution can violate exact equality. It does not
assume that a common residual relative to uncertain nominal CFOs is equivalent
to a common total receiver offset.

## Complete outcomes

Positive held loss means constrained SSE exceeds independent SSE, normalized
by each receiver's held energy. These numbers describe the returned candidates;
they are **not a reliable optimized model comparison**.

| Time (s) | Independent returned initializer | Shared returned initializer | RX0 held loss (percentage points) | RX1 held loss (percentage points) |
|---:|---|---|---:|---:|
| 3.775 | Yes | Yes | 0.000 | 3.205 |
| 19.025 | Yes | Yes | 0.000 | 3.463 |
| 25.900 | Yes | No | 0.123 | 0.516 |
| 26.400 | Abstained | Abstained | — | — |
| 28.200 | Yes | Yes | 0.000 | 2.481 |
| 30.850 | Abstained | Abstained | — | — |

At 26.400 and 30.850 s, the fixed nominees differ by roughly one 227.273 kHz
alias in receiver closure. Exact common-offset equality is infeasible inside
all four ±2,500 Hz residual bounds. These are explicit fixed-alias abstentions,
not absence-of-signal findings. No alias was changed to improve an outcome.

All eight executed optimizer calls reported success, but seven produced worse
training SSE than their respective initializers. In the fallback shared
initializers RX0 is unchanged while RX1 is adjusted to the mean receiver offset;
the zero RX0 held losses in those rows follow from that initialization. They
are not evidence of a physically special RX0 role. A local optimum or optimizer
termination is insufficient evidence that a constrained global profile was
found.

The [binding](figures/2026_09_23_shared_receiver_cfo/binding.json) and adjacent
six per-probe JSON files preserve every fit, coefficient, objective, convergence
flag, evaluation count, fallback, and abstention. The frozen executable remains
unchanged. Synthetic recovery and held-response independence tests passed;
they did not exercise the multimodal real-data frequency objective sufficiently
to qualify this optimizer for the desired comparison.

## Consequence for association and motion

Two-component waveform evidence remains useful, but per-tone fitted phases
absorb unknown channel and receiver responses. They cannot yet be treated as
baseline phase, satellite direction, or transverse speed. The remaining
actionable numerical step is a training-only optimization qualification with
known difficult frequency/alias cases and explicit objective checks, followed
by a separately versioned shared-offset comparison. Do not tune the optimizer
against these held losses or claim a new independent evaluation on the same
responses. Better satellite association and receiver position remain unproven.

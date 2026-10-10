# DS17-027: bounded own-arm repair still fails qualification

This source/receipt review uses only the saved own-arm solver evidence for the
zero-led retained state. It does not inspect reference coordinates, position
errors or other outcomes, and performs no model evaluation or replay. Iteration
154 remains unchanged. The stage authority is
`results/DS17-027/repair/zero/stages/5264d7518b6e898a7953a81a383b1489b09a92a15c9a0cc9810031e1f471207e.json`.

| Saved quantity | Before repair | After repair |
|---|---:|---:|
| Objective | 32045.60982094734 | 32045.60982094723 |
| Same-arm projected stationarity | 0.001773898802822943 | 0.0012605034525530745 |
| Independent feasibility | true | true |
| Qualified at 0.001 | false | false |

The bounded solver reports success/status 0 after three iterations and 25
feasible evaluations. Recorded repair wall time is 0.06044430797919631 seconds.
There are zero independently stationary candidates. Its saved terminal and best
feasible summaries agree in objective and stationarity with the returned fit.
Thus this **fresh 154 terminal** fails the independent gate despite solver
success. It was not stopped by the five-second or 200-iteration cap. Increasing
either cap alone does not address the observed termination reason.

## What the source establishes

[hard60_bounded_fit.py](../../src/leo/analysis/hard60_bounded_fit.py) calls SLSQP
with `ftol=1e-11`. It optimizes a transformed constrained problem and subsequently
uses `_Problem.stationarity` to audit the original scaled variables and active
constraint normals. The audit excludes fixed position and locked c coordinates,
and requires projected infinity norm at most 0.001. The solver's internal success
condition is therefore not equivalent to this independent acceptance condition.
The wrapper correctly preserves and rejects the unqualified result.

The objective changes by only about 1e-10 while the gradient-based criterion
remains above threshold. This is consistent with an objective plateau or a
stopping-tolerance/scaling mismatch. It does **not** prove floating-point noise is
the cause, identify the offending coordinate, establish local curvature, or rule
out active-constraint/geometry effects. The saved summaries do not contain the
gradient and finite-difference curvature needed for that stronger diagnosis.
The fit's `boundary=false` is not evidence that every timing or coefficient
constraint is inactive; that flag concerns the spatial disk.

The distinction from the original 151 receipt matters. Its legacy coarse fitter
can return a best feasible evaluation other than the optimizer endpoint and did
not preserve the optional endpoint diagnostics. We can establish original
returned-state nonstationarity, not original solver-endpoint nonstationarity.
Only the fresh bounded 154 fit supplies the terminal evidence discussed here.

## Smallest proposed general successor

After the complete 154 experiment is assessed, a separate protocol could allow
one existing reduced-Hessian polish **only** when the same-arm bounded repair
returns a finite, feasible but independently unqualified state. Apply the rule
to both discovery policies and every retained region, without selecting labels
or states by position error. Reuse the sealed queues and preserve both failed
receipts; do not rerank discovery or release the original c lock.

The existing [100 reduced_newton.polish](../2026_10_09_position_error_iter100/reduced_newton.py)
already accepts `rf_arm`, `fixed_position` and the slope bound. An explicit
arm-correct port can call it with the original discovery arm, fixed position,
hard60, at most two rounds/100 objective evaluations, unchanged full KKT and
physical feasibility gates. Its active-face, gradient-difference curvature step
addresses coupled/scaled directions more directly than repeated objective-only
line searches. It rejects insufficient dimension budgets and non-positive
curvature rather than adding an arbitrary ridge. Its initial-score ceiling of
128 ULP is a numerical equivalence rule, not a relaxed convergence threshold;
preserve the outer nonincrease check against the original state as well.

Do **not** call [102 qualification.qualify](../2026_10_09_position_error_iter102/qualification.py)
unchanged: it hardcodes fitted-c in its preliminary problem and does not forward
the discovery arm to the polish call. That would be inappropriate for this
zero-c own-arm stage. A successor must explicitly test zero lock, fixed position,
active constraints, original objective binding, same-arm KKT and failure receipts.
It should record gradients/curvature already produced by the bounded polish so
the plateau hypothesis becomes testable without a separate uncontrolled replay.

This proposal reuses an existing small numerical mechanism and changes neither
the model nor the independent gate. It may still fail when a conservative active
face blocks descent or curvature is not suitable. It is not proof of positioning
benefit, justification to tighten SLSQP `ftol` per scan, or permission to accept
0.0012605 as converged. No successor implementation, freeze or execution is
authorized by this note.

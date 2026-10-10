# Own-arm qualification before the existing calibration transition

Source-only, conditional preparation. The directory was confirmed absent before
creation. No model calls, fits, recording reads, freeze or deployment have
been performed. Decide whether to run a successor only after complete iteration
151 review. The live protocol and every frozen source remain unchanged.

The retained-state diagnostic established that two original **returned best
feasible states** failed their independent KKT check. The coarse fitter did not
persist the optional terminal diagnostics in this path. The optimizer's actual
terminal state is therefore unknown; this is not proof that it stopped at a
nonstationary point or that increasing its iteration budget would help.

`own_arm.py` adds one narrow, injected-port wrapper. It first audits the original
state under its own discovery arm. Qualified states pass through without repair,
regardless of the saved optimizer/convergence flag. An unqualified retained state
gets exactly one existing bounded-fit attempt from its original vector, at the
same fixed position and under the **same** discovery arm, with hard60 slopes,
5 seconds and 200 maximum iterations. The zero-c coarse lock remains exact.
The supplied independent auditor must use the actual `_Problem`, original prior
disk, orbit-coverage/coupled timing constraints, static-c bounds, and fixed-position
constraints, with finite objective/gradient and full scaled KKT ≤0.001. Local
checks additionally reject moved points, changed vector size/arm, slope violations
and nonfinite states. A qualified replacement may not worsen the independently
repriced original objective by more than the existing 1e-6 comparison tolerance.

Only then does an explicit caller-supplied function invoke the unchanged
[150 transition](../2026_10_10_position_error_iter150/transition.py). This wrapper
does not import or construct that runtime adapter. It does not call iteration
102: that qualifier assumes fitted-c and cannot silently repair a zero-c state
under its original constraints. The ordinary 150 promotion/polish, if needed
after own-arm admission, remains a separate downstream action and cost.

The bounded port returns serialized PositionFit and diagnostics dictionaries;
a future adapter must use production `json_value` without losing terminal/best
state evidence. Originals, audit records, returned candidate, solver diagnostics,
rejection reasons and downstream transition results are kept separately. Invalid
nonfinite evidence is represented as a string for JSON-safe failure receipts,
never admitted as a fitted value. `own-arm-admitted` certifies only this gate,
not successful downstream calibration, final qualification or position accuracy.

No completed discovery score is overwritten or reranked, no retained region is
added, and no reference coordinate/error selects a repair or winner. The same
conditional rule applies globally to both discovery arms. The bounded fit already
prefers independently qualified feasible candidates when available, unlike merely
returning the lowest-score unqualified state; this is not just a longer legacy
coarse fit. Its five-second deadline is checked during optimizer evaluations and
callbacks, so independent audits and summarization can add wall time. Additional
attempts/cost must be explicit in any future frozen controller budget.

Fake-port tests cover both arms, exact budgets, unchanged
originals, bypass of already-qualified states, rejected movement/locks/nonfinite
values/worse scores, and preservation of failure diagnostics. These tests have
run as lightweight unit checks alongside the three publisher tests:
`14 passed in 0.09s` with the pinned 47e interpreter and pytest plugin autoload
disabled. Eleven cases belong to this wrapper. They exercise injected fake
ports, not an optimizer, numerical model, quadrature or recording. No additional
numerical research worker was started. Production-adapter parity and localization
benefit remain untested. No generic controller, storage mechanism or recording
adapter is added.

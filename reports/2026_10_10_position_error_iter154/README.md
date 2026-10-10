# Own-arm qualification before the existing calibration transition

Preparation and independent review are complete. Iteration 151 is fully evaluated
and published; this successor will test the uniform repair against fresh controls
using its sealed discovery. The implementation's 29 source/synthetic tests passed
in 1.43 seconds with the pinned 47e interpreter. Metadata-only preparation checked
the twelve members, source/input bindings and numerical runtime. No recording
fit, new grid, or deployment change has occurred in this iteration.

[PLAN.md](PLAN.md) defines the matched experiment and progression rule;
[REVIEW.md](REVIEW.md) records the independent source review. A separate metadata
freeze and publication precede the two-worker recording replay. The design notes
below preserve the original preparation rationale; the recording adapter and
all-48-terminal reporter are now implemented, rather than future proposals.

The initial retained-state diagnostic established that two original **returned best
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

## Possible successor execution after full 151 review

Reuse sealed 151 discovery rather than another grid search. Preserve all twelve
members and both discovery policies, including failed or incomplete rows. For
each completed queue, use exactly its three retained regions, original bootstrap,
satellite subset and original coarse fit. Do not rerank discovery using repaired
scores, substitute another region or use a later promoted fit as the original.

A separate protocol must bind the published 151 protocol; terminal searches,
original point/bootstrap bytes and retained-region trace authority; clean public
input identities and observation content/order; causal TLE snapshot and exact
bank ordering/orbit states; numerical sources/native library/runtime; and all
prior, constraint and fitting policies. Subset indices must identify the same
physical satellites. Reconstruct and independently reprice each original before
repair, checking its discovery-arm lock, fixed coordinates and physical bounds.
Keep reference-error evaluation authorities outside inference admission. Freeze
the additional repair budget and separate control/candidate stage identities.

The clearest primary comparison is **fresh downstream control versus fresh
downstream candidate from the same sealed discovery**. Control uses unchanged
150; candidate adds this own-arm repair before unchanged 150. Both retain three
regions and identical downstream settings, including both final c arms. Earlier
151 endpoints are historical parity comparators, not automatically fresh controls.
Expose control replay differences; time-limited fitting is not necessarily
bitwise deterministic, and tolerances must not change after outcomes are seen.

Reusing an unchanged regional continuation is defensible only if its effective
admitted prefit, correction, association, bank, vector/clock starts, constraints,
sources and complete input/policy bindings are identical and the relevant stage
receipts are complete and independently qualified. A changed prefit invalidates
all dependent stages. Unchanged coordinates alone do not establish equivalence.
Nor can an unchanged region justify reusing the branch-level B7 selection when
another region changes: that selection depends on the complete region inventory.
Any such reuse is explicitly cached computation with historical-cost accounting,
not fresh matched downstream timing. Fresh continuations are simpler to audit
for the initial small handoff comparison.

Report inherited discovery cost separately from new own-arm repair evaluations
and elapsed time, and separate those from existing free-c promotion, calibration
and final-fit costs. Apply the same repair rule to every retained own-arm failure
in both branches; labels, reference errors and earlier favorable outcomes never
decide which failures receive it. Preserve missing inputs, unqualified repairs
and budget exhaustion in full-member coverage. Evaluate position only after all
declared continuations seal, keeping both final c arms and frequency effects
separate. This design authorizes no replay, implementation, freeze or launch.

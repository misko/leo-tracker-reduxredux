# Preparation: bounded scalar polish of an ordinary failed calibration prefit

Pure prototype and synthetic tests only. No recording has been evaluated by this
prototype; parent review and a separate immutable freeze are required before the
single consumed ac11 diagnostic. Frozen iteration93 and production remain unchanged.

The algorithm uses the existing `_Problem` feasibility, physical bounds, scales
and independent KKT gate. Keep the supplied feasible original vector unchanged
even if the helper normalizes its internal start at a timing boundary; record that
helper delta. Reject an infeasible original rather than silently clipping it.

Choose the largest scaled projected KKT component among free coordinates. Test
both signs of the globally fixed scaled steps `1e-2,1e-3,...,1e-8` in that coordinate.
Only a strictly lower **exact unchanged objective** can replace the current state;
ties retain it. Fixed position, hard60, RF locks, timing bounds and priors remain
the same. No reference coordinate, position error or geographic preference enters
coordinate choice, step choice, stopping or acceptance.

Stop upon independent stationarity≤0.001, no tested feasible improvement, ten
rounds or160 objective evaluations. Retain every attempted trial, including
infeasible or failed evaluations; failed calls count toward the budget. Preserve
accepted-step provenance and monotonic objective history. No-improvement or a
solver-like success status does not override qualification.

This is a small diagnostic for a missed local refinement, not a general convergent
optimizer. A feasible multidimensional descent may exist when no tested scalar
step works, particularly at coupled constraints. The fixed grid can miss a useful
step or fail to reach the stationarity threshold within its budget. Lower score
does not establish better localization. Any subsequent region continuation still
requires independent qualification and inference-only comparable-score selection.

Synthetic tests cover monotonic quadratic descent, independent qualification,
active bounds, explicit no-improvement, fixed position/RF locks, bounded operation
counts, unchanged feasible boundary starts, and preserved failed trial receipts.
No new RF collection, reserve access or production change is part of preparation.

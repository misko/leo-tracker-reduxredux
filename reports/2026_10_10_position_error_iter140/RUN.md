# Full193 phase comparison execution

The frozen protocol was published to remote main in commit `e1592f931` before
execution. Its file SHA256 is
`1c5c86cd48e1aa8bd5fa37634989229f36b4eb970f699935fc9f939e577f1387`.
It binds 193 members, 1,615 sources and 773 inputs. Iteration137 verified both
archived models for every member with exactly zero objective difference before
this experiment was sealed.

One serial, single-thread worker was launched in the released second research
slot, while iteration129 retained the first. The owning SOL agent is
`/root/next_position_models`; launch session `85422`, batch PID `1368740`.
These identifiers record launch provenance, not a claim the process remains
live indefinitely. Recheck the actual handle or PID before reporting activity.

Initial execution check: DS16-001 completed, with all four timestamp/phase ×
fitted-c/zero-c attempts independently qualified. No reference coordinates or
position errors were inspected in this execution check. The controller continued
to the next frozen member. This is not an accuracy result or an early success
claim for the phase model.

Every member has at most four attempts under the frozen 90-second/600-iteration
budget. A failure remains an explicit receipt; there are no implicit retries.
The controller stops on a claim without a terminal result or a foreign receipt.
An observation timeout is not a process failure and must never trigger a restart.
Do not launch a second iteration140 worker. All193 terminal results are required
before the reference-only final reporter runs.

The [PLAN.md](PLAN.md) records pre-freeze preparation and matched model policy;
its historical wording is preserved because it belongs to the frozen source
closure. This execution note is outside that closure. Production is unchanged.

## First unqualified attempt: retained without retry

`POST18-NEWER-20261009-001`, phase/fitted-c, returned normally but failed the
independent convergence gate: stationarity 0.0011646383087408757 versus 0.001.
The receipt records `solver_success=True`, `reported_converged=False`, and
`independently_feasible=True`. It used 5.8079666 seconds and 206 saved feasible
evaluations, so the 90-second budget was not exhausted. No reference or position
error was inspected for this execution diagnosis.

The SLSQP fitter uses ftol=1e-11 and can report success before the independent
stationarity requirement passes. The receipt does not retain the solver message,
iteration count or separate terminal gradient blocks; it cannot identify the
exact successful stopping criterion or which parameter block dominates this
failure. Extending the maximum time would not force a successfully terminated
solver to keep working. This is an unqualified returned fit, not an exception,
and remains part of the final coverage and fallback accounting.

Source review confirms iteration100's reduced Newton repair is not a drop-in
joint-model solver: its vector-only evaluate/constraint layout excludes the
smooth-clock/RF/satellite block. A future repair would need the full scaled joint
constraints, c=0 RF locks, local position disk and independent qualification.
Iteration143's receiver-only step is also not a demonstrated fix without a
gradient-block audit. Neither changes this frozen experiment; no retry was run.

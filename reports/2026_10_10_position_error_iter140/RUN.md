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

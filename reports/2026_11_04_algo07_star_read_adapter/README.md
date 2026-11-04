# ALGO07*: operation-local read adapter and integrity qualification

The terminal-reuse prototype now lives in a component-owned **opt-in storage
adapter**. It has passed 55 focused tests and matches the previously verified
complete terminal and receipt values on DS26-0002 and DS26-0267. Normal stores,
installed workers and production defaults remain unchanged. Full numerical
qualification of this optimized candidate is still outstanding.

## What changed

`leo.storage.graph_terminal_reuse.GraphTerminalReader` creates a fresh validation
scope for every public `terminal(job)` call. `FastGraphPositionStoreV6ReadReuse`
uses that reader while inheriting the existing job lifecycle and storage
contract. It retains no entries across public reads. The original numerical
workers, native inputs, causal catalogue and scientific stage budgets are
unchanged.

The experimental coordinator is `tools/run_algo07_star_reuse.py`, a separate
entry point that substitutes this adapter only for the final stage's public
storage port. Its other stage behavior is copied from the frozen original
coordinator. The verification CLI selects it only when a **new case** is
initialized with `--candidate-terminal-read-reuse`; the reference always uses
the original watcher path. Candidate Python source files and both coordinator
scripts are pinned and checked before and after execution.

During implementation the original coordinator was briefly edited, then
restored byte-for-byte after checking the frozen manifest. No new coordinator
was launched with that edited entry point. Existing runs retain their mandatory
post-execution manifest verification. The separate experimental driver avoids
changing the frozen baseline for this work.

## Integrity evidence

The storage-owned tests exercise actual six-stage store implementations and
versioned terminal validators using temporary test data. They reuse an existing
contract fixture factory without editing scientific golden fixtures, and need
no hardware, QNAP or PostgreSQL.

| Scenario | Checked behavior |
| --- | --- |
| Changed native GLRT input | Rejected by original and warmed reuse paths |
| Changed acquisition inventory | Rejected by both paths |
| Corrupted terminal at each of six stages | Rejected by both paths |
| Deleted terminal at each of six stages | Rejected by both paths |
| Contract-valid but wrong embedded incumbent | Rejected by both paths |
| Valid outer terminal whitespace change | Exact original return value and updated receipt |
| Caller mutates a returned object | Independent later return; cached data remains unchanged |
| Symlink replacement | Re-enters original confinement checks |
| Source changes through nested reuse | Not hidden by warmed ancestor entries |
| Repeated calls to public reader / lifecycle adapter | Fresh validation scope every time |
| Experimental CLI selection | Candidate only; original reference command preserved |
| Candidate source edit or new source file | Source-pin validation fails |

The focused suite has **55 passing tests**, including storage, coordinator,
verification CLI and existing runtime-configuration tests. Lint passes. This
does not establish universal atomicity under arbitrary concurrent filesystem
mutations; no such claim is made by the prototype.

## Real completed-store checks

The component adapter was checked against the complete previously verified
original terminal/receipt hashes, without rerunning inference:

| Case | Complete return matches | Measurement scope |
| --- | --- | --- |
| DS26-0002 | Yes | One fresh component-adapter read |
| DS26-0267 | Yes | One fresh component-adapter read |

[evidence.json](evidence.json) records the component hash, full-return hashes,
reference receipts and prepared experimental configuration. These are exact
full-value comparisons, including both calibration arms. The earlier
[timing plot and prototype report](../2026_11_04_algo07_star_terminal_reuse/README.md)
remain historical component measurements, not a speed claim for the integrated
coordinator or production.

## Execution and acceptance

The zero-change DS26 pairs continue under the four-path bound. DS26-0102 has
completed ALGO04 on both sides and resumed from ALGO05. DS26-0170 has completed
ALGO02 and resumed from ALGO03. Its [initial comparison](ds26-0170-initial.json)
passes all 17 prepared files and six scientific result files, including both
calibration arms, with zero differences. Their full comparisons remain pending.

A new `iteration001/DS26-0002` candidate is prepared with fresh native evidence
and pinned experimental code. It adopts the completed independent reference
for parity only; no timing comparison may be inferred from a reused reference.
It has not started numerical execution at this report checkpoint. Require the
full DS26 science/artifact comparisons before accepting this iteration, then
measure controlled end-to-end performance. The existing grid-deadline artifact
failures remain visible and are not waived by scientific parity.

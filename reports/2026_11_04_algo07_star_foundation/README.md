# ALGO07* iteration 000: isolated coordinator and DS26 inventory

ALGO07* is a runtime implementation of production ALGO07. Its first version
preserves the initial fit and every subsequent recovery pass. It has not been
qualified or deployed, and no speedup is claimed in this report.

The execution plan is [ALGO07*](../../docs/operations/algo07-star-plan.md).

## Scope and acceptance gate

The mandatory iteration gate is fresh production-versus-candidate comparison on
all available DS26 fast scans, retaining missing inputs and failures in the
denominator. Compare both `c=0` and fitted-`c`, track memberships, causal elements,
satellite ownership, nomination and acceptance decisions, nuisance estimates,
objectives, optimizer histories, endpoints and presentation evidence. A matching
final error alone is insufficient. Reference coordinates are for presentation
and evaluation only.

No recovery pass may be removed just because it usually rejects proposals.
Queue handoffs and repeated preparation are the first optimization candidates;
changing scientific search budgets or priors is outside the exact-equivalence
track. Production workers currently have different pinned runtimes, so the
initial coordinator retains their separate interpreter processes.

## DS26 inventory

| Accounting | Scans |
| --- | ---: |
| Total DS26 members | 317 |
| Fast scans included | 159 |
| Fast scans with verified native evidence available | 158 |
| Fast scans with no native run | 1 |
| Adaptive scans excluded | 158 |

Membership SHA-256:
`9e4c7b0528b21329792783f337063ebb838048b186781985c95231d5fe4dd3c6`.
This inventory checks native tracking evidence, source inventory bindings and
the native report through public storage ports. It does not rerun or re-verify
raw IQ, and availability does not mean a successful position solution.

The older retrospective ALGO07 audit contains only 148 DS26 outcomes. It is useful
for selecting diagnostic cases but cannot stand in for the current inventory or
fresh numerical qualification.

## Implemented foundation

- `FastScanStore.export_replay_inputs` creates a new private store containing
  exact copies of three native evidence documents. It copies no fitted answer
  and preserves the original tracking bytes and job identity.
- `leo.application.algo07_star` coordinates ALGO02 through ALGO07 in order using
  narrow stage ports. Completed checkpoints are validated on resume. A failed
  stage or contested owner cannot be reported as scientific completion.
- `tools/run_algo07_star.py` binds the original stage adapters to pinned
  production workers. Each bounded invocation stops at a stage boundary when
  insufficient time remains; it never shortens a production stage's budget.
- `tools/inventory_algo07_star.py` retains every fast dataset member and reports
  unavailable evidence explicitly.
- `tools/compare_algo07_star_initial.py` compares initial-stage public exports:
  exact preparation bytes and the existing strict six-file numerical comparison.
  It explicitly does not claim full ALGO07 or cohort equivalence.

The coordinator and comparator use separate private roots. No services, queues,
production publications, QNAP paths or scientific policy have been modified.

## First fresh smoke pair

The first case is DS26-0002, selected as the first available member in the frozen
membership order, independently of its geographic error. Both private inputs
contain the same native observations. The candidate uses the coordinator; the
reference invokes the installed production watcher once against its own private
root. Both retain the original 1,200-second stage budget and single-threaded BLAS.

The pair's frozen inventory contains 71,484 files, including installed worker
sources, configurations, Python environments and 1,381 TLE snapshots. Snapshot
membership and file hashes are checked before and after execution. Newly added
archive snapshots invalidate this initial conservative fixture, even when they
would be irrelevant to the historical observation. The unchanged production
worker retains its causal-selection policy; inventorying a snapshot does not
permit the inference to use later elements.

The first candidate initial stage rebuilt 127 graph tracks (75 curved) from
4,211 native GLRT points, with 3,684 points assigned to the graph. It completed
in 134.80 seconds measured around the coordinator stage adapter, including its
validation. This is one stage on a shared host, not a speed benchmark.

The independent fresh production replay also completed. All 17 preparation
files were byte-identical, and the six scientific result files matched exactly
after the existing comparator validated the two result-hash links, explicit
input provenance paths and five top-level timing fields. Both calibration arms,
satellite/point ownership, gates, objectives and saved optimizer histories were
included. No numerical tolerance was used.

The reference watcher invocation took 210.63 seconds, versus 134.80 seconds
around the candidate stage adapter. These timing scopes differ and this is one
pair on a shared host. Do not interpret their ratio as an optimization speedup:
both use the same unchanged numerical workers. A controlled timing study follows
scientific qualification.

See [initial comparison receipt](initial-comparison.json),
[DS26 input inventory](input-inventory.json), and [runtime selection](runtimes.json).
The complete private fixture is at
`/srv/bulk/leo/research/algo07-star-20261104/iteration000`.
Its frozen manifest SHA-256 is
`a470b3f33614a1c5e8fabf8d87d08ee912ace55040e53ea46ad3cf2051b927df`.

Recovery stages ALGO03–07, all-eight-figure parity, fresh full-DS26 comparison and
runtime optimization remain outstanding. Initial-stage parity is not full ALGO07
parity or a DS26 cohort result.

## Tests and next work

The component test selection passes 22 tests, including the existing native
storage tests. New checks cover original-byte preservation, source-session
binding, destination protection, ordered incumbents, checkpoint validation,
failure/ownership handling, full cohort accounting, source/archive pin omissions
and detection of changed preparation evidence. Ruff passes for the new files.

Next, extend the first paired comparison through each recovery boundary and
publication, and qualify the coordinator on DS26 before
changing numerical calculations. For every optimization, identify the first
divergent stage if parity fails and retain the production implementation.

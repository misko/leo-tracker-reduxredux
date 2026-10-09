# Independent review of the generic recovery pilot

Preparation review only: at inspection, the inventory, tests and README exist;
the numerical driver is not yet available. This is not a launch or correctness
approval for unfinished code. No recording fits or objective evaluations were run.

## Baseline and cache binding

The standard [B7 runner](../../src/leo/application/hard60_b7.py) runs **three**
ordinary regional passes: baseline12.5, sep25 and sep50. A historical hard60
publication is not a matched B7 baseline, nor is a replay of only its selected
winner. Older source policies and B7 source documents must remain distinguished.
The pilot must materialize all three ordinary passes and their region inventories,
then run unchanged B7 joint stages. Preserve source/checkpoint availability and
new baseline failures explicitly.

`SharedPoints.key` changes only basin-independent point keys with the exact
`point:east:north` suffix to `b7-shared:point:east:north`. Calibration, association,
final and recovery receipts keep their original policy/pass keys. A generic cache
overlay must not strip prefixes or alias arbitrary historical keys to new B7 keys.
The production shared-point rule itself is not proof that an older policy has
identical observations, score, priors, timing bounds, bank ordering or bootstrap.

Permit reuse only after exact public binding and payload checks plus reconstructed
model identity. Track input AND analysis manifests, causal TLE/snapshot, prior and
score signature, observation ordering, bank order, bootstrap and physical fit
options. Objective agreement alone does not prove identical models. A mismatch
must recompute under the new baseline namespace or fail explicitly; never silently
accept an alias. Local overlay writes stay in the report directory through narrow
checkpoint ports, without mutating production receipts or constructing private paths.

## Recovery eligibility and candidate preservation

The inventory correctly keeps sep50-only member050 and does not gate by grid
spacing or reference error. Runtime `regional_triggers` enumerates ordinary
calibration failures across the reproduced regional passes and excludes recursive
recovery of recovery regions. This covers newly discovered baseline failures,
rather than limiting the operational rule to the initial metadata list.

Deduplication must reflect an identical physical model/start, not merely equal
coordinates or a historical failure key. Retain all contributing passes. Current
inventory hashes coarse/bootstrap content and score identity, but the numerical
caller remains responsible for analysis/observation/bank binding verification.
Spacing is not present in the runtime dedup identity: if identical model/point
receipts occur at different spacings, explicitly record all spacings and define
which unchanged local-final radius applies before freezing. Do not silently choose
the first insertion order when radius can affect operational constraints.

Independent convergence, not the optimizer success flag, determines whether
polish is needed. The direct prefit refinement and freshly rebuilt receiver
correction/postfit must preserve the original physical position/bounds and budget.
No historical rescued timing vector/correction may substitute for ordinary starts.
Association is shared across c arms; both arms receive matched bank, observations,
priors and local-final budgets, including c=0 RF locks. Any failure retains the
ordinary baseline outcome and its full receipt.

Ordinary regions/finals remain candidates. Append recovered candidates to a copy;
do not mutate the baseline region inventory before its replay. Use existing
qualified model-score/calibration-penalty selection. B7 stage acceptance remains
unchanged, without selecting an earlier stage or region by reference accuracy.

## Bounded execution and evidence required

The parent proposes at most six500-second baseline slices and six500-second
candidate slices per member. Persist actual slice counts and distinguish expired,
deferred, failed and terminal stages. A cap reached before completion is a reported
coverage failure, not permission for additional slices, dropping the member or
declaring a partial baseline matched. Worker concurrency also needs a frozen cap.

Budget includes baseline completion, qualification, association, six matched
finals and candidate B7; per-stage budgets alone do not bound the whole job.
Large tangent dimensions must skip explicitly when the100-evaluation curvature
budget cannot accommodate a sweep. No unbounded cold-grid retries are implicit.

Before execution, synthetic actual-driver tests should demonstrate all three
passes, incompatible aliases rejected, ordinary candidate immutability, runtime
new-failure triggers, any-grid and sep50-only retention, local-radius derivation,
matched c coverage, exact budget/resume enforcement and failure continuation.
Freeze sources/native kernels/model inputs and publication provenance before fits.

Reports must show every pilot member and failure, exact/near ordinary replay
parity where an archived B7 source exists, and matched per-arm position/frequency
effects separately. These failure-triggered development members provide diagnostic
generalization evidence, not an unbiased population mean or unseen validation.
Closed reserves remain closed; known coordinates enter post-fit reports only.

## Final actual-code review

Reviewed the completed `run.py`, `overlay.py`, `freeze.py` and revised runtime
inventory after the preparation review. **No blocking issue found for freezing
this bounded research pilot.** Parent reports20 component/controller tests passing;
this independent review did not launch any fits.

The driver reconstructs input/analysis manifests, causal snapshot/evidence, prior
and exact bank ordering before constructing its compatible overlay. Source
compatibility checks current physical source digests, score and configuration.
The only explicitly excluded mismatch is the presentation-only
`application/regional_position_report.py`, recorded as a nonnumeric mismatch.
Old-hard60 aliasing is limited to current baseline configuration point keys into
`b7-shared` points; aliased payloads must contain coarse/bootstrap fits and their
saved objective is checked against the rebuilt model before reuse. Calibration,
recovery and final aliases are not generated. Existing exact-key receipts remain
conditional on the same verified compatible source.

All three baseline passes are explicit. Candidate starts from a deep copy of the
completed baseline regions, adds every runtime ordinary failure trigger, and uses
separate baseline/candidate B7 stage prefixes. Recovery identity now includes the
effective local-final radius and records all contributing spacings, resolving the
preparation deduplication concern. Shared association, both c arms, all ordinary
starts and existing boundary-roundoff corrections are retained and audited.

The immutable slice claim counts a started invocation even after a crash, binds
each claim to the protocol, and prevents more than six baseline or six candidate
slices. Candidate requires a terminal completed baseline; caps and failures preserve
available ordinary fallback. Plan enforces two workers/one thread and unchanged
B7 policy. Freeze binds all snapshot payload hashes and inherited numerical closure.

Residual limitations are explicit rather than blockers: stored coarse
`converged=true` is independently rechecked before use, but a newly failed check
records failure instead of attempting polish. This conservatively loses a possible
recovery; it cannot falsely qualify it. Exact source/model reconstruction should
make such flips rare, and the receipt will reveal them. Qualification has a bounded
evaluation count rather than a hard per-call wall timer, so realized slice runtimes
must still be reported. Research pilot success would not by itself justify default
deployment or a population-wide accuracy claim.

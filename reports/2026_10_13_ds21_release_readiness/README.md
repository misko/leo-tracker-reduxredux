# Full DS21 release readiness: metadata only

The primary eight-channel corpus has potential input artifacts for all 54
members: 53 original bound tracking snapshots are present, and DS21-065 has a
separate completed preparation-only export. This does **not** establish model
readiness or accuracy. The historical metadata audit below recorded preparation
receipts for all 34 fast development members and five complete discovery/proposal
pairs. Subsequent development work is summarized separately; the audit's original
counts and receipt remain unchanged. Locked inference remains unopened.

Subsequent numerical work completed the [DS21-007 fitted-only proposal chain](PROPOSALS_007_RESULTS.md).
The subsequent [DS21-009 initialization](PROPOSALS_009_RESULTS.md) also completed.
The subsequent [DS21-011 initialization](PROPOSALS_011_RESULTS.md) completed too.
The subsequent [DS21-013 initialization](PROPOSALS_013_RESULTS.md) completed as well.
There are now nine complete development proposal sets, with 25 still requiring
initialization. The [DS21-009 model-seed diagnostic](PROJECTION_009_DIAGNOSTIC.md)
isolates a Model B calibration projection failure before any final location fits.
The [v2 initialization](INITIALIZATION_009_V2_RESULTS.md) now succeeds with two
independently verified physical source transfers. Its first sequential path
saved three stationary fits before a descriptive metadata-validation mismatch;
a separate reader recovered those same fits without refitting or source edits.
The [completed fitted-only three-model comparison](THREE_MODEL_009_RESULTS.md)
now has 54 stationary fits and all 12 outcomes sealed before seven error rows:
A/all **0.658299 km**, B/all/low/high **5.327196 / 0.790354 / 0.772167 km**, and
C/all/low/high **1.595252 / 4.547625 / 1.758365 km**. None is below 0.5 km.
B's all/high winners reach timing constraints while their positions stay inside
the original geographic disks. Half views share discovery and initialization;
reference error does not select a start or algorithm. DS21-011's final model
comparison has started without an accuracy result; DS21-013's final models have
not started. The [independent 009 audit](THREE_MODEL_009_AUDIT.json) passes, and
locked inference remains unopened.
The metadata-only inventory below is retained as the historical audit.

The subsequent [DS21-007 joint baseline](JOINT_007_RESULTS.md) completed all
18 fits, all stationary: CH1–8 / CH1–4 / CH5–8 errors are 3.524 / 3.738 / 4.325 km.
Combining bands helped this case, but none reached 0.5 km. Locked inference
remains unopened.

The [source-bound metadata receipt](metadata-v1.json) records all 108 original
members, file availability, development-only preparation/discovery/proposal
metadata and the DS21-065 preparation overlay. It binds 64 parsed metadata
documents. Membership SHA-256 remains
`a701553b01ae023ea8b68b4ea6757fc7a75dc9ac7c754118b69bd8bce6003c39`.
No membership, role, eligibility or denominator changed.

## Inventory and availability

| Original stratum | Development | Evaluation | Bound tracking snapshots | Separate overlay |
|---|---:|---:|---:|---:|
| Fast, acquired CH1–8 | 34 | 20 | 53, all local files present | DS21-065: one export, not adopted into membership |
| Adaptive, acquired CH1–4 | 35 | 19 | 0 in this membership | None inspected |
| Total | 69 | 39 | 53 | One preparation-only artifact |

The original split contains 29 UTC-hour acquisition groups: 19 development and
10 evaluation, randomized with seed 20261013. The adaptive members are the
four-channel secondary corpus; they do not supply acquired CH5–8. No bound
tracking snapshot is recorded for any of those 54 members. This audit does not
assert that their raw recordings or detector products are absent; those stores
were not searched.

The primary CH1–8 denominator remains 54, including all 20 evaluation members and
DS21-065. The historical membership's acceptance text says below 1 km. The latest
user target is **below 0.5 km for every eligible CH1–8 member, fitted c only**;
that stricter target belongs in a new versioned model-release protocol. The old
membership must not be rewritten, and unavailable or failed members cannot be
removed from the target denominator.

For locked members, the audit uses original recorded input path/hash metadata and
local file status only. Tracking payloads are not opened or newly hashed, so
presence is not a fresh byte-integrity or preparation check. The separately
committed DS21-065 preparation completion/exclusion metadata is inspected only
to identify its exported input artifact. No locked positioning/discovery/model
terminal, candidate measurements, reference or error join is read.

## Development artifacts

All 34 fast development labels have an existing census receipt reporting
`prepared` with all, low and high views. These are existing preparation records;
no source was prepared again in this audit.

| Development case with complete discovery/proposal metadata | Causal full-bank count | Included common-bank count | Saved proposals per view |
|---|---:|---:|---:|
| DS21-001 | 849 | 39 | 6 |
| DS21-003 | 896 | 37 | 6 |
| DS21-005 | 928 | 44 | 6 |
| DS21-023 | 857 | 33 | 6 |
| DS21-039 | 836 | 43 | 6 |

These five discovery terminals report available three-start discovery and bind
their protocol bytes. Their protocols match original input and membership
hashes. Each complete six-proposal terminal binds its protocol and the common
discovery parent, with all/low/high seed files present. Full-bank arrays and
physical seed states are not interpreted or replayed. Current numerical/source
compatibility still needs the eventual release's normal validation gates.

The remaining 29 development labels have no discovery/proposal pair in these
namespaces: 007, 009, 011, 013, 025, 027, 029, 031, 033, 035, 037, 041, 043, 045,
051, 053, 055, 057, 059, 061, 071, 073, 075, 077, 079, 081, 083, 085 and 087
(all with prefix `DS21-`). No evaluation discovery/proposal directory or terminal
is inspected to make these counts.

## Lean development preparation commands

This section retains the historical audit's proposed commands. The current
fitted-only path uses `tools/ds21_fitted_initialization.py` with one explicit
case/stage/slice, followed by the [v2 model protocol](THREE_MODEL_EXPANSION_V2_PROTOCOL.md)
and `tools/ds21_fitted_model_receipts.py` for continuation and aggregate review.
It does not invoke the old two-arm orchestration. Current proposal coverage is
nine sets, leaving 25 initializations; the historical 29-label inventory below
is not the current work count.

After the coordinator pins the initialization source/input recipe, start with one
missing development label, for example DS21-007, through the existing discovery
port. From `/home/mouse9911/gits/leo-ds21-three-models`, the bounded invocation is:

```bash
sudo -n env PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout --signal=TERM --kill-after=5s 495s \
  /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python \
  -m ds21_common discover --label DS21-007
```

This is a proposed command, not an execution performed by this audit. It uses
the existing development role guard, original source verification, causal bank
port and discovery checkpoints. One slice handles **one label**, with termination
at 495 seconds and forced termination by 500 seconds. Inspect the process and
checkpoint/terminal before authorizing another slice on the same label. A
checkpoint is partial progress, not completion; a first 500-second slice does not
guarantee a completed cache. Keep one heavy process and one BLAS thread. The 29
missing labels are a work inventory, not one unattended batch command.

The next existing composition, `python -m ds21_shared_proposals --label DS21-007`,
is **not yet runnable for a new label**: it requires discovery plus sealed Model
B-v3 candidate-pool/hybrid and cold-control parents. It does not manufacture six
starts from census metadata. The future fitted-only initialization recipe must
declare how those physical proposals are produced without rerunning historical
two-arm fits, or explicitly choose a different matched proposal recipe before
comparison. That is a release decision; this audit produces no banks or seeds.

## DS21-065 input overlay

Original membership still records `input: null` for this evaluation member.
The preparation-only export is a distinct research artifact with recorded input
SHA-256 `2b6a68f5458a651f2faf6495f8cafc19e57b49a63711087c8b7ca327934ce0c5`
and sidecar SHA-256
`e8856bd1c7db0b3e44967b6072c1a0ff01b25672f6a5f2ee774d0cb7b1aa6d8b`.
Both bound local files are present. Their payloads are not opened by this audit.

The committed metadata reports 6,757 original windows, 6,752 valid, five excluded
for recorded acquisition invalidity, 3,743 retained processed windows, 3,009
existing fast-score skips and 7,486 receiver probes. The export made zero
detector calls, localization fits or membership changes. Original timing and
visit/counter gaps remain part of its declared policy. Probe count is not a
passing-candidate, usable-track or localization-success count.

A model release must explicitly bind this overlay's original membership/raw
authority, preparation protocol, input hash and exclusion sidecar. It cannot
silently fill the old membership's null field or treat successful export as
successful inference. Downstream preparation on this qualified input remains
unknown in this audit; the default original source loader rejects the null input.

## Blockers before full matched fitted-only inference

1. **Select and freeze the model policy after the current development controls.**
   This metadata audit selects no calibration, bank, association, weighting or
   optimizer policy. The original common loaders/discovery entrypoints reject
   evaluation roles; that guard must remain intact. Locked execution needs an
   explicit frozen release composition, not a development-helper bypass.
2. **Complete missing development initialization under declared bounded slices.**
   Twenty-nine prepared development cases lack the corresponding discovery/bank/
   proposal artifacts. Input, causal TLE policy, ordering, original native RF/time,
   initialization and training selector must be bound before each numerical stage.
   Existing cached artifacts are not proof of a compatible future model state.
3. **Resolve qualified inputs explicitly.** Adopt DS21-065 only through the
   versioned preparation-overlay binding above; retain its historical unavailable
   result. If a full 108-member secondary analysis is intended, the 54 adaptive
   members additionally need an authorized input-export/re-analysis plan through
   existing ports. No such work is attempted here.
4. **Use a fitted-only release and immutable per-case attempts.** Preserve matched
   observations/banks/physical starts/priors and declared budgets across compared
   variants. Use at most 500 seconds per slice, one heavy process and BLAS thread
   limits. Checkpoints, failed preparations/fits and interrupted attempts must
   remain visible; do not automatically spend another slice or exclude failures.
   Do not invoke a historical two-arm runner expecting it to honor the newer
   fitted-only instruction.
5. **Keep evaluation causal.** Predeclare training-only state selection, source
   checks and error scoring before opening the 20 locked primary members. Seal
   inference before reference joins. Report frequency/likelihood effects separately
   from position accuracy, retain all 54 primary members, and use the new strict
   0.5 km threshold without retuning to locked errors.

No banks, seeds, fits, detector products, RF collections or locked numerical
evaluations were generated. No QNAP mutation or broader corpus scan occurred.

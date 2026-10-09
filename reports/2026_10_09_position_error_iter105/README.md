# Generic five-member calibration recovery pilot — preparation

Select every newer-development member with an ordinary retained calibration
failure in [iteration104's explicit bindings](../2026_10_09_position_error_iter104/source_bindings.json).
This yields006,026,046,050,051 from failure metadata, never position error.
There are seven separation-pass entries and five distinct input/model/point
receipts. Member050 must be included even though its failed region is retained
only in the sep50 pass; `retained_baseline=false` is not an exclusion criterion.
Do not filter by grid spacing: the observed failures include5,10 and20km cells.

## Source audit and required baseline

Members006/026/046 currently have older hard60 publications. Members050/051 have
operational B7 publications. All need a freshly verified matched B7 baseline for
this pilot; old hard60 accuracy is not a B7 baseline. Across the complete newer
development inventory,39 of45 have older hard60 publications; this pilot does
not silently promote those39 to B7 or evaluate their quality from old errors.

Use the source's public status port to preserve its document and exact input,
analysis, checkpoint binding, causal TLE and configuration identities. Read the
explicit coarse/bootstrap semantic keys through `RegionalCheckpointStore.get`
and verify the canonical payload/bootstrap digests recorded in104. Never build
private checkpoint paths. Fully reconstruct observation ordering, prior/score,
candidate-bank ordering and coarse objectives before any retry is enabled.

Existing single-case95 loading validates exactly those identities, but requires
a supplied source-specific document and selected coarse receipt. It can be used
through a generic adapter; its ac11 file paths and baseline extractor cannot be
used as a cohort input authority. Newer104 metadata supplies enough public port
identity to prepare this adapter, not proof that every model already reconstructs.

## Matched ordinary pipeline and candidate

1. Materialize a read-only snapshot of usable existing public checkpoints into
   the research artifact. Bind every payload hash before numerical execution.
   Local overlay writes must remain confined to the new report directory.
2. Reproduce all three standard B7 regional separation passes under current
   frozen policy. Reuse only verified compatible coarse/other checkpoints; run
   missing ordinary stages with unchanged budgets. Then run the ordinary B7
   joint stages as the baseline. This is required for the three older hard60
   members; merely applying B7 to their old single regional winner is insufficient.
3. Enumerate every ordinary retained calibration failure in those baseline
   regions, at any grid spacing. Preserve the original regions. Deduplicate by
   input, reconstructed prior/score, bank, point and exact coarse/bootstrap
   content; retain all contributing separation-pass names. Any new failure
   exposed by completing missing B7 passes follows the same rule and is reported.
4. If the original coarse fit is independently unqualified, attempt immutable102
   direct qualification once, with its100-evaluation/two-round cap. Otherwise
   independently verify and retain that qualified coarse fit. Never use optimizer
   success alone. Missing inputs, invalid constraints, large dimension, failed
   curvature and failed qualification stay explicit.
5. From that prefit compute a fresh receiver correction and bounded recovery
   postfit as in103; allow one102 qualification only on independent postfit
   failure. No historical rescued seed/correction is substituted.
6. Shared association and matched c finals use unchanged budgets and ordinary
   region-local bounds. In particular, derive radius from cell spacing and the
   configured minimum, not ac11's hardcoded25km. Preserve all ordinary winners,
   rank by existing operational score policy, then replay candidate B7.

The initial metadata inventory is frozen separately from any new ordinary
failures discovered during baseline completion. Coverage must show both. No
pilot member disappears because of an input/model/optimizer failure.

## Frozen-budget proposal approved for preparation

At most nine unique ordinary retained regions per member (three passes of three
basins), with no recursive recovery of previously generated recovery regions.
For each triggered region: at most100 prefit polish evaluations, one20s/600
bounded postfit, at most100 postfit polish evaluations, one60s association and
six20s/600 finals. Use the existing B7 per-stage90s/600 budgets and local500s
checkpointed slices. Baseline reconstruction and missing ordinary stages are
additional compute and must be quantified from checkpoint availability first.
The approved cap is six baseline slices plus six candidate slices per case,
each500s, with at most two single-thread workers. An immutable started receipt
consumes its slice even after a crash; the cap cannot reset on restart. Exhaustion
is an explicit terminal result with the baseline fallback when available. No
standard point budget, fit budget or ordinary candidate is reduced to fit the cap.

The concrete driver is `run.py --label LABEL --phase baseline|candidate`; the
parent-owned controller resumes each phase from immutable local checkpoints.
`source_snapshot.py` reads public snapshots, `overlay.py` verifies exact keys and
payloads with local-only writes, and `freeze.py` binds all source values and
policy. Historical cache compatibility is independently checked after reconstructing
input/bank identities; missing or changed source/config identities disable reuse.
One explicitly frozen compatibility rule permits old hard60 baseline
`config:point` to serve a B7 `b7-shared:point`: exact current run configuration
and score, identical verified input/evidence/prior/bank ordering, matching
historical physical source hashes, and a recomputed exact saved coarse objective
are all mandatory. Calibration, recovery and final keys are never aliased.
Every successful coarse alias records its source key/payload and objective check.
The only source-hash exclusion is `application/regional_position_report.py`,
which renders after inference and is not imported by numerical runners. Its
historical mismatch is still recorded. No other source mismatch is ignored.

Region deduplication includes the derived local radius;40km and5km cells that
yield different final constraints remain separate, while all contributing
spacings are recorded. The standard hard60 boundary-roundoff rule is preserved:
only position overshoot within1e-6km is moved inward by1e-8km. Every candidate
final records original/effective seeds and the resulting position delta.

Synthetic tests cover exact-key/hash gates, persistent caps, all three unchanged
baseline passes, separate candidate B7, stale baseline rejection, sep50-only
retention, distinct constraint radii, missing receipts and nonmutation. No
numerical execution before parent freeze/publication. No production source
change, RF collection, reserve access or deployment.

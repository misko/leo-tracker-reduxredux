# Independent sidecar workspace review

Date: 2026-09-30

Verdict: **no source-level correctness or ownership blocker found** in the
isolated sidecar variant. Production promotion remains unqualified pending the
sidecar-specific execution checks listed below.

## Frozen inputs

- `source/sidecar.cpp` —
  `f2fb20b646287e4ef0392131a48e3dff337b14db69ef09564eae1b0439b659bc`
- `test_sidecar_workspace.cpp` —
  `a9115b6c1948a69881e49d42a5ea8d923e80bbccec589839bdaca773f06cab18`
- `build.sh` —
  `97ecd2ec051c01c8340d29ca794197cb62041089a46fa50b42ed8657cbbed045`
- dense-ID-in-`Point` comparison source `source/candidate.cpp` —
  `ee3af274c7ff58593e4e0cbc94455034738a075e12ddfa8bda43bb634f8298bf`
- source-view baseline `source/view.cpp` —
  `b56a93a22fb9923b6b7dc24d43fd982cb722bd1dafd2e432d802c914f61d326d`

## Review

`bind_source_groups` runs after the existing canonical lane sort. It emits one
integer group index for every candidate in that sorted vector. `reconstruct_lane`
then creates `Point` entries in the same loop order and moves the complete index
vector into its local `SourceWorkspace`. Every raw and refined index is a point
index, so `workspace.point_group_indexes[index]` has the same meaning as the
candidate variant's `points[index].source_group_index`. Neither vector is
reordered after binding.

The sidecar owns `size_t` values and retains no candidate or fallback-key view.
The temporary string-view map used while binding has the same reviewed lifetime
as the dense candidate: candidate strings outlive reconstruction, fallback
storage reserves the full candidate count before retaining its first view, and
no view escapes `bind_source_groups`. Moving the completed integer vector into
the workspace is therefore independent of those temporary lifetimes. Explicit
and synthesized `time:<ns>` collisions, embedded-NUL keys, lexical group order,
and strict rank/tie behavior remain unchanged.

The workspace is constructed inside each `reconstruct_lane` invocation. It owns
its immutable point-to-group vector and mutable best/touched/result scratch, so
parallel lane callbacks do not share new state. The synchronous lane executor
still returns each lane's final tracks through the existing per-index result
slot. Cached and stateless reconstructions both reach the same lane-local
function.

`one_per_source` clears its touched and result vectors, records a group only on
the sentinel-to-index transition, restores every touched best slot before its
final sort, and returns workspace result storage. Both production uses pass
that reference immediately to `split_contiguous`, which copies indexes into an
owned vector of vectors before nested refinement or the next peak reuses the
workspace. The focused test retains a split result across another selection and
checks every best slot is reset.

The focused test compares against the owning-string control for explicit and
fallback collisions, empty/subset/disjoint/repeated selections, duplicate
indexes, embedded NUL and long keys, tied ranks, 10,000 randomized cases in
both input orders, and two independent threaded lane workspaces. Its
`sizeof(Point)==32` assertion binds the intended layout on the tested ABI. The
sidecar is also byte-identical to the frozen dense candidate across all 60
causal prefixes (`sidecar-prefix-parity.json` SHA-256
`f05e18a4a1d830b3858a7bf40d2a12a6de84a56a3c2c885f111b56c59cc43b48`).
The focused host and ASAN/UBSAN runs pass with empty sanitizer stderr.

## Promotion evidence still required

The retained full ASAN/UBSAN reconstruction belongs to the earlier dense
candidate, while the sidecar currently has focused sanitizer coverage only.
Before production promotion, run the complete 11,747-candidate reconstruction
under the sidecar sanitizer build and retain its exact output and empty stderr.

The sidecar-focused two-thread test proves independent workspaces but does not
invoke the public `LaneExecution` dispatcher. Before promotion, build and run
the existing lane-execution component test against the frozen sidecar source,
including its duplicate/missing/out-of-range/failure-recovery cases; a TSAN run
should bind the actual concurrent lane path. This is an evidence gap rather
than a source finding because all added state is visibly lane-local.

The ARM binaries are cross-built but were not physically run at review time.
The root-owned focused run and bounded candidate/sidecar ABBA must finish with
exact scientific output before any ARM performance or promotion claim. A later
production change would also require the ordinary component suite and coherent
application rebuild; this report makes no such promotion, hardware, IQ, or RF
claim.

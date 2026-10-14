# Fixed-point discovery selector control

This prespecified metadata-only control compares exactly two proposal selectors
on the same completed DS21-039 coverage search. It isolates the ordering and
separation effect documented in [the coverage result](DISCOVERY_COVERAGE_039_RESULTS.md).
The original low-first selector skipped the high/all minimum because it lay
8.839 km from the low winner under the fixed 12.5 km separation rule. No new
grid, timing prior, calibration parameter or numerical fit is introduced.

## Fixed comparison

- Parent: the completed `discovery-coverage-v1-absolute-source` DS21-039 search,
  with its genuine legacy input/source/bank authority and bounded qualification.
  All 100 saved point results and their original fitted-c training certificates
  remain fixed. Optional reference-error files are neither bound as selection
  inputs nor decoded.
- Original condition: stationary minima in **low, high, all** order.
- Only alternative: stationary minima in **all, low, high** order. This prioritizes
  the combined-view training objective; no ordering is selected from reference
  error and no third order is tried.
- Both conditions retain own-view objective ranking, east/north coordinate tie
  breaks, the all-view stationary score fallback, original 12.5 km separation,
  at most three proposals, and the sorted union of selected catalogue numbers.
  No observation, objective, convergence threshold or candidate identity changes.
- The original condition must reproduce the parent's full selected row sequence
  exactly, not merely the same centers or score totals. Minima with no eligible
  fit are unavailable; nonstationary results never donate a minimum or fallback.

The pure component is
`src/leo/analysis/research/discovery_proposal_selection.py`. Its narrow API is
`select_proposals(rows, *, view_order)`, accepting saved rows keyed by original
point identity. It returns selected point summaries, original training objectives,
catalogue unions and all three minimum decisions. Skipped minima record whether
they duplicate an already selected point or lie within separation, together with
every blocking point and distance. Exact 12.5 km separation remains eligible.
The component reads no files and imports no application, CLI or storage code.

## Authority and execution

`tools/ds21_discovery_selector_control.py` provides `freeze(directory,
parent_directory=...)`, `run(directory)` and `read_terminal(directory)`. All paths
resolve to absolute paths before binding; it does not reproduce the older
relative-key defect. Its genuine parent reader validates the original coverage
source archives, input/bank/qualification bindings, complete numbered slice,
100 point triplets, hierarchy and original selector. The new protocol binds that
parent inventory and archives its own source closure, including the new component
and runner. The frozen historical sources remain unchanged. Existing-protocol
validation precedes any archive mutation, so a missing archive is not restored.

Freeze validates original-order closure without producing the alternative
condition. One explicit metadata-only run computes both fixed conditions under
**60 seconds internal / 75 seconds TERM / 80 seconds KILL**, including final
parent/source checks. A durable launch precedes validation/computation; completion
binds the immutable terminal. Failed or orphan attempts refuse continuation and
retry. Cached reads validate launch/termination, source/parent authority and the
entire recomputed pure selection inventory. There are **zero preparation,
propagation, prediction, objective, gradient or optimizer calls**. No held or
reference access is permitted, and this tool has no evaluation action.

The terminal reports both selected sequences, skipped minima and blockers,
training objectives and candidate unions, including additions/removals versus
the original condition. Changed candidate unions are an intended consequence of
the unchanged selection rule. No score is described as a common-support global
likelihood improvement. This control cannot establish frequency-model truth,
optimizer-disk coverage, localization accuracy or a sub-0.5 km result.

## Narrow downstream provider design — not implemented here

The existing generic and coverage initializer readers reject this genuine legacy
authority. A future qualified provider should accept **(sealed selector control,
literal condition)** and return the following narrow payload without relabeling
old receipts:

1. Original member/membership/census plus the completed DS21-039 qualification's
   prepared hashes, partition, time/RF/group frames, clock nodes and causal snapshot.
2. The same full 836-satellite bank, selected full point rows resolved from the
   condition's keys, catalogue-ordered candidate indices/union and three centers.
3. Its own condition/source/ancestor bindings. The selected rows are a new explicit
   provider result, not a replacement historical discovery terminal or generic
   case protocol. Reference artifacts remain excluded from authority.

A separately named stage facade can then reuse the original numerical
`operation`, `assemble`, `stage_proposals`, completed-call and slice validators
with explicit payload arguments. It needs its own qualified context/predecessor
reader rather than modifying frozen `read_case` or global module functions.
Each condition follows the exact original **shape → fresh shape bootstrap →
hybrid → fixed-pool cold bootstrap → ordered six physical proposals** chain.
Fresh bootstrap may expand from the full bank; cold uses the original fixed pool,
nearest donor and missing-satellite timing fallback. The six proposals remain
cold-0/1/2 then shape-low/high/all, with all 18 physical exports and original
closure checks. Original and all-first descendants stay in separate namespaces.

Matched stage caps remain nine shape fits and nine hybrid fits at 20 seconds/600
iterations (240/255/260-second slices); each nine-call bootstrap stage uses the
original 5-second caps within 90/105/110-second slices. Export remains separately
bounded. Full-bank/input/partition/priors/math/budgets match; the selected geography
and induced candidate pools may differ by design. The historical 43-candidate
native parent is not substituted for either condition's derived union.

A final separately qualified model consumer can reuse original model factories,
v2 strict-first seed projection and proof-gated exact-source fallback, once-only
all-training receiver lifts, and the literal high-stage metadata reader. Each
condition requires its own 12 A/B/C outcomes and at most 54 optimizer calls:
six dependent A paths, plus six starts for each B/C view, with fitted c throughout.
A's dependent failure rules and independent B/C views remain unchanged. Original
20-second/600-iteration/25 km fit domains and full outcome/reference gates apply;
raw failures remain visible with no automatic retry. A matched two-condition
comparison could require 108 calls, not reuse the unrelated historical final fit.

These downstream adapters and numerical slices require separate qualification and
root review before execution. This protocol authorizes only the saved-point
selector control; it does not claim that reordering will improve localization.

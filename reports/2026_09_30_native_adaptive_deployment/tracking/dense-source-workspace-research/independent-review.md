# Independent dense source-workspace review

Date: 2026-09-30

Verdict: **no correctness or lifecycle blocker found** in the isolated research
candidate. This review does not promote the candidate or qualify its pending ARM
performance result.

## Reviewed closure

- `source/candidate.cpp` —
  `ee3af274c7ff58593e4e0cbc94455034738a075e12ddfa8bda43bb634f8298bf`
- source-view baseline `source/view.cpp` and `source/control.cpp` —
  `b56a93a22fb9923b6b7dc24d43fd982cb722bd1dafd2e432d802c914f61d326d`
- `source/tracking.hpp` —
  `943f00942b43d5e9e7b155d0428d8d2aa96153f52eb607083a13b86ab57865ba`
- focused test `test_dense_source_workspace.cpp` —
  `aa6302792514ccb297f96326b15385a2f6c7267d111058c70a44f4e830acd715`

The reviewed evidence includes the 60-prefix byte-parity receipt
`prefix-parity.json`, SHA-256
`278ba3d74f666488aa4efe58942886ffce458a894d48ffb4c80fbc8814745cd0`,
and the physical focused-test log, SHA-256
`9d73ec85c4ca41252c17d8ae8e0a249c3b69fb75358cf0e08c913a33f777e10f`.

## Findings

The dense binding preserves the baseline grouping relation. Explicit source IDs
borrow immutable candidate strings. Synthesized `time:<ns>` strings are stored
in a vector that reserves the complete candidate count before retaining its
first view. The ordered map and point-key views are destroyed before that owned
fallback storage. An explicit `time:<ns>` ID and the corresponding synthesized
fallback therefore still collide, and `std::string_view` ordering preserves the
baseline string ordering, including embedded NUL bytes. The returned
`SourceGroups` contains only integer values; no borrowed view escapes binding.

Dense IDs are assigned in lexical source-key order. A selection uses the same
strict rank tuple as the baseline: negative weight, absolute residual, then
candidate ID. Equal ranks retain the first input occurrence in both versions.
Duplicate indexes consequently do not add duplicate touched groups. Sorting the
touched dense IDs reproduces the old ordered-map enumeration, and the unchanged
final time/candidate sort preserves observable ordering. Empty, subset,
disjoint, repeated, fallback-collision, embedded-NUL, long-key, and tied-rank
cases are covered by the focused differential test.

`one_per_source` returns a reference to workspace result storage, but each
production call passes that reference directly to `split_contiguous`.
`split_contiguous` copies the indexes into an owned vector of vectors before it
returns. The outer raw segments remain owned while an inner refined selection
reuses the workspace. The focused test also retains a split result across an
explicit subsequent workspace call. No later refinement or peak retains a
workspace alias.

Reset behavior is complete on every normal return. The touched and result
vectors reserve `group_count`, at most one touched entry is recorded per group,
and every touched best-index slot is restored to the sentinel before the final
result sort. Thus the hot selection path performs no expected allocation after
workspace construction. Binding allocations occur in local objects before the
points and workspace become visible. Later fit or segment exceptions occur
after selection has reset its slots. The private helper still assumes validated
point indexes and a workspace created from the same lane binding; production
constructs both together in `reconstruct_lane`, so this does not add a public
precondition.

Each `reconstruct_lane` invocation owns its `SourceGroups`, points, and
`SourceWorkspace`. Lane-execution jobs share only immutable candidates and
write their existing per-index result slots. The new workspace has no static or
cross-lane state. The two-thread focused case checks independent repeated
workspaces; the dispatcher and cached-bin synchronization are unchanged by the
candidate diff.

## Evidence assessment

The focused host and ASAN/UBSAN logs both report 20,000 differential selections,
reset checks, boundary cases, owned split lifetime, and lane isolation passing;
their stderr logs are empty. The retained full sanitizer stderr is also empty.
All 60 causal prefixes, including the complete 11,747-candidate output, are
byte-identical to the source-view baseline. The physical focused test passed in
3.920307765 seconds wall time with exit code zero.

These results support semantic and ownership equivalence for the isolated
candidate. They do not establish the pending ARM ABBA performance result, make
a production-promotion claim, or extend application, detector, IQ, or RF
qualification.

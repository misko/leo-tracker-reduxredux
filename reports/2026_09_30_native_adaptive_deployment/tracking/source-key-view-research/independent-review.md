# Independent source-key view review

Verdict: **no blocker found**. This review covers the isolated research change
only. It does not promote the change into production or make an ARM performance
claim.

## Reviewed material

- Production control `native/adaptive/tracking/tracking.cpp`:
  `eeefee63d956a1aeaeb88ee0b2f2560876107a9f5f79e3b5aa28616036d7b96c`.
- Research `source/tracking.cpp`:
  `b56a93a22fb9923b6b7dc24d43fd982cb722bd1dafd2e432d802c914f61d326d`.
- Strengthened report-local `test_source_keys.cpp`:
  `80c5a5ed95d2a3c8106f748898a8b44284ee51b4c9073ddc4c50045be74f2ad4`.
- Existing full DS9 output and all 60 causal-prefix comparisons documented in
  `README.md` and `prefix-parity.json`.

The source diff is limited to adding `<string_view>` and changing the local
`one_per_source` key map from owning `std::string` keys to borrowed
`std::string_view` keys, while retaining owned synthesized fallback strings.

## Findings

- Explicit keys borrow `Candidate::source_group_id` strings. Those candidates
  remain immutable and alive for the complete synchronous lane reconstruction.
- Fallback storage reserves `indexes.size()` before its first element is
  retained, so later pushes cannot relocate a fallback string. `best` is
  declared after `fallback_keys`, which ensures that the map and its views are
  destroyed before fallback storage.
- An explicit key such as `time:7` and the synthesized fallback for timestamp 7
  compare identically to the owning-string implementation, regardless of which
  is encountered first. Embedded NULs also retain length-aware lexical
  comparison.
- Rank comparison and final output ordering are unchanged. Replacing a map
  value never replaces or invalidates its key view.
- Allocation or comparison exceptions unwind local state only. They cannot
  leave cache or result state partially mutated.
- Every lane owns its map and fallback vector. Parallel lane callbacks share
  only immutable candidates. This is safe under the existing borrowed,
  synchronous `LaneExecution` contract; an executor returning before its jobs
  finish would already violate that contract independently of this change.

The focused test now contains deterministic duplicate-index coverage and a
late-first-fallback case where explicit views are already stored before the
fallback vector reserves. That case also forces an explicit/fallback `time:`
collision. The pre-existing 10,000 seeded cases remain unchanged.

## Focused qualification

Exact build and run commands are retained in `focused-review/host-command.txt`
and `focused-review/sanitize-command.txt`. Both use the report-local research
source and production headers. Compiler identity is retained in
`focused-review/compiler-version.txt`.

- Normal host: pass, 0.06 seconds wall, 4,216 KiB peak RSS. Binary SHA-256:
  `b1fb2e25ddc80a65e1f18f58b8ff7f46159d9e9d61426b4f29259fe3f57a2a95`.
- ASAN/UBSAN: pass, 1.20 seconds wall, 246,184 KiB peak RSS, empty sanitizer
  stderr. Binary SHA-256:
  `cb0a2bed5e20f50462a311626f21b2fc4ce9c60a4bb50c9c33c57caea3d3831c`.

The first normal compile failed before producing a binary because the shared
`/tmp` user quota was exhausted. Its log is preserved as
`focused-review/host-build-initial-tmp-quota-failure.log`. Both qualifying
builds then used the recorded task-specific compiler `TMPDIR` under `/var/tmp`.
The only successful-build diagnostic is the same internal-linkage warning in
both modes caused by directly including the research `tracking.cpp`; there are
no runtime or sanitizer diagnostics.

# Final immutable publication access

The recorded composition needs the actual published track memberships,
supports and partitions for comparison. `Analysis::final_published_snapshot()`
now returns the existing immutable publication only after
`finish_after_rf_stopped()` completes successfully and joins the analysis
worker. It does not trigger a publication, retain an additional history, or
change inference. A pinned search may refer to an older snapshot; the accessor
explicitly returns the latest publication, not the search's input.

`Session::current_snapshot()` forwards the existing Coordinator accessor and
is analysis-owner-only. The Analysis wrapper guards access with its lifecycle
mutex and a completion flag set after the successful join/final processing.

The complete component-owned `test_live.cpp` suite passes in host and
ASAN/UBSAN builds. Added cases reject access before finish, during active
analysis, and after failed finish; verify the final generation, observation
count and nonempty tracks; and keep the returned snapshot alive after Analysis
destruction. Existing lifecycle, source timing, failure and search tests also
pass. The same suite also passes on physical PLUTO+ ARM; its measurement is in
`physical.time.json`. No application deployment or RF collection is part of
this change.

Builds use `LEO_LIVE_CORE_ONLY`, the same six application/ingest/timing/runtime
source files as `application/build-live.sh`, and the matching host/sanitizer
online archives retained in `../sidecar-workspace-release-v1/build-online-*`.
They compile C++17 with `-O1 -g -fno-fast-math -ffp-contract=off -pthread`,
strict warnings, and sanitizer flags in the sanitizer variant. Artifacts and
source/library hashes are retained alongside this report.

# Execution status

The full193 protocol was published to remote main at
`96a85799e7f91a9628f7f99fbc556b0d8b66d993` before recording reconstruction.
Research source commit: `b5fd9eb4a`.

Protocol file SHA256:
`41b1acba455805344d17f5ecf92b0827e645defd5f5ffaafb69da86f71c3f0f6`.
Canonical protocol digest:
`sha256:b5fb8cbbd6c950d85ef0ae21912eff286a052c430e84b037740358116857db6c`.

All 193 clean input bindings passed metadata checks. The frozen membership is
DS16 63, DS17 51, DS18 34, and consumed newer development 45. DS18-034 retains
its original null publication-manifest field; later analysis input, evidence,
bank and observation identities remain strictly bound. No member was omitted.
The pinned-runtime test suite passed **25 tests**. The source closure contains
1598 files, input closure 196 files and runtime closure 2340 files.

Batch zero was launched on two single-thread workers, using the immutable
47e executable. Root owns shard zero (session 17877), processing DS16-001 then
DS18-001. The debug_search_gap agent owns shard one (session 95011), processing
DS17-001 then POST18-NEWER-20261009-001. Both initial search claims were verified.
These session identifiers are monitoring information, not restart instructions.
Do not duplicate a claimed worker or retry an orphan.

Both batch-zero controllers subsequently exited successfully. All twelve
member phases completed. The checkpoint and verified move to local bulk are
published in [PROGRESS.md](PROGRESS.md). The original `results` path is now a
symlink; retain that path spelling for every future invocation.

**Current work: batch one is running.** Root owns shard zero, session **84385**;
debug_search_gap owns shard one, session **10020**, controller PID1722725.
Both initial DS16-002/DS17-002 search claims were verified through the symlink.
This batch contains the fixed sixteen members numbered002–005 in each dataset
group. Four cohort members are complete, sixteen are assigned to this running
batch, and173 await later batches. Do not restart claimed workers; require both
terminal batch-one controllers before admitting batch two.

No geographic evaluation has run; no position-error claim is available for this comparison. Production
B7 and the historical full193 fitted mean of 1.254810 km remain unchanged.

Scientific source, policy and inputs are frozen. Later evaluation/report code
must be sealed separately; publish position plots only after the full cohort's
selections and failures have terminated. This narrative status file is outside
the numerical input closure.

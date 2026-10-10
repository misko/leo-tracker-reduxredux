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

Batch one subsequently finished with both terminal shard receipts and all
48 member phases complete. Its timing and coverage are documented in
[PROGRESS.md](PROGRESS.md) and [CHECKPOINT_1.json](CHECKPOINT_1.json).

Batch two also finished with both terminal shard receipts and all 48 member
phases complete. Root's shard-zero session **81726** and shard-one session
**53775** both exited zero. The checkpoint plot, receipt hashes and exact
membership are in [PROGRESS.md](PROGRESS.md) and
[CHECKPOINT_2.json](CHECKPOINT_2.json). **36/193 members** are complete;
157 remain in the frozen later batches. Both batch-two receipts were verified
before admitting batch three. Do not restart or duplicate claimed workers.

**Current work: batch three is running.** Root owns shard-zero monitoring
session **58400** and shard-one session **83565**. Their first DS16-010 and
DS17-010 search processes were verified live with one numerical thread each,
and both controller claims carry the frozen protocol digest. These handles are
for observation; do not restart claimed workers after a quiet poll.

No geographic evaluation has run; no position-error claim is available for this comparison. Production
B7 and the historical full193 fitted mean of 1.254810 km remain unchanged.

Scientific source, policy, inputs, and the separate evaluation/report protocol
are frozen. Publish position plots only after the full cohort's selections and
failures have terminated. This narrative status file is outside the numerical
input closure.

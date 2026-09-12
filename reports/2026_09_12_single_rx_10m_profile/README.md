# Single-RX 10 MS/s profile: qualification pending

The implementation and plan are in this worktree. Production has **not** been
switched. The 300-second hardware/storage/analysis acceptance gate is incomplete.
No new hopping duty measurement is available.

## Bounded attempts on 2026-09-12

- Attempt 1 selected RX1 but exposed an additional paired-RX guard in the PPU
  source geometry layer, before sampling. Fixed in PPU
  `b513e0b0dab1c15ce790317b35b5edf1abbacfff`, with both physical receiver masks,
  priming geometry, gain readback and capability rejection tested.
- Attempt 2 failed the stock iiOD health check before sampling. Dependency sync
  had replaced the receipt-bound native Python binding; it was restored.
- Attempt 3 entered the owned alternate iiOD lifecycle, then blocked in
  `os.fsync()` of the isolated store's spool directory **before opening a radio
  buffer**. A cancellation SIGALRM was sent while the process was waiting in the
  kernel. It was delivered when the wait returned, and cleanup completed with
  no cleanup-error note. The raw report's "15-minute total deadline" text comes
  from that signal handler; this attempt was manually cancelled earlier, not
  allowed to reach the automatic deadline. The process exited around 17:19:56
  UTC; by 17:22 the production process, not the canary, owned the radio lease.

## Storage observations

At 17:22 UTC the `/srv/bulk` storage path was still experiencing long waits.
The kernel reported XFS journal workers and an analysis process blocked for
more than 122 seconds at 16:45:10, before these canary attempts. This establishes
an issue beginning no later than approximately 16:43, with affected operations
still present about 39 minutes later. Some I/O and the cancelled canary did
progress, so this is not evidence of a complete permanent deadlock.

The RAID worker stack contained `md_super_wait`, `md_bitmap_wait_writes` and
`raid5d`; XFS/application stacks contained journal-space and journal-flush waits.
The four-member RAID6 remained `[4/4][UUUU]`, with no rebuild in progress. All
four HDDs and the cache NVMe reported passing SMART health and no logged errors.
The volume had approximately 41 TB free. The LVM cache reported writethrough
mode and zero dirty cache blocks. These observations do not establish the root
cause or exclude hardware faults.

A five-second device-stat sample showed all four HDDs completing reads and
writes, while the RAID and XFS device still had over 2,000 operations in flight.
Several separate worktree-archive rsync jobs were writing into `/srv/bulk` and
waiting in dirty-page throttling. Their causal role is unconfirmed. No archive
job, RAID setting, filesystem setting, or host power state was changed here.

## Software validation

- PPU: 246 tests passed across IIO geometry, metadata and persistent hopping.
- Native iiOD: eight component test executables passed; ARM provider built and
  packaged with source and artifact identities in the runtime provenance.
- Leo: earlier broader component runs passed; the final focused rerun passed
  40 tests covering profile/retry selection, capture/analysis storage, native
  analysis, and runtime validation. Mypy passed all 492 source files.
- Separate numerical tests cover native 10 MS/s pilot timing/CFO and actual
  elapsed-time Doppler across retune gaps. Both RX identities have coverage.
- UI: 15 tests passed, including single physical RX presentation; build passed.

The full real 300-second acquisition and analysis must pass after storage is
healthy before selecting this profile or publishing a measured hopping duty.

`analyze_canary.py CAPTURE_REPORT ISOLATED_STORE OUTPUT_REPORT` runs the same
production analysis service at a 120 ms probe stride, with two workers and a
30-minute analysis bound. It verifies the capture digest, full visit coverage,
native rate, physical receiver identity and published artifacts. It never
opens a radio and can resume checkpointed analysis after an interrupted run.

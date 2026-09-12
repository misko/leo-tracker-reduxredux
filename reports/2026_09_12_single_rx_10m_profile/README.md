# Single-RX 10 MS/s profile: capture and analysis passed, activation pending

The implementation is in draft PR #24. Production has **not** been switched.
A real 300-second RX1 scan and full-recording analysis passed using the same
writer on isolated local NVMe. Production `/srv/bulk` write/flush readiness is
still unresolved; the local-NVMe result does not qualify that storage volume.

## Completed live result

Session `scan-hop-4790de1446a38628` used radio `radio_pluto_5d4d` at
`192.168.1.20`, with physical RX1 held throughout, 10,000,000 samples/s,
eight pilot-centred targets and 120 ms valid visits.

| Measurement | Result |
| --- | ---: |
| Device-clock span | 300.0157401 s |
| Valid IQ time | 286.56 s |
| Valid duty | **95.5149%** |
| Classified transition time | 13.4557401 s |
| Missing samples / overflows | **0 / 0** |
| Stored visits | 2,388 |
| Raw CI16 bytes | 11,462,400,000 |
| Compressed IQ bytes | 4,966,501,077 |
| Writer queue high-water / capacity | 8 / 64 visits |

Full analysis completed at 18:01:23 UTC using the staged production build:
all 2,388 visits, 299 sweeps and 2,388 native-rate 20 ms probes were accounted
for. Every published chunk retained RX1. Analysis produced 11,437 fractional
candidates and 1,211 passing per-probe winners; these are detector results,
not independent satellite identifications. Coverage, GLRT-response and CFO
artifacts passed digest verification. The plotted device-time axis spans
300 seconds and retains the transition gaps.

The recording remains under `/var/tmp/leo-single-rx-canary5`. Compressed capture
and analysis receipts and the three verified PNGs are retained beside this
report. No IQ was copied into the production recording inventory.

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
- Attempt 4 used isolated local NVMe and reached the radio. An early metadata
  buffer refill failed with `ESTALE` after two reported blocks. Diagnostics
  confirmed buffer closure and restoration of the original radio settings;
  no successful capture receipt was fabricated. The exact cause is unconfirmed.
- Attempt 5 added bounded retention of the owned iiOD log before normal
  cleanup. RX1 completed the full scan with the results above. Its daemon log
  was empty. This successful retry does not establish a fix for attempt 4.

Analysis initially used default BLAS threading. It was manually interrupted
after checkpointing completed sweeps and resumed with production's explicit
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1` settings. The first
analysis report's deadline text came from that manual SIGALRM, not an elapsed
30-minute deadline. The resumed analysis finished successfully.

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
data, RAID setting, filesystem setting, or host power state was changed here.

At the user's request to resume work, the migration was briefly paused at
approximately 17:32 and then all 25 affected processes were resumed when the
user asked to leave migration alone. No further migration changes were made.
The first small file-flush probe took minutes to return and timed out. A
second 64 MiB write/flush probe launched at approximately 17:56 was still in a
kernel filesystem wait at 18:01, with its cancellation signal pending. It
returned failed after 322.614 seconds, when its pending 30-second timeout could
finally be handled. The probe has exited and held no radio lease. Neither
probe establishes production storage readiness; its final result is retained
in `bulk-readiness2.json`.

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
- All developer gates covering the full installed-release delta passed using
  the explicit libiio integration source, including the previously unconfigured
  synthetic threaded integration tests. Deployment radio-binding tests also
  passed (95 tests with the front-door checks).
- Release `f707c81d549727e84754f2dddbbaa3760dd35260` staged and passed protected
  corpus, native science, PostgreSQL, and production Chromium qualification.
  Its scanner deployment policy preserves the explicit single-profile radio
  instead of overwriting it with the older profile's radio default.

## Remaining activation work

The acquisition and analysis-service configuration candidates are prepared
under root-only `/run/leo-single-rx-rollout`, with original settings retained
for rollback. Both point to the new profile/runtime and the existing `.20`
radio; they have not been applied. After storage readiness passes, merge and
qualify the selected exact release, apply acquisition and analysis bindings
together through the supported deployment path, and inspect one bounded
production scan. No additional RF campaign is needed.

`analyze_canary.py CAPTURE_REPORT ISOLATED_STORE OUTPUT_REPORT` runs the same
production analysis service at a 120 ms probe stride, with two workers and a
30-minute analysis bound. It verifies the capture digest, full visit coverage,
native rate, physical receiver identity and published artifacts. It never
opens a radio and can resume checkpointed analysis after an interrupted run.

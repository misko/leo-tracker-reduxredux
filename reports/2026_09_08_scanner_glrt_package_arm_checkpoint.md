# Scanner GLRT: exact package verified on the ARM spare

2026-09-08. **Target loader and saved-IQ execution, not live RF or deployment.**

The [cross-built userspace package](2026_09_08_scanner_glrt_userspace_bundle_checkpoint.md)
now runs its real acquisition SDK and isolated worker on the allowed spare,
with **278/278 expected results** numerically verified and carrying its actual
algorithm/configuration identities. Target loader traces confirm use of the
bundled SDK, libiio, XML/zlib and FFTW libraries, without `LD_LIBRARY_PATH`.
The package's iiOD executable is invoked only with `-V`, which returns before
creating an IIO context or listener.

This test found and fixed a real packaging incompatibility: the radio lacks the
optional BusyBox `stat` applet. The initial guard correctly refused to proceed;
the corrected guard preserves all ownership/permission requirements using
commands present on this image. The failed attempt, recovery and passing run
are retained. **350 component regressions pass.**

No receive buffer was opened, no RF was collected, no listener was started and
no installed binary/library, FPGA, kernel or flashed firmware was changed.
Classification remains default-off/unqualified, nothing is remotely merged or
deployed, and the unchanged-live-duty objective remains unproven.

## Exact workload and identities

The tested package is unchanged from the preceding build checkpoint:

- Manifest: `01c6c1b7037a7dd3de700ff78fd7c9e779373f2d2e4d4ee26d26256851407e7b`
- Algorithm: `10a19ceeb54e1a05f8022a5b8c937f7e596ba7f81315dc62132a8c2a80b5d236`
- Configuration: `f071ba3fa4fedd097091f588439262a2a25616b7c64817741e7d96ee0e0a676d`

The replay harness now accepts a prebuilt SDK and literal runtime search path.
It does not rebuild or copy the SDK under test. Two optional, paired CLI
identities replace its test-only defaults; malformed/zero/uppercase identities
are rejected before opening any payload. The verifier compares each frame to
independently supplied expected identities, rather than trusting identities
read out of the result itself. Existing default test IDs and default build
search-path behavior remain available for earlier fixtures.

Each rate uses the same hash-checked pack of 16 saved full RX1 dwells and frozen
numerical expectations as the preceding SDK replay. The source excerpts are
disjoint and repeated, not a continuous new scan. RX0 and the 1 ms transition
padding are synthetic sentinels. Arrival timing is modeled: 131,072-sample
blocks, two-block-late hop events, and a 40 ms delay on every fourth block.
Counter epochs above 2^53 remain integers; fractional offsets stay separate.

The fixed execution matrix is:

| Run | Rate | Duration | Purpose | Results |
| --- | --- | ---: | --- | ---: |
| 0 | 2.5 MS/s | 1.936 s | Loader trace + numerical/frame verification | 16/16 |
| 1 | 5 MS/s | 1.936 s | Loader trace + numerical/frame verification | 16/16 |
| 2 | 2.5 MS/s | 15 s | Untraced modeled-load check | 123/123 |
| 3 | 5 MS/s | 15 s | Untraced modeled-load check | 123/123 |

The count follows `floor(duration_ms / 121)` complete modeled visits, each with
120 ms valid IQ plus synthetic guard. It is not a measured RF duty percentage.
The initial failed stage ran none of these four tests; the successful attempt
does not repeat a completed replay.

Every result has complete source binding and agrees with the frozen fractional
numerical fields at the existing `rtol=1e-9`, `atol=1e-10`. No valid result is
busy, failed, incomplete or missing. This checks numerical/transport fidelity,
not independent detector sensitivity or false-positive rate.

## Timing: short untraced checks only

| Metric | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| Nominal block period | 52.43 ms | 26.21 ms |
| SDK callback p99 | 7.78 ms | 10.92 ms |
| Maximum SDK callback | 9.22 ms | 16.43 ms |
| Worker CPU p99 | 64.30 ms | 111.68 ms |
| Worker wall p99 | 66.37 ms | 117.09 ms |
| Maximum worker wall | 66.66 ms | 118.13 ms |
| Input-ready callback to frame p99 | 152.52 ms | 175.68 ms |
| Callbacks exceeding nominal block period | 0 | 0 |

At 5 MS/s the worker still has limited headroom against 120 ms dwell arrivals;
the <=100 ms CPU-p99 development target is not met. ARM CPU accounting has the
previously observed coarse timing granularity. These 123 repeated-source visits
are neither an independent tail distribution nor a new 300-second soak test.
Loader-traced executions are excluded from this timing table.

Result-frame latency includes waiting for the next metadata carrier. It is not
an acquisition stall and must not be subtracted from scanner duty. Conversely,
zero callback deadline exceedances under this model do not prove that actual
IIO refill, iiOD locks, IRQ/network work and retunes fit the remaining margin.
The [previous 300-second SDK checkpoint](2026_09_08_scanner_glrt_sdk_replay_checkpoint.md)
remains the full-duration modeled-load evidence; no new full RF scan is claimed.

## Compatibility failure and corrected cleanup

The first real companion verification failed with `/bin/sh: stat: not found`
after all eight companions uploaded. No daemon version check or replay started.
The conservative cleanup also refused to delete unverified companions. The
separate scratch directory was empty because replay payload transfer had not
begun. Both conditions are retained in the initial `end.json`.

PPU now checks the fixed permission, link-count and numeric-uid fields from
`LC_ALL=C ls -ldn`, alongside the existing regular-file/symlink, exact size,
SHA-256 and complete-inventory tests. Paths have already been restricted to
canonical private directories and safe basenames; unexpected output fails
closed. This does not relax modes or ownership and requires no radio-image
change. A portable regression runs the real scripts with a minimal command
directory that deliberately contains no `stat`.

Before a fresh attempt, the known task-created failed-stage directory was
revalidated against the complete manifest on the exact idle target and removed
through the corrected companion cleanup. Only the receipt-named empty scratch
was removed with `rmdir`; original local package files were retained.

The initial research driver did not persist its session nonce before staging.
Recovery therefore records its basis explicitly: the preceding exclusive mkdir
and uploads belonged to this task, the exact private release path and complete
contents were revalidated, and the target was idle under the shared lock. The
corrected driver persists nonce and daemon paths **before** staging. This is a
research-driver audit improvement, not permission to adopt arbitrary remote
directories by reading their owner marker.

The successful final cleanup reports no retained scratch, daemon or companion
directory and no cleanup errors. Session-private host credentials were removed.
Hash-checked installed iiOD, FFTW and core loader/libc/math/thread libraries were
unchanged before/after execution. No unrelated process was stopped or restarted.

## Target and test coverage

Only USB-attached `winbond-db620818a328172c`, at USB path
`/sys/bus/usb/devices/5-1`, is used over its physical Ethernet interface
**192.168.1.14**. USB identity, pinned SSH identity, exact serial, eth0 MAC/address,
shared ownership lock, inactive receive buffers and absence of other network
clients are checked around execution. Production `.20`/`.21`, excluded serials,
`.15` and the `.18` FPGA canary are not used.

The actual production companion staging, verification and cleanup methods run
on the ARM target. However, the full iiOD start/listen/stop lifecycle is **not**
executed here: `iiod -V` proves loader/version execution only. The SDK replay
has no IIO dependency. Both facts limit the claim even though loader paths,
binary hashes and decoded result frames agree.

**202 Leo scanner/native tests** and **148 PPU lifecycle/capture tests** pass with
zero failures, errors or skips. They include the new identity/prebuilt-SDK
cases and the stat-free shell regression. Ruff, formatting, whitespace and
strict PPU module type checks pass. No numerical threshold or golden fixture
changes. The code is committed locally as Leo `c37ff662` and PPU `8baea1c`;
the libiio source revision remains `a188a70d`.

## Remaining work

1. Qualify the detector's positive decisions independently, including short
   bursts, window boundaries, weak signals and nuisance false alarms. Unknown
   or unconfirmed input must not become an absence claim.
2. Improve/characterize 5 MS/s CPU and wall-time headroom under the complete
   producer workload, not only the numerical worker.
3. Exercise the full owned daemon/provider/host path and explicitly authorized
   bounded RF off/on comparisons. New RF authorization is still pending.
   Measure counter-based valid duty, continuity, overflow, hop timing and every
   result's source/terminal accounting without changing acquisition geometry.
4. Review and authorize merge/deployment only after the scientific and live
   operational gates pass. This package check does not enable classification.

[Raw evidence, references, failed attempt, recovery and reproducible recipes](evidence/2026_09_08_scanner_glrt_package_arm/index.json)
retain 106 hash-checked non-IQ/non-executable artifacts. The exact build helper
version is retained by its recorded SHA-256; its later default-RPATH-only
compatibility adjustment does not change the explicit target build command.

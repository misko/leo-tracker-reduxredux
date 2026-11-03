# Continuous scanner implementation and qualification

Status, 2026-10-09: the fast IQ scanner is merged and published independently as
[firmware v0.62 development prerelease](https://github.com/misko/plutosdr-fw/releases/tag/v0.62-plutoplus-spf-continuous-fast-scan).
The exact packaged image passed bounded development-radio
qualification. FPGA acceleration is explicitly paused until this release is
delivered; saved source and simulation results remain available. No FPGA power
candidate has been deployed, and its full-chip placement is not qualified.

The v0.62 image retains v0.61's existing FPGA and PLL timeout correction. Exact
image tests returned 601 receive windows across two recording segments and 112
loopback windows, all with 50,000 complex samples per RX and a measured counter
guard of 20 ms. Independent checks found a 354.132 ms median eight-channel sweep
for the receive run. The 28 tone-target receiver decisions were ACTIVE; the other
196 loopback decisions were QUIET, with no ADC12 clipping in tone windows. A
legacy-v3 check also passed 14 windows and an ordinary capture afterward.
Firmware source and complete scope are tracked in
[firmware PR 125](https://github.com/misko/plutosdr-fw/pull/125).

## Motivation

Both [scan workstreams](scan-workstreams.md) repeat the ordered eight-target
table on the device until STOP. The IQ path saves exact 20 ms windows for offline
GLRT. The standalone power path keeps only window measurements and bounded
telemetry, so a host IQ consumer is unnecessary.

## Problem

The original prototype used bounded, weighted campaigns. Fast repeated visits
did not imply ordered first coverage or indefinite operation. Production claims
also require independent evidence for RF settling, sample identity, file
rotation, cancellation, restoration, and FPGA integration.

The development radio is USB serial `104000b29905000e17000800065934759d`, exposed
on LAN `192.168.1.15`. Its cabled fixture connects TX2 through a 20 dB attenuator
and tee to both receivers. The tests below use diagnostic IF targets
1.80, 1.81, ..., 1.87 GHz. They do not qualify an antenna/LNB interpretation,
all 56 directed frequency transitions, or Starlink identity.

## Solution

The additive iiOD v5 mode uses an ordered device scheduler and bounded queues;
older wire modes retain their semantics. START prepares the radio once.
Independent STATUS/STOP requests carry session and generation identity. STOP
acceptance is distinct from the final drained/restored receipt. The host rotates
sealed IQ v1 segments at 512 windows without resetting device generation or
global visit sequence.

The FPGA PWR1 block admits an exact future sample interval and reports integer
energy, signed sums, rail contacts and counters. A separate ARM controller owns
Fast Lock recalls and runs without IQ DMA. Its latest-eight cache and 64-record
history disclose expired reader cursors. Invalid/aborted measurements remain
separate diagnostic records and cannot claim activity. Its conservative guard
starts after acknowledged recall; this differs from the IQ mode's total
transition allowance and needs independent timing measurements.

## Method

The IQ firmware is developed in the isolated `codex/continuous-ordered-iq`
libiio worktree, based on deployed source `0b7718af9eed0a42eec448d03248c8497b13a779`.
Native protocol, policy, session and queue tests include more than 20,000 visits,
counter rollover, repeated ring wraps, pressure, partial IQ and graceful-to-forced
STOP. The host uses a separate negotiated v5 PPU implementation.

The test daemon and matching library were staged in the radio's RAM filesystem.
The original iiOD/library and read-only `qspi-linux` backup are retained outside
the repository. The flash image has not been replaced. Artifact hashes and
activation evidence are in
[`reports/2026_10_09_continuous_scanner`](../../reports/2026_10_09_continuous_scanner).

### Measured IQ behavior

| Test | Retained dual-RX windows | Result |
| --- | ---: | --- |
| Initial ordered receive-only run | 101 | Exact 50,000 samples/RX; all eight targets; no skipped/invalid visits; restored |
| Segment rotation | 601 | 512 + 89 windows in two sealed files; unchanged device session/generation; restored |
| Five-second TX2 loopback | 123 | 32 receiver decisions ACTIVE on the tone target; 214 other decisions QUIET; RX/TX restored |
| Independent CLI START/STATUS/STOP | 89 | Live status, captured = durable, no fault, restored, repeated STOP idempotent |

The 601-window run measured first complete coverage in **302.4756 ms**, median
successive valid-window start spacing **40.2812 ms**, and median recurring
eight-channel sweep **322.3176 ms**. Maximum observed recurring sweep was
**325.536 ms**. These exclude initial preparation and final restoration.
Each full window contains 400,000 raw bytes across two receivers; one eight-target
sweep retains 3.2 MB. The measured median cadence corresponds to about 9.93 MB/s
of retained raw IQ before compression.

Offline GLRT processed all 601 recorded windows, including all quiet windows,
with zero skips. Verified reading, analysis and output took 0.811 seconds on this
host, excluding Python startup. The supplied template pair and RF/UTC mapping
remain diagnostic; this result does not establish tracking accuracy.

The TX2 test used a +100 kHz DDS tone, TX gain -30 dB and RX gain 40 dB. All 16
tone-target windows had the expected peak on both receivers without ADC12 rail
contacts. This confirms channel-dependent power behavior for that fixture; it
does not qualify smaller guards or all source/destination frequency pairs.

The separate CLI canary exposed a live-checkpoint tuple-to-JSON conversion bug.
That failed run is retained as evidence; the radio restored its original settings.
The correction and a real progress-callback test are implemented. The repeated
independent START/STATUS/STOP canary passed with 89 captured and durable windows,
no reported fault, terminal restoration, and an idempotent second STOP.

### Transition allowance versus post-recall guard

The measurements above used the first v5 implementation's **total transition
allowance**, with `valid_start = selection_counter + 20 ms`. Only a recall
completing after that boundary moved the boundary to recall completion +20 ms.
Consequently, the original implementation did not guarantee a positive minimum
post-recall settling interval when recall completed just before the boundary.
The continuous-mode correction is implemented and requalified below; earlier
recordings and their receipts remain unchanged. The 322 ms cadence belongs to
the original total-allowance implementation.

The original 601-window run had post-recall-to-valid-start intervals of
10.5932–16.2944 ms (median 16.1884 ms). The 123-window tone run had
10.3700–16.3280 ms (median 16.2188 ms). All windows contained exactly 50,000
samples and none began before recall completion. Receipts are summarized in
`observed-recall-guards.json` under the report directory.

An offline diagnostic divided each of the 32 tone-bearing receiver windows into
80 slices of 625 samples (0.25 ms). First-slice power versus the final 10 ms
average ranged from -0.0282 to +0.0308 dB; coherent 100 kHz tone amplitude ranged
from -0.0289 to +0.0299 dB. No slice in these windows exceeded 0.0641 dB power
deviation from that tail average. `retained-window-tone-stability.json` retains
the measurements. This supports stable power within those retained windows;
it does not test discarded transitions, establish a minimum settling guard,
prove absence of stale samples, or cover all directed frequency pairs.

The corrected daemon, libiio commit `44efe08`, uses
`valid_start = max(selection_counter, recall.counter_after) + guard_ticks`
for continuous v5 only. Versions 1–4 retain their existing behavior. Tests cover
recall completion immediately before, at and after the old boundary, a zero-tick
recall and the unchanged finite modes. The host independently rejects complete
windows that violate the configured post-recall minimum, and new receipts name
`minimum-post-recall-v1` with required and observed guard sample counts.

This daemon was deployed in RAM with SHA-256
`6b14d3ecb943d0c7027902e19819bec5cd2d1f978a2d28f4197e23fd8a74ad52`.
The new 101-window receive-only canary had zero missing/invalid/skipped windows
and restored the radio. Every reported post-recall guard was exactly 50,000
ticks (20 ms). Median valid-start spacing was 44.1080 ms; median recurring sweep
was **352.8660 ms**, maximum 354.4156 ms. First-eight coverage, measured from the
first valid sample to the eighth window's end, was 328.2524 ms. That is distinct
from a recurring sweep. A separate five-second TX2 canary retained 112 windows:
28 receiver decisions ACTIVE on the tone target and 196 other decisions QUIET,
zero skipped/invalid visits, and successful RX/TX restoration.

These are guarantees in the **reported counter domain**, not a physical RF
settling-time calibration. The deployed kernel source at
`fastlock-attestation-v059-source/linux-v1` waits for RX PLL lock and checks LO
readback/profile CRC before reading its post-recall GPIO counter. That counter
is a synchronized raw FPGA counter; its CDC age is not yet qualified. The FIFO
IQ timestamp also differs from the prepack sample origin by one tick. Neither
source inspection nor a blind one-tick adjustment establishes the physical
minimum guard. Same-sample FPGA/IQ parity and transition-focused RF tests remain
separate qualification gates.

### FPGA gates

Simulation compares 50,000-sample integer results against an independent oracle,
including signed extrema, timing gaps, rejected late starts, resets, abort and
result pressure. The standalone controller also runs 20,000 simulated visits,
retains diagnostic failures, bounds arithmetic and keeps restoration errors
visible. Native and sanitizer tests pass. The repository component suite now
passes 202 tests (`final-component-tests.txt`); the external PPU suite passes
82 tests at commit `c818d1868d974b1552f3a25a2ca1717808bbd299`.

The first integrated FPGA placement attempt exceeded available packing capacity.
The rebuilt baseline alone routes with 13,524 LUTs, 23,075 flip-flops and all
4,400 slices occupied (setup slack +0.767 ns, hold slack +0.019 ns). A separate
native-factor-one candidate omits the optional FPGA RX decimator and TX
interpolator to make space for power measurement. It preserves the RFIC's
internal filtering, native IQ and timestamps. Its capability register explicitly
reports native-only operation, and unsupported FPGA filter factors must fail
visibly. Full candidate placement/routing are still required; a passing
standalone core report is insufficient.

Independent review also reproduced stale completed-result visibility across a
reset while the RX clock is stopped. Asynchronous validity/control reset and an
owned regression now pass. Resource trials retained all result fields while
moving arithmetic into DSP blocks and separating synchronous data banks from
asynchronous control resets. The latest candidate also removes a duplicate CPU
command bank by rejecting shadow-register writes with AXI SLVERR while COMMIT
is pending. Full and partial writes, stalled RX clocks and acknowledgement
unlocking have owned tests. Actual source revisions are synthesized with IP
caching disabled after a stale-cache trial was identified and excluded.

The independent power/IQ comparison harness and its component tests are ready.
It opens one normal dual-RX metadata capture, arms a separate MMIO-only helper,
and selects exactly 50,000 samples per RX using the supplied source-derived
counter mapping. It checks integer energy, sums, peaks and rail contacts,
counter continuity and record identity. Capture, transport and cleanup failures
remain failures during replay. Numerical parity under that supplied mapping is
reported separately from physical mapping qualification; it cannot establish
the mapping merely by comparing aggregate statistics on periodic or constant IQ.

After a complete image passes those gates, the bounded hardware checks must show
free-running counters with IQ DMA disabled, exact power/IQ parity with the
qualified timestamp packing offset, continued scanning without a host reader,
and explicit STOP/restoration. `tools/repack_fpga_fit.py` prepares an offline
RAM-boot candidate while verifying that kernel, root filesystem, device trees
and other FIT properties are preserved. It performs no device deployment itself.

### Sample-rate scope

The continuous IQ v5 implementation currently rejects rates other than
2.5 MS/s. Policy, wire validation and recording geometry require 50,000 samples
per receiver. This is a current implementation and qualification boundary, not
an architectural requirement of an ordered eight-target scanner. Other scan
modes accepting higher rates do not imply this mode already supports them.

With a 20 ms capture and nominal 20 ms transition per target, the ideal sweep is
320 ms regardless of sample rate, provided processing and transport keep up.
For dual-RX complex signed-16-bit IQ, the uncompressed quantities are:

| Rate per RX | Samples per RX/window | Bytes per sweep | Average retained bytes/s at 320 ms |
| --- | ---: | ---: | ---: |
| 2.5 MS/s | 50,000 | 3,200,000 | 10,000,000 |
| 5 MS/s | 100,000 | 6,400,000 | 20,000,000 |
| 10 MS/s | 200,000 | 12,800,000 | 40,000,000 |

The input IQ rates during capture are respectively 20, 40 and 80 MB/s, excluding
metadata and framing. Higher-rate support requires negotiated geometry, bounded
queue/storage sizing, sustained throughput and settling tests, plus appropriate
filter, threshold and offline-analysis configuration. No 5/10 MS/s continuous
qualification is claimed here.

The native-factor-one FPGA personality does not itself imply a 2.5 MS/s sample
clock limit. However, PWR1 currently accumulates a fixed 50,000 samples: 20 ms at
2.5 MS/s, 10 ms at 5 MS/s or 5 ms at 10 MS/s. A duration-preserving extension
would need explicit 100,000/200,000-sample support and rechecked arithmetic
widths, controller deadlines and timing. The current controller enforces
2.5 MS/s, so these shorter intervals cannot silently be reported as 20 ms.

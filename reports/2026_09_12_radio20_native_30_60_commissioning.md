# Radio .20: native 30/60 MS/s FPGA commissioning

Both new FPGA profiles have been built, deployed and exercised on
`192.168.1.20`, serial `1040005e0b100007100010000bf33a5d4d`.
Each passed receive-interface calibration, ARM-local continuous IQ ingestion,
16 scheduled native measurement jobs, and an independent retained-evidence
review. **Autonomous acquisition, catch-up and sustained feedback remain
unqualified.** The jobs used arbitrary future pilot times, not acquired locks.

The resident firmware at this checkpoint is `glrt-iq-tracking-r30000000-v1`.
Buffers are idle, the tracking queue is drained and cleared, and TX LO is
powered down. There is no installed background tracking service.

## Implemented architecture and rates

| Component | Location | Sample rate / clock | Evidence |
| --- | --- | --- | --- |
| AD9361 reception and ingress | Radio FPGA | 30 or 60 MS/s; 100 MHz processing clock | Both receive clocks calibrated and PN-eye checked |
| FIR channel extraction | FPGA | Native rate to 2.5 MS/s | 30-MS/s bank added; existing 60-MS/s bank preserved |
| CI16 DMA ingestion | Radio ARM | 2.5 MS/s, 10 MB/s | 2,621,440 contiguous samples at each native rate |
| Blind coarse search | ARM | Retained 2.5-MS/s IQ, 14,000 samples/window | Full integer grid matches independent oracle; initial runtime about 1.82 s/window |
| Full resolver and retained-IQ catch-up | ARM | 2.5-MS/s IQ | Earlier 14-case saved-IQ baseline; integration with blind search remains |
| Scheduled pilot measurements | FPGA | 30 or 60 MS/s | 16 complete native jobs per profile |
| Trend conversion and feedback controller | ARM | Event-driven; explicit native-rate coordinates | Source/history mapping and controller tests pass; acquired live integration remains |

The additive `GLI1-1.0` interface exports filtered IQ and `GLT1-1.0` native
tracking. It does not relabel the published GLA1/GLF1 interfaces. The combined
image omits FPGA acquisition, local search and legacy scoring engines.

FIR group delay is 636 native samples at 30 MS/s and 1,272 at 60 MS/s:
53 coarse samples, or 21.2 microseconds. ARM ring coordinates represent the
signal center; native timestamps and original snapshots are retained. Mapping
history to the native scheduler multiplies integer coordinates and local sample
offsets by 12 or 24; physical CFO values remain in Hz. This creates a software
proposal and does not manufacture FPGA observations.

## Routed builds and actual radio results

| Measurement | 30 MS/s | 60 MS/s |
| --- | --- | --- |
| Routed setup / hold slack | +0.078 / +0.024 ns | +0.085 / +0.022 ns |
| LUT usage | 9,102 / 17,600 | 9,901 / 17,600 |
| BRAM usage | 28.5 / 60 | 34.5 / 60 |
| DSP usage | 28 / 80 | 36 / 80 |
| PN-eye passing points | 181 / 256 | 173 / 256 |
| Selected RX delay register | 0x08 | 0x08 |
| Retained IQ | 2,621,440 CI16 samples | 2,621,440 CI16 samples |
| RF duration of successful probe | 1.048576 s | 1.048576 s |
| Complete / acknowledged jobs | 16 / 16 | 16 / 16 |
| Native samples per job | 39,600 | 79,200 |
| Late / expired / unavailable jobs | 0 / 0 / 0 | 0 / 0 / 0 |
| CDC / pacer drops during epoch | 0 / 0 | 0 / 0 |
| Queue high-water mark | 4 | 4 |
| Final stop / drain / clear | Passed | Passed |

Three short probes actually opened RX: two at 60 MS/s and one at 30 MS/s,
totalling 3.145728 seconds. An earlier harness attempt stopped before RX.
All tests used the established LNB settings: requested/read-back LO
1,690,312,496 Hz, RF bandwidth 2.5 MHz, manual gain 30 dB, A_BALANCED port.
These are transport and arithmetic-availability tests, not physical accuracy
or satellite-identity measurements.

The FPGA's finite capture stop deliberately invalidates its tracking epoch.
The harness checks that this occurs only after complete IQ delivery, retains
every result before acknowledgement, and clears the epoch after draining.
Two earlier harness failures remain visible: an epoch was requested before
opening the source, and an expected end-of-capture invalidation was initially
misclassified. Neither was hidden by changing FPGA fault semantics.

The 30-MS/s image initially booted with the AD9361's 30.72-MS/s default clock.
Its pre-epoch snapshot recorded 5,413,836 historical pacer drops. Configuration
and calibration then set exactly 30 MS/s, and REBASE established a fresh epoch
with zero drops throughout the qualified visit. The independent review retains
these boot counters separately. A startup service must configure/calibrate the
clock before opening RX and creating a tracking epoch.

## Deployment and reproducibility

Both packages passed independent U-Boot payload extraction, GNU cpio inspection
and DFU suffix verification. Both written FIT hashes were read back before
reboot and re-attested afterward, with the same exact radio serial. The PPU
profiles also check the Micron flash, protected bootloader, saved Ethernet
address, idle buffers and TX state. Each operation held the normal production
qualification lease and radio lock. The exact v0.49 rollback image was verified
locally; this checkpoint deliberately leaves the new 30-MS/s image resident.

| Package | FIT SHA-256 |
| --- | --- |
| 30 MS/s | `c7245f4e8f5f0045c780dae46402375c143ea31ad2d08014a1670af9dac37703` |
| 60 MS/s | `19c1504e8cbf442f4fd2ee995a0ceaf3780a9a4559026a653f8fdaae53932f1b` |

Built source commits: HDL `5379707fb1197a713913ada645470b9847020602`,
Linux `93924ab8fb3aac44ff0f7452141350dde005be8b`, Buildroot
`3179d1c6df88038560b56ddb1db350ffc68b41b0`. The later commissioning/runtime
tools are committed separately in `plutosdr-fw` branch
`codex/radio20-tracking-qualification`. PPU transition support is in
`device-tool-radio20-tracking`, commit `97a4f0b`.

Full evidence root:
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`.
Successful directories: `board-{30000000,60000000}-v4`,
`verify-{30000000,60000000}-v1`, `deploy60-v3`, `deploy30-v1`,
`hardware60-v3`, `hardware30-v1`. Original manifests, earlier failed attempts,
raw IQ, all snapshots, submitted descriptors and returned moments remain there.

Compact repository evidence: [30-MS/s independent review](figures/2026_09_12_radio20_native_30_60_commissioning/radio30-review.json),
[60-MS/s independent review](figures/2026_09_12_radio20_native_30_60_commissioning/radio60-review.json),
[30-MS/s deployment](figures/2026_09_12_radio20_native_30_60_commissioning/radio30-deploy.json),
[60-MS/s deployment](figures/2026_09_12_radio20_native_30_60_commissioning/radio60-deploy.json),
[30-MS/s calibration](figures/2026_09_12_radio20_native_30_60_commissioning/radio30-calibration.json),
[60-MS/s calibration](figures/2026_09_12_radio20_native_30_60_commissioning/radio60-calibration.json),
[initial coarse-grid review](figures/2026_09_12_radio20_native_30_60_commissioning/coarse-initial-review.json).

## Next integration constraint

The initial ARM blind scan was numerically exact across all 146,652 grid
scores and all selected peaks in four retained physical windows. Its measured
times were 1,821.30, 1,822.17, 1,820.79 and 1,826.48 ms. That already exceeds
the current one-second seed-age limit, before full resolution. Improving this
runtime is required; widening the freshness limit is not an established fix.
The score peaks alone do not prove accepted acquisition or tracking support.

Subsequent saved-IQ-only ARM optimization reduced the same scans to
1,185.61–1,186.22 ms. Integer corrections preserve exact square roots and Q16
quotients while avoiding software 64-bit conversions/division. The dot-product
range was also proven to fit signed 32-bit accumulators; squaring still widens
to 64 bits. These timings still exceed the seed-age limit, and exclude loaded
DMA and resolver work. All four complete score grids remain byte-identical to
the independently verified initial grids.

A two-thread partition of that exact computation subsequently measured
638.23–645.01 ms per window on the radio. All 146,652 scores again match
byte-for-byte. Partial partitions cannot publish peaks; writers are joined
before peak selection. This brings the isolated scan within the one-second
seed-age limit, while loaded DMA contention, subsequent resolution/catch-up
and total acquisition latency still require integration tests. No RF was
collected during these scanner benchmarks. Evidence:
[two-thread ARM review](figures/2026_09_12_radio20_native_30_60_commissioning/coarse-parallel-review.json).

The next checkpoint is a direct software-candidate handoff through full
resolution and catch-up into GLT1, with current source-time checks and native
feedback. Sequential RF scanning, reacquisition and slower multi-frame
refinement require that acquired loop first. The present evidence does not
claim those stages are implemented as a complete autonomous service.

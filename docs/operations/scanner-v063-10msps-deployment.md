# Radio .20: v0.63 and fixed 10 MS/s

## Current cadence (2026-10-23 Pacific)

The operator increased the wait after each scan to twenty minutes. Captures
remain five minutes, alternating fast lower, adaptive, fast upper, adaptive.
This gives approximately 25 minutes between capture starts and 50 minutes
between fast-scan starts, subject to the existing backlog gate. The installed
`zzzzz-fast-v16-startup.conf` timer override uses `OnActiveSec=20min` and
`OnUnitInactiveSec=20min`, matching `deploy/systemd/leo-shared-scan.timer.conf`.
The deployment record below describes the earlier ten-minute cadence.

Target: `192.168.1.20`, serial `1040005e0b100007100010000bf33a5d4d`.
Preserve the existing five-minute capture / ten-minute gap, alternating fast
lower, adaptive, fast upper, adaptive. Test captures are receive-only and
bounded to seconds, with no retries on failed restoration.

## Firmware gate

Read the live identity with PPU inventory and `/opt/VERSIONS` through the
serial-specific pinned SSH key. Require v0.63, device libiio source
`6162275af8ec4622dc42a53307d6f5a65ed8840f`, and the official release binding
to firmware source `f17a4737e6bfbebcd91e7d5dd5902c2d855ae05f`.

The retained PPU LAN flash receipt is
`/srv/bulk/leo/continuous-scan-v063/persistent-radio20/receipts/edf9646f-8fac-4024-93b7-5e399866f1f5.json`.
It records protected-region verification, written-FIT verification, reboot,
same-serial return, host-key rotation, and TX-safe return.

Read exactly 12,817,135 bytes from the firmware partition. The required FIT
SHA-256 is `2d87ff9d79724f4452b6526de7d39656905fb35efd84bb4c57027299efd0b13e`.
The installed iiOD and libiio hashes must match the release artifact binding.
These checks passed during this deployment review; another flash is unnecessary.

If any check differs, stop. A new persistent installation uses PPU's exact
qualified `flash-lan` plan/execute flow, its printed serial/address confirmation,
firmware-only DFU/FRM and pinned SSH key. Review image, FIT, physical flash
bounds, protected regions and backup evidence before execution. An uncertain
write requires read-only reconciliation; never replay it automatically.
No bootloader or environment image is part of this deployment.

## Deployment result

Installed runtime: `/opt/leo-shared-scans/v063-10m-0eab0c85fa2aac69`.
Both scheduled recorder commands explicitly select 10,000,000 samples/s.
The deployed cadence is five minutes of capture followed by a ten-minute gap.
Capture was subsequently paused by the operator for NVMe evacuation and remains
paused during saved-data backfill; do not enable its timer as part of analysis
recovery.
The analysis worker and compatible viewer are deployed; legacy 2.5 MS/s
recordings continue to use their original formats and predictor policy.

The exact staged runtime passed 136 portable/PostgreSQL checks. Seven viewer
tests and the production web build passed. Short lower/upper canaries retained
91 windows each with exact 200,000 samples per receiver, all eight targets,
200,000-sample minimum guards and successful restoration. A 12-second adaptive
canary delivered all 87 planned dwells. Native saved-IQ GLRT and the installed
Standard tracking adapter checks passed.

The first scheduled 300-second adaptive recording completed and restored the
radio. Live IIO readback showed 10,000,000 samples/s on both RX channels. Its
existing delivery gate passed at 99.362%: 2,181 of 2,195 planned dwells delivered,
14 skipped dwells, 3 forced deadlines, no invalid or cancelled dwells. This is
not a zero-loss qualification. The scheduler advanced and scheduled its normal
ten-minute gap. Detailed metrics and immutable input references are retained in
`reports/2026_10_22_scanner_v063_10m/deployment-verification.json`.

## Host gate

Stop the scanner timer and drain the scanner service before changing its
configuration. Preserve the prior service overrides and capture configuration.
Stage a separate root-owned runtime from the existing installed worker sources
with only the reviewed scanner modules replaced. Bind every staged file by
SHA-256, including the matched PPU companion source and capture configuration.
Do not deploy unrelated dirty workspace changes or replace installed code.

Pass `--sample-rate 10000000` explicitly to both recorder commands. Continuous
windows retain native 200,000-sample simultaneous dual-RX IQ with a configured
20 ms minimum post-recall guard. Disk reservation budgets full-rate dual-RX
data and headroom. Segment and queue byte bounds apply at the selected rate.

Published v1 recording and scientific contracts remain fixed at 2.5 MS/s.
Native 10 MS/s recordings and analysis use additive v2 envelopes. GLRT uses
native IQ, rate and counter coordinates throughout reporting and tracking
export. The 2.5 MS/s fast predictor and its cutoff are disabled at 10 MS/s;
every valid window receives GLRT. This is not a sensitivity or localization
qualification. Existing LNB reference hypotheses remain explicit.

## Native fast-analysis recovery

Full 512-window native segment jobs exceeded the existing 600-second execution
limit. Native analysis now queues at most 64 windows per job; legacy 2.5 MS/s
segment scopes remain supported. The reader verifies each selected compressed
chunk, its index and its complete uncompressed payload while consuming the
requested interval, before a job can publish its result. Neither IQ, detector policy nor original sample coordinates
are changed. Execution bounds participate in the immutable release identity.

The analysis runtime is
`/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9`. Its Standard adapter is
`/opt/leo-fast-standard/native-10m-585a256cd61ff4b5/bin/fast_scan_standard_pipeline.py`,
using the existing selected Standard worker and orbit renderer. The adapter
selects `DualRxPersistentHopTimingV2` for 10 MS/s and retains the legacy timing
constructor for earlier rates.

Analysis temporary files use `/srv/bulk/leo/presentation-cache/tmp` on RAID.
This host's OS filesystem has no space available to unprivileged workers;
falling back to `/tmp` prevents Standard plot publication.

ADC-clipping flags continue to invalidate affected windows. The native v2
tracking export records each excluded visit, IQ digest, counter interval and
reason, then supplies only valid windows to tracking without renumbering visits
or compressing counter gaps. GLRT reports still account for the entire sealed
inventory. Legacy export behavior and published scientific contracts are
unchanged.

The ten saved scans were backfilled from RAID. All 67,728 windows are accounted
for: 67,433 processed windows and 295 explicit exclusions for recorded
ADC-clipping flags. All 1,060 bounded GLRT jobs succeeded without a retry or
failure; the slowest finished within 451 seconds of the 600-second limit.

All ten Standard analyses completed tracking, position methods, blind regional,
adaptive TLE position, regional position and orbit publication. All 40 orbit PNGs
passed digest checks. Each scan retains fitted-c and zero-c results for B3, B4 and
B4W, conditional on common upstream calibration and association; frequency-fit
metrics and reference-distance errors are reported separately. Completion is
not a claim of improved localization accuracy.

The installed native runtime passed 34 focused portable/PostgreSQL tests; three
Standard adapter tests cover native and legacy timing, clock-step rejection and
counter support. All 352 native-runtime files and three Standard adapter files
matched their deployment manifests. The running API served all ten completed
native reports and orbit manifests successfully; a PNG delivery check also
matched its published digest.

The CPU queue limit is restored to eight and the regular analysis watcher is
running with the bounded native runtime. Capture remains paused and its timer
disabled. Selection, input-quality inventory and acceptance evidence are under
`/srv/bulk/leo/fast-scan-backfill-20261023`; the readable final receipts are
`acceptance.json` and `api-acceptance.json` in that directory.

## Installed verification and recovery

Run short lower/upper continuous canaries and a short adaptive canary under
the existing per-radio and pipeline locks. Verify actual readback rates,
window lengths, guard counters, hashes, terminal accounting and restoration.
Read sealed windows back through the installed source and exercise native-rate
GLRT and the tracking-input rate/counter mapping. Keep receipts and test logs
under `/srv/bulk/leo/scanner-v063-10m-deploy-20261022`.

Only after successful canaries, install a final service override selecting the
new configuration and enable the existing timer. Verify systemd's resolved
command and both nested commands select 10 MS/s. Keep the previous runtime
and configuration intact for rollback. On failure, stop the timer, retain
evidence, restore the prior service selector and configuration, and report
that the rate deployment failed. Do not collect extra data to compensate.

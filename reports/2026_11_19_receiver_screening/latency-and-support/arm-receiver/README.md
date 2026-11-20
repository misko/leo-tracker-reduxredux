# Offline AArch64 stock and fifth-center receiver

The static detector capsule runs both modes on successive packed dual-receiver CI16 windows with one warm context per stream. Cortex-A53 QEMU preserved candidate order and fractional gate decisions on all 72 compared receiver lanes. Fractional tracking CFO was identical on every complete matched candidate. The largest fractional epoch difference was **1.62 × 10⁻¹⁴ samples**. Warm AArch64 QEMU detector wall was **372.97 ms stock and 452.88 ms fifth-center** on the recorded panel. Physical-board timing remains unmeasured. [Qualified capsule](arm64-detector-capsule.tar.gz) · [Native output and parity](parity.json) · [Timing data](stage.csv)

## Physical development device

The host identified the attached PlutoSDR+ from the local USB kernel hierarchy. USB ID `0456:b673`, its ACM and Ethernet siblings and the development serial ending `4759d` match the earlier device receipt. The host is x86-64 and has no local IIO or remote-processor entry for executing code on this board. Both previously attempted strict LAN and USB SSH routes stopped at host-key verification before login. The documented project host-key pin remains root-only and unreadable under the current account. This check read kernel metadata and file permissions. It sent no traffic, opened no serial device, made no board changes and collected no RF. [Current local evidence](board-access.json) · [Earlier strict identity attempts](../../receiver-core/board-replay/README.md)

The existing development Pluto uses the Cortex-A9 ARMv7 release. Its [previous operating-system-matched offline package](../../support-preserving/fifth-arm/README.md) is the build for that board once there is a trusted, explicitly authorized idle execution route. The new AArch64 executable targets a Linux ARM64 deployment with an Armv8-A CPU. It uses the same frozen stock and fifth-center native science as the earlier package, and adds a persistent-context chronological replay for that target. [Prior CFO-stride cross-build](../../receiver-core/stride-arm/README.md)

## Full native measurement boundary

Use the first six chronological valid visits from each of DS26-0197 and DS29-0316. Their complete 1,600,000-byte windows preserve exact raw hashes, delivery clocks, receiver order and original sample counters. The six controls use zero IQ, a one-live-frame pilot and a strong pilot at each edge, with signed carriers at ±193,450 Hz and ±688,125 Hz. A single process keeps the detector, FFTW plans and buffers alive over each edge's six recorded inputs, then its three controls. Two chronological passes give 24 recorded calls per mode, including two first calls. The table uses the 22 warmed recorded calls per mode. A separate process envelope includes the library setup, file reads and JSON output. [Fixture identities](fixtures.json) · [Whole-process and first-use measurements](summary.json)

| Execution and mode | Warm process CPU | Warm wall | Calls within 20 ms wall |
| --- | ---: | ---: | ---: |
| Native x86 stock | 16.64 ms | 17.77 ms | 21/24 |
| Native x86 fifth-center | 20.75 ms | 22.50 ms | 2/24 |
| Cortex-A53 QEMU stock | 370.87 ms | 372.97 ms | 0/24 |
| Cortex-A53 QEMU fifth-center | 439.72 ms | 452.88 ms | 0/24 |

The warm emulated fifth-center scout used 59.12 ms median CPU before the 380.54 ms median native detector. Separate per-call medians need not sum to the median combined time. Entire emulated 18-call streams took 5.68–7.58 s wall and peaked at 50,252–54,612 KiB process RSS. RSS includes the emulator. File reads had a median below 0.50 ms in all four cells. Both builds and both detector modes used the same pinned host CPU for measurements. [Stage figure](stage.pdf) · [Pinned executable and FFTW source/build hashes](build-arm64.json)

The x86 reference exactly reproduced all 24 corresponding archived recorded stock/fifth packets. Across architectures, all 36 mode/window comparisons retained the full ranked proposal list and region size and all ordered candidates retained their integer timing/CFO-bin keys. The full scientific JSON digests agreed on 4/36 mode/window combinations. The receipt retains the different nonzero numeric payloads. Both architectures and modes retained all four planted strong lanes, and both zero controls stayed gate-negative. The fifth center recovered all four signed one-frame lanes on each architecture, compared with zero for stock. [Per-window verification](parity.json) · [Complete measured native rows](native-rows.json.gz)

## Run the capsule

Unpack `arm64-detector-capsule.tar.gz` into a new local directory. Run `./benchmark` on an AArch64 Linux host or `./benchmark qemu` on a host with `qemu-aarch64`. The command checks all bundled hashes, then emits JSONL identifying the stream, setup and every native dual-lane result. The ~3 MiB ELF links both FFTW precisions and the C runtime statically. It has no ELF interpreter or shared runtime dependencies. The ~25 MiB package also carries the authenticated fixtures and exact/rolled templates. No repository, Python, archive or network connection is needed at runtime. [Relocated one-command execution](relocated-command.json) · [Qualification seal](qualification-lock.json)

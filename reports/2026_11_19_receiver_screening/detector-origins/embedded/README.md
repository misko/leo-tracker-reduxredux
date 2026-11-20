# Offline capture-era acquisition on Cortex-A9

The standalone ARMv7 hard-float program ran the capture producer’s original portable folded-anchor body on a saved 20 ms DS26-0036 input. Native x86 and Cortex-A9 QEMU agreed on all **279,993** scores within **5.56 × 10⁻¹⁷** absolute error and selected the exact same eight epoch/CFO basins. The x86 C executable reproduced the installed portable extension byte for byte. The installed AVX2/FMA result also selected the same eight basins. Body CPU was **0.680 s on x86** and **27.886 s in QEMU**.

## Physical board availability

Read-only host inventory at 13:50 UTC showed one attached ADALM-PLUTO USB device and the timestamp-capable PlutoSDR+ serial link ending in `4759d`. Its USB network had a local `192.168.2.10/24` address and a stale cached neighbor. The operations documentation identifies this serial as the development device previously used via LAN `.15`. An active acquisition timer and fast scanner process named the different production serial ending in `a5d4d`. These facts establish attachment and distinguish the scheduled host scanner. They do not attest idle status or establish a currently authorized CPU-only board execution route. No serial port, remote connection, radio operation, or device-side command was used. [Development device record](../../../../docs/operations/continuous-scanner-implementation.md) · [Production acquisition status procedure](../../../../docs/operations/adaptive-radio20-recovery-plan.md)

## Actual input and software boundary

The fixture uses segment 0, visit 1, receiver index 0, from the lower pilot edge at 10 MS/s. An independent read of the bound segment verified the full dual-RX CI16 SHA-256 and matched all 200,000 receiver-lane samples exactly after conversion to complex128. The fixture also preserves the capture-time exact pilot template, 21 CFO cells, 12 anchor intervals, 15 frame offsets, captured prefix power and 13,333 epoch cells. The recorded original capture result had four passing candidates on this receiver. Candidate gating and following conditioned/fractional refinement did not run in this benchmark. [Raw CI16 audit](raw-input-audit.json) · [Input and producer bindings](source-lock.json) · [Frozen protocol](PROTOCOL.md)

The standalone executable compiles the hash-matched production C kernel without Python, FFTW or radio interfaces. The only changes at its boundary are a fixed little-endian input format, workspace ownership, bounded input validation and clock measurement. The version-5 EABI ELF is static and uses the Cortex-A9/NEON hard-float flags. Numerical output is every little-endian binary64 score in CFO-major order. The same frozen capture Python function selects the top eight basins from each grid at comparison time. [Exact portable body](_native_acquisition_grid.inc) · [Full parity and target ELF evidence](receipt.json)

## Measured stages

| Stage | Native x86 CPU s | Cortex-A9 QEMU CPU s |
|---|---:|---:|
| Input and validation | 0.006062 | 0.011657 |
| Workspace | 0.000032 | 0.000287 |
| Magnitude precheck | 0.001331 | 0.010992 |
| Folded grid body | 0.679971 | 27.885671 |
| Score output | 0.000331 | 0.001066 |
| Total instrumented | 0.687728 | 27.909672 |

Process CPU and monotonic elapsed measurements independently close across all adjacent stages. External elapsed time was 0.693 s on x86 and 28.339 s for QEMU. Each execution performed 2,146,326,336 complex accumulation steps with 9,562,000 bytes of explicit input, output and workspace allocations. That is an allocation total, not a device RSS measurement. The recorded process high-water can include the launcher’s state and QEMU overhead. QEMU uses the corpus host CPU, so these times establish reproducibility of the target executable and its instrumentation. Physical board throughput, capture overlap, complete detector speed and position timing remain unmeasured.

## Run the portable capsule on the host

Extract the capsule into a new local scratch directory. It contains the static ELF, the authenticated input packet and SHA-256 sums. A buildroot sysroot and Python are unnecessary for this execution.

```sh
tar -xzf cortex-a9-offline.tar.gz
sha256sum -c SHA256SUMS
qemu-arm -cpu cortex-a9 ./capture-board-folded folded.input >scores.bin 2>stages.json
sha256sum scores.bin
```

The QEMU score digest from the measured run is `497b3990e4354cbb260395113fe89f940240664c05db7e02fd1b0ec9a0e59ada`. On an independently authorized, idle compatible board, the same program takes the same argument directly from its approved scratch directory. Its only program input is the file opened read-only. [Runnable Cortex-A9 capsule](cortex-a9-offline.tar.gz)

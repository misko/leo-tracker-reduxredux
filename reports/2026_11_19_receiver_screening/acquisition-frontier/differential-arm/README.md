# Differential FFTW scout on the ARMv7 ABI

The standalone ARMv7 build produced **byte-identical scores on all 293,326 cells** and exactly the same complete top-16 ordering on **22 of 22 receiver lanes** as the native x86 executable. It also agreed with the frozen Python ordering on all 22 lanes. The maximum normalized score deviation from NumPy was `6.22e-7`. Warm dual-receiver score CPU was **2.44 ms on native x86** and **62.79 ms in Cortex-A9 QEMU**. [Timing figure](stage.pdf) · [Numerical and clock receipts](measurements.json)

| Input | Actual edge | Rank-one ARM centers for receivers 0 / 1 | Scope |
| --- | --- | ---: | --- |
| DS26-0162 visit 19 | Upper | 5783 / 3038 | Preserves the previously recovered receiver 1 timing |
| DS29-0082 visit 2 | Upper | 5095 / 8954 | Preserves the close-ranked difficult result with the wrong receiver 1 timing |
| DS26-0237 visit 198 | Lower | 1435 / 10804 | Preserves the genuine lower-edge scout result |
| Signed full-frame and one-frame plants | Both | 735 / 735 in all four windows | Known-epoch synthetic check at the original signed CFO |
| Seeded noise and zero IQ | Both | Noise ranks match x86. Zero emits empty lists. | Checks ranking and abstention before any GLRT gate |

The first three inputs are the unchanged authenticated dual CI16 payloads from the prior x86-runtime panel. All synthetic waveforms use that panel’s sealed seeds and exact byte hashes. The scout ranks positive local maxima of the exact-minus-rolled differential power surface and can nominate epochs in noise. Scientific admission belongs to the subsequent GLRT. The scorer uses three template phase residues but emits timing and score only. CFO and phase estimates, the complete receiver, localization, and physical silicon throughput are outside this measured boundary. [Input and template hashes](source-lock.json) · [Prior complete detector boundary](../differential-runtime/README.md)

## Stage measurements

| Median per complete dual-RX input | Native x86 CPU / wall | Cortex-A9 QEMU CPU / wall |
| --- | ---: | ---: |
| Read and validate | 1.72 / 2.11 ms | 6.45 / 7.41 ms |
| Allocate FFTW context and plans | 0.62 / 0.64 ms | 11.99 / 12.51 ms |
| First score | 3.52 / 3.57 ms | 70.56 / 73.42 ms |
| Warm score | 2.44 / 2.55 ms | 62.79 / 63.50 ms |
| Warm top-16 extraction | 0.33 / 0.33 ms | 2.17 / 2.17 ms |
| External process, six calls including startup and output | 21.53 / 25.22 ms | 428.52 / 485.96 ms |

Each platform ran one cold and five warm calls per fixture. Counterbalanced runs used the same pinned host CPU 2. The QEMU clocks describe the emulator process and guest clock observations on this host. ARM metadata shows static ELF32, EABI5 hard-float, ARMv7-A, VFPv3, and NEONv1. The executable reports FFTW `3.3.10-neon`, linked from the previously qualified local archive with SHA-256 `85e6c4828eca8b0295eab8dabd600e6688f14adc2b9bea8371abd2f55b1336a2`. The x86 executable reports `3.3.10-sse2-avx`. The only numerical scorer is the frozen 44-sample differential C source. [Toolchain and ELF receipt](source-lock.json) · [Per-call CSV](stage.csv)

Explicit buffers total **6.16 MiB** on ARM, including 2.53 MiB for the scout workspace. This excludes FFTW plan and libc sorting allocations. Separate process sampling observed peak RSS of about **9.29 MiB** for native x86 and **15.48 MiB** for QEMU across the recovered real and lower one-frame inputs. These peaks use `/proc` after the expected executable starts. The recorded raw `getrusage` peaks include inherited launcher high-water accounting and are retained in the raw receipt only. QEMU resident memory includes the emulator itself. [Process-memory witness](memory.json)

## Offline ARM capsule

The capsule contains the tested static ARMv7 executable, both authenticated template banks, and the signed lower-edge synthetic CI16 canary. Extract it to a new local directory and verify the recorded SHA-256 values. The executable requires exactly 20 ms at 10 MS/s in little-endian signed 16-bit `[time][receiver][I,Q]` order, with two receivers. Score output is two rows of 13,333 little-endian binary64 values on stdout. Stderr contains JSON clock and top-16 results.

```sh
tar -xzf differential-armv7.tar.gz
sha256sum -c SHA256SUMS
timeout 15s qemu-arm -cpu cortex-a9 ./differential-scout-arm \
    lower-strong.ci16 lower-filters.c8 lower-energies.f64 6 \
    > timing-surface.f64 2> scout-receipt.json
```

The cross-build and exact template export are reproducible from the repository module `tools.pipeline_eval.qualification.differential_arm`, using `prepare`, `run`, and `capsule` with a workspace and a single pinned core for the measurement. The packaged sample contains synthetic IQ. No new RF collection, network or device execution was used. [Runnable ARMv7 capsule](differential-armv7.tar.gz) · [Protocol](PROTOCOL.md) · [Result hashes](result-lock.json)

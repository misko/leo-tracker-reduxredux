# Full folded acquisition with overlap-save FFTs

On the authenticated capture-era DS26-0036 input, the folded acquisition body used **78.2% less CPU on x86** and **75.8% less CPU in Cortex-A9 QEMU** than the original portable FP64 C loop. The new bank preserves all 279,993 CFO/epoch cells, all 12 anchors and 15 frame offsets. Every score agreed with the same-input direct calculation within **3.06 × 10⁻¹⁶**, and the original capture selector retained the same eight basins in the same order. [Measurement receipt](receipt.json) · [Frozen inputs and build hashes](source-lock.json)

| Captured receiver | Direct body CPU | FFT bank body CPU | Direct / FFT observed total CPU |
|---|---:|---:|---:|
| Native x86, median of three pairs | 0.6583 s | 0.1435 s | 0.6662 / 0.1509 s |
| Cortex-A9 QEMU, one pair | 27.3005 s | 6.6055 s | 27.3260 / 6.6328 s |

The body measurement includes FFT plan creation and the filter spectra. Wall and process CPU clocks come from the same executable on each architecture. Both methods used the same standalone adapter for input authentication, workspace setup and score writing. The x86 runs were fresh applications in alternating order on core 5. The emulated ARMv7/NEON hard-float applications used that same host core.

## How the bank preserves the score

The original loop multiplies the waveform by each short, CFO-modulated complex pilot slice at every allowed starting sample. The bank reverses and conjugates each slice to make an FIR impulse response. A 512-point overlap-save block reuses one complex input FFT across every template/CFO pair. The exact CFO phase rotations are shared across anchors. The code keeps only the linear-convolution portion of each inverse transform. It normalizes each correlation magnitude using the original pilot and waveform energies before folding by epoch. It divides the folded magnitudes by the original count of geometrically supported samples, including zero-energy intervals in that count.

On the measured geometry the bank used 427 input FFTs, 252 filter FFTs, and 104,286 inverse FFTs. Explicit FFT buffers add **2,088,960 bytes** above the unchanged standalone harness allocations. FFTW plan allocations are outside that byte count. The direct wrapper's nominal complex accumulation count labels the original geometry even when it runs the FFT bank. The FFT arithmetic and accumulation order change rounding, while retaining every original observation. This is a generic FIR decomposition, separate from the Qin-specific rectangular-tone approximation and from support-reduction experiments. [Bank implementation](../../../../tools/pipeline_eval/variants/folded_bank.c)

## Adversarial controls

The paired weak-pilot fixture adds two nearby epochs at opposite CFOs and an in-band interfering tone to seeded noise, using the captured template and geometric support. Both implementations matched every cell and the retained basin order on both architectures. The `717 samples / −240 kHz` plant entered the retained set at rank five. The `713 samples / +240 kHz` plant was outside the retained eight in both. The retained basins are coarse nominations. A subsequent detector would still have to apply the capture producer’s refinement and margin gate.

The zero-pilot control uses the same seeded noise alone. Its full cell comparison passed and all eight coarse noise basins kept their order. The controls use the complete captured score-grid shape.

| Synthetic control | x86 direct / FFT body CPU | QEMU direct / FFT body CPU | Largest absolute score difference |
|---|---:|---:|---:|
| Weak pair with interference | 0.6543 / 0.1456 s | 27.2513 / 6.5705 s | 3.34 × 10⁻¹⁶ |
| Noise only | 0.6464 / 0.1401 s | 29.6920 / 6.5141 s | 3.06 × 10⁻¹⁶ |

The recorded cost compares the original portable-double kernel. The optimized Qin-specific spectral path was outside the timing comparison. The benchmark measures a single receiver’s coarse acquisition grid. It leaves dual-receiver throughput, refinement, tracking, calibration and positioning unmeasured. QEMU times cannot establish physical device throughput.

## Reproduction

The FFT ARMv7 binary, direct comparator, authentic input and hashes are in the benchmark archive. The executables use the platform’s dynamic loader, and the FFT bank needs the bound double-precision FFTW library. The source lock includes both ELF records, the Buildroot sysroot and the library hashes. From an empty scratch directory with that local sysroot, verify the archive payload and run either binary with the same input.

```sh
tar -xzf armv7-benchmark.tar.gz
sha256sum -c SHA256SUMS
qemu-arm -cpu cortex-a9 -L "$sysroot" ./folded-bank-armv7 folded.input >bank.bin 2>clocks.jsonl
```

The full benchmark builder generates the two synthetic inputs and runs all pairs. The target archive runner reads the given packet and writes the little-endian binary64 score grid to stdout.

- [Protocol](PROTOCOL.md) · [Runnable ARMv7 benchmark archive](armv7-benchmark.tar.gz) · [Score and timing evidence](receipt.json)

The archived benchmark driver matches the SHA-256 in the original source lock. The current driver was formatted after measurement and has an identical Python syntax tree. [Measured Python driver](measured-source.zip)

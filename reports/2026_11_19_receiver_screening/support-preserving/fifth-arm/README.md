# Complete fifth-center detector on ARMv7

The offline ARMv7 hard-float executable runs the complete dual-receiver wide detector, from saved CI16 through fractional CFO/epoch refinement and the original gate. In union mode it computes the same 44-sample differential FFTW scout as the host and adds the first ranked timing center per receiver to the existing detector. The stock mode calls the original four-center ABI. The off mode passes two absent hints through the optional ABI. It reproduced stock output on both architectures at both edges.

The same-source ARM and x86 builds matched **32/32 stock and 44/44 union gated candidates** and every ordered integer candidate key on all 16 receiver lanes per mode. All **16/16 complete ordered top-16 scout lists** and all eight union support traces matched. Across all 57 stock and 66 union completed refinements, CFOs were identical, the fractional offset differed by at most **2.1 × 10⁻¹⁴ samples** and the margin differed by at most **5.1 × 10⁻¹⁶**. The gated candidates' full epoch, after adding the integer start, differed by at most **9.1 × 10⁻¹³ samples**. Full floating-point rows were bit-identical on two of eight windows per mode. The native x86 executable reproduced all 16 prior stock/union payloads exactly after removing clocks. [Numerical and timing summary](summary.json)

| Genuine saved IQ | Edge | Capture-era target passed by stock / union on both builds |
| --- | --- | --- |
| DS26-0162 visit 19 | Upper | No / yes |
| DS26-0237 visit 72 | Lower | No / yes |
| DS29-0082 visit 2 | Upper | No / no |
| DS26-0237 visit 198 | Lower | No / no |

The roster spans prior known recoveries and difficult examples. It measures cross-build parity on those examples. Both signed plants at ±688.125 kHz passed on both receivers. Both seeded-noise windows stayed below the gate. The study ends at RF measurements and emits no position. [Protocol](PROTOCOL.md) · [Measurements](measurements.json)

## Timing

Median milliseconds across eight windows per mode. Each measured call used a fresh process, with run order alternated on the same host core. The process row includes file input, runtime startup, plan setup and JSON output. Detector context and scout CPU are also measured inside the executable. ARM numbers describe QEMU Cortex-A9 on x86 and give no physical-board timing or memory measurement.

| Stage | Native x86 CPU / wall | Cortex-A9 QEMU CPU / wall |
| --- | ---: | ---: |
| Stock detector context | 14.2 / 14.2 | 255.5 / 255.8 |
| Stock detector call | 29.9 / 29.9 | 936.3 / 936.7 |
| Stock whole process | 48.6 / 50.4 | 1,221.7 / 1,226.3 |
| Union detector context | 13.9 / 14.2 | 254.6 / 254.7 |
| Union scout context | 0.14 / 0.14 | 4.34 / 4.34 |
| Union differential FFT and top-16 rank | 6.4 / 6.5 | 93.0 / 93.1 |
| Union detector call | 31.5 / 32.3 | 932.2 / 932.3 |
| Union whole process | 59.2 / 62.7 | 1,321.3 / 1,325.3 |

[Stage chart](stage.png) · [PDF](stage.pdf) · [All cold CPU and wall timings](stage.csv)

## Offline replay

The capsule contains the ARMv7 EABI5 hard-float/NEON detector, its runtime loader, glibc, libm, double-precision FFTW, both edge template sets and the signed lower-edge synthetic vector. The detector and single-precision FFTW scout link into the ARM executable. The capsule includes no genuine capture bytes. Both modes reproduced the published signed-lower ARM output when run from a fresh extraction with only the bundled guest runtime. [ARM capsule](fifth-armv7.tar.gz) · [Extraction verification](capsule-verification.json)

```sh
mkdir replay
tar -xzf fifth-armv7.tar.gz -C replay
cd replay
sha256sum -c SHA256SUMS
timeout 15s qemu-arm -cpu cortex-a9 -L runtime ./fifth-detector-arm union \
  lower-strong.ci16 lower-exact.c16 lower-control.c16 lower-filters.c8 \
  lower-energies.f64 1 > receipt.json
```

Replace `union` with `stock` to run the four-center control, or with `off` to test the optional ABI with no hints. To use another offline file, provide exactly 200,000 little-endian `[rx0 I, rx0 Q, rx1 I, rx1 Q]` signed 16-bit samples at 10 MS/s and the template set for its edge. The executable assumes the original 10 MHz wide-detector RF geometry. A compatible ARMv7 Linux can launch the executable using `./runtime/lib/ld-linux-armhf.so.3 --library-path runtime/lib:runtime/usr/lib ./fifth-detector-arm` followed by those arguments. Qualification used file input and the emulator.

The source lock records the sealed center-union detector sources, both compilers and binary artifacts, matching ARM and x86 FFTW inputs, runtime library hashes, exact references, input SHA-256 and prior paired records. [Center-union release](../center-union/README.md) · [Source lock](source-lock.json) · [Result lock](result-lock.json)

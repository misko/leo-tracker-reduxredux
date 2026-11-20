# Scalar fractional GLRT reuse on x86 and emulated ARM

The existing architecture-independent center reuse preserved every scientific return on this panel. A portable implementation also shared template traversal for the two left and the two right outer starts. It kept both start scores and their FFTs independent. The combined variant reduced median total CPU by 10.9% for stock and 6.8% for fifth-center on Cortex-A53 QEMU. On x86 the median reductions were 4.5% and 1.9%, respectively. No variant consistently completed a recorded dual-receiver call within 20 ms on the measured host. No physical-board test was run.

## What changed

The original scalar search evaluated five integer points for each fractional epoch. The [`glrt_center_cell` overlay](../../../../tools/pipeline_eval/variants/glrt_center_cell.py) reused the completed final score at `k=2` when the support, original score configuration, epoch and acquired CFO matched. It left the other four calls in their original order. This overlay was already implemented separately from the AVX2-only grouped search.

The new portable [`arm_center_pair.h`](../../../../tools/pipeline_eval/variants/arm_center_pair.h) additionally paired integer offsets −2/−1 and +1/+2. Each start retained its own binary64 sums in sample order and its own normalization, spectra and peaks. A pair used the original scalar path if the original support crossed the circular epoch edge or the two starts did not admit the same frames. The timed binaries excluded the diagnostic counters. A separate instrumented build counted work and verified the returned packets.

Across the 12 recorded dual-receiver visits, stock used 830 scalar lattice calls. Center reuse replaced 166, leaving 664. Center plus pairing dispatched those remaining cells as 332 pairs with 4,882 shared frame traversals. Fifth-center used 850 scalar lattice calls. Center reuse replaced 170, leaving 680, and pairing dispatched those as 340 pairs with 5,010 shared frame traversals. Pairing kept the four outer hypotheses and their FFTs. All 72 recorded-or-control visit contexts conserved original lattice coverage across timed architecture/detector settings.

## Paired timings

The fixed roster used visits 12–17 from DS26-0197 and DS29-0316, two chronological passes per detector and variant. Each timing below is a median over 22 warm dual-receiver calls. The 20 ms tally includes the first recorded call in each context, yielding 24 calls per cell. Total includes the scout, when enabled, and native detection. It excludes fixture reads and context setup. The full process CPU, wall, peak RSS, per-call measurements and high percentiles are in the sealed evidence.

| Execution | Detector | Variant | Fractional CPU (ms) | Total CPU (ms) | Total wall (ms) | Total wall p95 (ms) | ≤20 ms |
|---|---|---|---:|---:|---:|---:|---:|
| Native x86, CPU 8 | Stock | Original | 8.686 | 25.665 | 26.109 | 29.682 | 0/24 |
| Native x86, CPU 8 | Stock | Center | 7.371 | 24.537 | 24.575 | 34.747 | 1/24 |
| Native x86, CPU 8 | Stock | Center + pairs | 7.520 | 24.502 | 25.041 | 37.128 | 0/24 |
| Native x86, CPU 8 | Fifth | Original | 8.920 | 30.197 | 30.197 | 35.131 | 0/24 |
| Native x86, CPU 8 | Fifth | Center | 7.766 | 30.883 | 30.884 | 37.879 | 0/24 |
| Native x86, CPU 8 | Fifth | Center + pairs | 7.736 | 29.619 | 29.620 | 36.442 | 0/24 |
| Cortex-A53 QEMU, CPU 9 | Stock | Original | 274.441 | 532.130 | 532.202 | 667.004 | 0/24 |
| Cortex-A53 QEMU, CPU 9 | Stock | Center | 233.623 | 487.516 | 513.170 | 622.236 | 0/24 |
| Cortex-A53 QEMU, CPU 9 | Stock | Center + pairs | 223.923 | 474.251 | 474.307 | 606.941 | 0/24 |
| Cortex-A53 QEMU, CPU 9 | Fifth | Original | 282.193 | 644.041 | 647.246 | 739.703 | 0/24 |
| Cortex-A53 QEMU, CPU 9 | Fifth | Center | 245.319 | 602.835 | 606.859 | 701.090 | 0/24 |
| Cortex-A53 QEMU, CPU 9 | Fifth | Center + pairs | 231.618 | 600.043 | 604.950 | 692.519 | 0/24 |

Including setup, fixture reads and JSON output, the two QEMU stock processes together used 16.22, 15.33 and 14.76 CPU seconds for original, center and combined. Fifth-center used 20.69, 19.48 and 19.35 seconds. Peak process RSS stayed between 49.8 and 53.6 MiB under QEMU and 42.7 and 47.4 MiB on x86 across these processes. The x86 paired fraction was effectively unchanged from center-only, and x86 timing tails did not improve on this small panel. QEMU clocks measure the host executing the AArch64 binary. Physical ARM runtime and the physical 20 ms deadline remain unmeasured.

## Numerical qualification

- All 432 timed science payloads matched their same-architecture original packets byte-for-byte. This covers candidate order, integer and fractional epoch, grids and scores, signed CFO, gate status, native receiver/probe fields and scout hints. The independently rebuilt trace variants also matched in all 144 comparisons. Input authority, delivery clocks, raw SHA-256 and physical sample counters are in [input-lock.json](input-lock.json).
- All 24 recorded stock/fifth packets from the original x86 binary reproduced the archival candidate lists exactly. Direct cross-architecture comparison of the original binaries gave complete packet byte equality on 4/36 recorded-or-control contexts, identical candidate order and fractional-gate order on all 72 receiver lanes, and the same scout ranks and admitted region counts on 36/36. The maximum observed tracking CFO difference was zero and the maximum fractional epoch difference was 1.17 × 10⁻¹⁴ samples. [Cross-architecture comparisons](cross-architecture.json)
- Both architectures, all variants and both detector modes accepted the planted strong pilots from both receivers at ±688,125 Hz. Fifth-center also recovered the signed ±193,450 Hz one-frame controls on both receivers on both edges. Stock kept those four planted lane targets withheld. No zero-control lane emitted a gated candidate. Control matching required a gated CFO within 1 kHz and epoch within two samples.
- Two isolated compilation preflights failed before processing any windows. The runner's diagnostic declaration was moved below the POSIX setup, and the overlay was rebuilt in `native_glrt.c`, the translation unit that includes `full_search.c`. The final build receipts pin the original toolchains, edited and unchanged objects, overlay hashes, and measurement binaries. No sealed base source was edited.

The portable C component tests exercise separate scalar sums, exact pair output, terminal and circular fallback, and diagnostic conservation. The build and evaluation commands and sealed evidence are linked below.

- [Protocol](PROTOCOL.md) · [x86 build](build-host.json) · [ARM64 build](build-arm64.json)
- [Stage CSV](stage.csv) · [Stage figure](stage.png) · [Vector figure](stage.pdf) · [Summary](summary.json)
- [Measurements](measurements.json.gz) · [Numerical parity](parity.json.gz) · [Seal](qualification-lock.json)

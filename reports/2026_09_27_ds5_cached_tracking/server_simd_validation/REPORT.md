# Unchanged server SIMD validation

This outcome-informed validation ran the unchanged exact-SIMD candidate after its
original component planning gate failed. The follow-up was authorized because a
smaller general compute improvement could still be useful. It does not
retroactively pass the original 1.10x gate and introduced no new minimum speed
threshold.

The paired run covered 320 receiver cases: 256 new development receivers, 24 old
constructed-control receivers, and 40 new adversarial-control receivers. Each
variant received one warmup and three cyclically counterbalanced repetitions on
P-core 0. Timings are complete caller thread CPU and wall measurements. The
original FP64 path includes receiver packing. Totals sum each receiver case's
three-repetition median directly.

| Variant | CPU total | Wall total |
|---|---:|---:|
| Original packed FP64 | 947.315 ms | 980.620 ms |
| Stable strided FP32 FFTW | 670.953 ms | 694.606 ms |
| Unchanged strided FP32 FFTW + integer SIMD | 670.523 ms | 699.900 ms |

The total original-FP64-to-SIMD result is **1.4128x CPU** and **1.4011x wall**.
Almost all of that benefit already comes from the stable FP32 FFTW and strided
ingress work: original FP64 to stable FP32 is 1.4119x CPU and 1.4118x wall. The
new integer SIMD increment is **1.0006x CPU** and **0.9924x wall** overall. On the
256 real development receiver cases alone it is 1.0041x CPU and 1.0022x wall.
The earlier approximately 1.065x random-input component result therefore did not
transfer materially to this corpus.

| Scope | Receiver cases | FP64→SIMD CPU | FP32→SIMD CPU | FP32→SIMD wall |
|---|---:|---:|---:|---:|
| New development | 256 | 1.4121x | 1.0041x | 1.0022x |
| Old constructed controls | 24 | 1.4626x | 0.9975x | 0.8994x |
| New adversarial controls | 40 | 1.3903x | 0.9813x | 0.9909x |
| 2.5 Msps | 160 | 1.4251x | 0.9937x | 0.9770x |
| 5 Msps | 160 | 1.4067x | 1.0041x | 1.0003x |

The scientific validation gate passed. Every one of the 320 SIMD results exactly
matched every non-timing field from stable FP32 FFTW, and all three repetitions
were deterministic. Original FP64, stable FP32, and SIMD each produced 169
positive top results. All 169 stable and SIMD positives matched the FP64 reference
within the frozen 2 us circular timing and 8 kHz CFO identity rule, with no lost or
additional positives. By inventory, the matched counts were 129 new-development,
8 old-control, and 32 adversarial-control receiver cases.

These controls verify result preservation under their constructions; they do not
calibrate physical detector sensitivity or false-positive rate. FP64 is a
numerical reference rather than physical truth. The evidence establishes about a
1.41x total server improvement from all prior FP32/strided work and essentially no
incremental corpus benefit from this SIMD prototype. It does not establish 10x,
ARM, production, or RF performance.

Frozen evidence:

- `design.json`: `b991ad7d932eb2d087078556bcc75411cd21452aa9b08861fe0192c91c86434b`
- `source_lock.json`: `10457033eadadaa51c05e1794bc35ae26843aade3b5be2b591ce07acef5cb7db`
- `run_validation.py`: `cfc250c8d3bda0abf6bec71de84c3ce29cda684859e756221f91696b3c81dade`
- `results.json`: `b9e580a95434f073d06ec8a6b19535cc95204d773f9cba3ccfd06ef66bf0d22a`
- Unchanged candidate binary: `1364b352d661df932716781dbf5b022bde738a76dceb73141b64fe35d43371ad`
- Original failed component result: `4f1abd221b530cb7953a9a0cee9f09f98a9e9f3250cdb137f348ae87aa99ea61`

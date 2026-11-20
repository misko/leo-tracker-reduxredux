# Frozen CFO stride under Cortex-A9 emulation

Across seven admitted saved-IQ visits, striding reduced measured emulated detector CPU by **8.32%** and regional coarse CPU by **37.35%**. External one-shot process wall rose **7.97%**. Both variants matched all eight capture-era positives and all 17 corresponding x86 positive records within the raw CFO tolerance. The results describe Cortex-A9 QEMU execution on the host. [Protocol](PROTOCOL.md) · [Stage figure](stage.pdf) · [Timing data](stage.csv)

## Build and paired boundary

Both ABI-1 libraries came from the existing frozen host source trees and the pinned Cortex-A9 hard-float release build. The full-bank ARM shared library and packaged CLI reproduced the earlier wide ARM artifacts byte for byte. The strided library SHA-256 is `777b72b4660b81de01af536c5143084dd5474cb347221178e0a972abc3e389ff`. The off-library SHA-256 is `ddc058cb82a223e70591d38ce2e904c073476cd994898e7369a845bfbcd218af`. The source manifests and export lists agree with the reviewed ABI. [Release receipt](release.json) · [Full build](control-build.json) · [Stride build](stride-build.json)

The packaged CLI moved the first emulation pass to host CPU0 through its guest affinity setting. The measured repeat used CPU2 and the same ARM libraries through the original CLI serializer compiled without its affinity macro. The CPU0 and CPU2 runs reproduced all public numerical payloads on seven held pairs and 14 controls. Both datasets remain sealed, and the timings below use only CPU2. [Affinity audit](AFFINITY.md) · [Affinity receipt](affinity-receipt.json)

| Seven emulated one-shot pairs | Full bank → strided bank |
| --- | ---: |
| Pooled native detector CPU | 3,010.01 → 2,759.48 ms |
| Pooled regional coarse CPU | 517.98 → 324.54 ms |
| Median native detector CPU | 421.28 → 396.90 ms |
| Pooled external QEMU process wall | 5.155 → 5.566 s |
| Peak emulator RSS | 50,092 → 50,172 KiB |

External wall includes QEMU and process startup, template/input reads, and serialization. The native detector timer starts after context construction. A separate ABI profile reused one context for five calls on the first valid visit from each recording. The startup, first-call and median of four subsequent calls are measured on the same raw bytes within each pair. [Scoped timing and memory](qualification.json)

| Reused-context profile | Initialization wall | First detector CPU | Subsequent median detector CPU |
| --- | ---: | ---: | ---: |
| DS26-0036 | 216.12 → 271.69 ms | 411.09 → 410.03 ms | 405.76 → 404.90 ms |
| DS29-0082 | 206.98 → 195.95 ms | 412.86 → 370.59 ms | 412.04 → 373.43 ms |

## RF and component checks

The paired roster was segment 3 sequences 8, 15, 22 and 27 for each recording. Seven of eight visits passed the original capture validity policy. All 14 ARM receiver rows differed in at least one numerical field from x86 in each branch. The Cortex-A9 implementation computes its coarse magnitudes with a reciprocal square-root vector kernel. Every held positive matched the corresponding x86 positive within two samples and 1 kHz raw CFO, and the preserved archives showed no changed positive identity. Within ARM, both branches emitted 17 positives. [DS26 replay](DS26-0036.json.gz) · [DS29 replay](DS29-0082.json.gz)

Both edges reproduced their native x86 planted matches for the signed edge and odd-CFO, faint, same-epoch 160 kHz and symbol-alias controls. The weaker same-epoch 160 kHz target on the upper edge was missed by both releases on both architectures. The upper −720 kHz control retained the target on both receivers with one fewer duplicate vote in the strided build. Empty and seeded noise emitted no positives. The frozen coarse-cell component fixture passed under QEMU with the original ARM vector magnitude code, and the Python receiver-order comparator test passed. This stage measured neither physical board performance nor geographic error. [Synthetic controls](controls.json.gz) · [Evidence seal](prediction-lock.json)

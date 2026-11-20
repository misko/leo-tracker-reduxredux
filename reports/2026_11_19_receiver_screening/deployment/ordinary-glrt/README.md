# Compact fine-frequency cache for ordinary wave8 GLRT

The detector used 5.73% less CPU on the held host panel and preserved every emitted candidate value, score, rank and diagnostic counter. The fine CFO stage used 43.10% less CPU. Both versions missed the 20 ms dual-RX deadline on all held host calls. Cortex-A9 emulation measured 0.96% less detector CPU and 4.60% less fine CFO CPU. Physical embedded throughput remains unmeasured. [Frozen protocol](PROTOCOL.md) · [Timing and parity](qualification.json)

## What changed

The two original frames per fine acquisition retain the original FFTW plan, FP32 input products and normalization. At 10 MS/s, the cache now keeps 1,601 of 20,000 output bins per frame. Every legal window is a contiguous slice of the cached signed frequency band. The allocation drops from 160,000 to 12,808 bytes per cached frame, or from 2,560,000 to 204,928 bytes at the maximum of eight distinct cached epochs with two frames each. FFT input and output workspace sizes remain the same. Template energy is accumulated once per receiver search. The overlay changes only the fine kernel and adds a 30-line C helper.

The frozen protocol also specifies a CI16 prefix energy calculation. A later source audit found that ordinary coarse search clears the preparation flag before calling fine acquisition. The measured trial therefore used original direct energy accumulation, with gains attributable to the cache layout and template reuse. The component test separately verifies the exact arithmetic of the dormant prefix helper. A production change to carry that flag would require its own measurement.

## Replays and deadline

Each recording contributed eight preselected segment-local visits, previously unused in detector qualification. Four DS29 visits retained their original capture exclusions. All 12 remaining visits matched the complete native candidate payload within each architecture and preserved 14 positive candidates across both physical receivers. Both weak pilot controls preserved original matching positives on both receivers, and all four empty or noise controls remained negative.

| Timing scope | Original → compact detector CPU | Original → compact fine CFO CPU | Median detector CPU | CPU deadline ≤20 ms |
| --- | ---: | ---: | ---: | ---: |
| x86, 58 paired steady calls | 1,854.64 → 1,748.36 ms | 243.79 → 138.71 ms | 32.31 → 30.11 ms | 0/58 → 0/58 |
| Cortex-A9 QEMU, 12 one-shot pairs | 4,440.15 → 4,397.69 ms | 971.70 → 926.99 ms | 382.06 → 379.58 ms | 0/12 → 0/12 |

The largest held host CPU time was 41.57 ms original and 61.03 ms compact. Isolated ARM CLI peak RSS including the emulator was 47,520 → 45,888 KiB. The x86 shared library remained 2,509,080 bytes. The ARM CLI grew from 1,696,312 to 1,700,408 bytes. For the original timings, making the entire measured fine stage free at fixed remaining cost would bound whole-detector improvement at 1.15× on x86 and 1.28× in emulation. The fine acquisition change clears the predeclared pooled host speed gate and leaves a 30 ms median call. [Raw paired outputs and timings](prediction-lock.json)

An isolated shared-library probe repeated the first admitted held visit of each case using a single reused context per build. Median of the next four calls follows the first-call measurement. The host DS26 difference varied between protocols. The main timing result comes from the alternating held panel above.

| Process | Context creation wall | First detector CPU | Warm median detector CPU | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| DS26 x86 | 20.13 → 14.56 ms | 20.98 → 21.16 ms | 19.43 → 21.19 ms | 41,124 → 39,824 KiB |
| DS29 x86 | 26.20 → 16.90 ms | 33.19 → 29.36 ms | 30.61 → 26.02 ms | 41,492 → 39,656 KiB |
| DS26 Cortex-A9 QEMU | 253.98 → 257.20 ms | 354.42 → 353.67 ms | 361.98 → 362.22 ms | 47,092 → 45,828 KiB |
| DS29 Cortex-A9 QEMU | 274.62 → 278.80 ms | 562.82 → 564.45 ms | 569.29 → 568.42 ms | 49,436 → 45,852 KiB |

On those two x86 visits, original median CI16 conversion consumed 5.60–6.14 ms and allocation plus cleanup consumed 0.85–1.03 ms. This work is outside fine acquisition. [DS26 host profile](DS26-0036-host-profile.json) · [DS29 host profile](DS29-0082-host-profile.json) · [DS26 emulated profile](DS26-0036-arm-profile.json) · [DS29 emulated profile](DS29-0082-arm-profile.json)

## Fresh positions after matched factor substitution

| Recording | Fresh / archived valid visits | Fresh worker wall | `c = 0` error | Fitted `c` error |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 / 6,757 | 9.40 s | 0.654 km | 0.739 km |
| DS29-0082 | 4 / 4,864 | 6.84 s | Withheld | Withheld |

Fresh fits consumed the actual held candidate factors and joined previously authenticated ordinary factors for the remaining visits. The serialized factor probes and Graph digest matched the independently measured complete stock replay, and the two model arms produced the same outputs with matched catalogue, causal candidate set, tile and options. DS29 withheld both corrections for weak held track support. [Fresh and matched control receipts](position-receipts.json)

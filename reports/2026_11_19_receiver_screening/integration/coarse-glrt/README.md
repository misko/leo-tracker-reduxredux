# Adjacent coarse epochs in the ordinary wave8 detector

The triplet kernel preserved every native candidate value, score, counter and rank on 23 valid held visits and all 10 controls per architecture. It cut measured regional coarse CPU by 0.73% on x86 and increased it by 0.47% under Cortex-A9 emulation. Whole CPU was 2.18% lower on x86, below the 3% acceptance gate, and 0.10% higher under emulation. The regional stage accounted for about 1.6 ms of the 74.3 ms pooled host difference. Neither build sustained the 20 ms deadline. [Frozen protocol](PROTOCOL.md) · [Paired RF and timing evidence](qualification.json)

## Ordinary search geometry and cost

The shipped wave8 release uses three differential proposal lags and at most four regional centers per receiver. Native coarse search covers each center and its adjacent samples on 11 searched CFO hypotheses. The kernel retains the original 12-lane layout. Three consecutive valid epochs share the reference vector load and a sliding sample triplet within each four-CFO group. Boundary positions and nonpositive energy use the original path. Both builds perform the same products and accumulation for every frame, symbol and epoch. Grouping reduces reference loads by up to a factor of three per triplet and adds zero heap workspace. The x86 library stays at 2,509,080 bytes. The ARM CLI grows by 4,096 bytes, from 1,696,312 to 1,700,408. [Kernel and build evidence](source-lock.json)

The original held host stage sums below pool 113 calls. The emulated stage sums pool 23 one-shot calls. Proposal includes fold, correlation and ranking. Fine FFT is included in acquisition, and stage instrumentation does not cover all outer cost.

| Original stage | x86 CPU | Cortex-A9 QEMU CPU |
| --- | ---: | ---: |
| Proposal fold / correlation / ranking | 135.7 / 59.0 / 58.9 ms | 260.7 / 337.4 / 97.0 ms |
| Regional coarse | 220.4 ms | 900.2 ms |
| Fine FFT | 448.0 ms | 1,932.5 ms |
| Conditioned CFO | 51.0 ms | 125.0 ms |
| Other GLRT | 297.2 ms | 647.2 ms |
| Fractional epoch | 1,106.6 ms | 3,991.1 ms |

| Platform | Detector CPU, original → triplet | Regional coarse CPU | Median detector CPU | Deadline ≤20 ms, CPU / wall |
| --- | ---: | ---: | ---: | ---: |
| x86 host, 113 steady paired calls | 3,404.58 → 3,330.30 ms | 220.44 → 218.83 ms | 29.68 → 29.70 ms | 1/113 → 1/113 / 1/113 → 0/113 |
| Cortex-A9 QEMU, 23 isolated pairs | 8,689.17 → 8,697.59 ms | 900.2 → 904.4 ms | 379.87 → 377.92 ms | 0/23 → 0/23 / 0/23 → 0/23 |

Removing all regional coarse time with other costs held fixed could raise throughput by at most 1.07× on x86 and 1.12× under emulation. Median host detector CPU consumes about 148% of a 20 ms single-core budget. Peak Cortex-A9 QEMU CLI RSS was 47,688 → 47,524 KiB including emulation. The host paired harness with both contexts and held input peaked at 246,608–252,008 KiB. Physical Cortex-A9 timing and RSS remain unmeasured.

Isolated profiles repeated the first admitted held visit in a reused context for each build. The warm columns give the median of the next four calls after the first. Host context preparation and cleanup sit outside the coarse kernel. The DS29 triplet context creation spike came from a single sample and is retained in the receipt.

| Case and platform | Context creation wall | First detector CPU | Warm detector CPU / regional coarse CPU | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| DS26 host | 13.66 → 13.71 ms | 28.01 → 27.90 ms | 25.94 → 26.60 / 1.63 → 1.79 ms | 41,808 → 41,836 KiB |
| DS29 host | 14.42 → 71.29 ms | 31.32 → 31.45 ms | 26.73 → 29.68 / 1.45 → 1.74 ms | 41,868 → 41,884 KiB |
| DS26 Cortex-A9 QEMU | 257.82 → 274.95 ms | 548.91 → 544.19 ms | 554.89 → 555.68 / 43.34 → 46.90 ms | 47,924 → 47,932 KiB |
| DS29 Cortex-A9 QEMU | 260.41 → 271.49 ms | 604.81 → 610.26 ms | 602.24 → 604.40 / 43.27 → 46.49 ms | 49,912 → 49,908 KiB |

[DS26 host profile](DS26-0036-host-profile.json) · [DS29 host profile](DS29-0082-host-profile.json) · [DS26 emulated profile](DS26-0036-arm-profile.json) · [DS29 emulated profile](DS29-0082-arm-profile.json)

## RF controls

The 23 valid visits emitted the same 37 positive records. The original capture excluded one DS29 visit. Each control used the same RF geometry per recording and all candidate payloads matched. The amplitude-128 +48 kHz pilot matched both physical receivers on both sessions, with maximum matched margins between 0.6710 and 0.6863. Empty, noise and the amplitude-8 plant emitted no positives. With the two interfering tones present, a target match within two samples and 1 kHz survived on only one of four receiver/session pairs, with margin 0.1767. The other three returned positive records outside the planted match window. [Per-receiver matches](qualification.json)

## Fresh geographic fits

| Recording | Fresh / archived valid visits | Fresh worker wall | `c = 0` error | Fitted `c` error |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 12 / 6,753 | 6.61 s | 0.654 km | 0.739 km |
| DS29-0082 | 11 / 4,857 | 4.98 s | Withheld | Withheld |

Both fresh clock-plus-offset workers used the actual modified held detector output and authenticated archived ordinary factors elsewhere. The scientific probes and Graph digest exactly matched the earlier complete ordinary replay, as did the output of both calibration arms. The input document digests identify each partial substitution. DS29 withheld both fixes for weak held track support. [Fresh and reference fit receipts](position-receipts.json)

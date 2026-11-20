# Portable ordinary GLRT interpolation

The four-output interpolation batch preserved every emitted native candidate field, score and rank in all 15 valid held visits and all six synthetic control pairs per architecture. The real IQ included both physical receivers and yielded 50 original positive records. One scheduled DS29 visit retained its original capture validity exclusion. Cross-compiled ARM results compare the two builds on the same Cortex-A9 emulator. Each architecture has its own exact comparison.

| Platform and scope | Detector CPU, original → batch | Fractional epoch CPU, original → batch |
| --- | ---: | ---: |
| Native x86 host, three paired repetitions | 895.59 → 898.48 ms | 308.12 → 294.45 ms |
| Cortex-A9 QEMU, one paired repetition | 5,766.55 → 5,735.33 ms | 2,566.15 → 2,535.45 ms |

The 0.32% host slowdown failed the predeclared 8% improvement gate. ARM detector CPU improved 0.54% under emulation. Peak emulator RSS was 47,608 KiB original and 47,332 KiB batched, including the emulator. Host paired-runner peak RSS was 231,748–237,520 KiB with both builds and the held IQ resident. The detector sums exclude file loads and emulator startup. Emulator time and RSS characterize these runs only.

The fractional stage was 34.4% of original host CPU and 44.5% of emulated ARM CPU in the held panel. Holding other work constant, removing the entire measured stage would bound the corresponding detector improvements at 1.52× and 1.80×. A completed fractional candidate can interpolate up to 15 frames × 64 symbols × 44 complex samples. At 16 taps and four FP64 multiply/add operations per complex tap, that is up to 2,703,360 multiply/add operations and 84,480 scalar divisions before unchanged correlation and FFT work. The batch shares interpolation weights where the actual rounded coordinates match and reuses existing FFT scratch. It preserves each output’s full tap accumulation.

| Case | Fresh / archived valid visits | Fresh worker wall | `c = 0` error | Fitted `c` error |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 / 6,757 | 5.57 s | 0.654 km | 0.739 km |
| DS29-0082 | 7 / 4,861 | 4.22 s | Withheld | Withheld |

Both fresh clock-plus-offset fits consumed measured candidate factors for the stated held visits and the previously measured ordinary factors for all other valid visits. The scientific probe serialization and Graph digest matched the authenticated complete ordinary replay exactly. The composite native document has a distinct provenance digest. The request, catalogue, ownership and position outputs for both calibration arms matched their complete ordinary controls. DS29 withheld both positions for weak held track support. The gallery keeps forced diagnostics separately labeled.

The source lock covers the frozen measurement runner, build overlay, C header and protocol. The four compressed receipts preserve timing and payload arrays. `ordinary_front_position` can repackage the summary and prediction seal from the raw-stage receipts and the fresh position worker receipts. See the `ordinary_front_build`, `ordinary_front_eval` and `ordinary_front_position` qualification entrypoints for replay arguments.

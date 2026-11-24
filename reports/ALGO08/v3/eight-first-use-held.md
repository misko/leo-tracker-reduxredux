# Held physical transfer through complete first verification

The same packed 8/12 ms capture and full first readback improved the held DS30-0169 writer-to-signed-output clock by **84.817 and 215.455 ms elapsed** in reversed orders. It preserved the first member's 64 issued visits, **51 admissions and 13 exclusions**, all 102 signed probe rows, all 56 mixed factors, and the original unfiltered EOF choice. Every packed first analysis authenticated all 128 encoded blocks and independently recovered and verified all 64 complete decoded windows and their aggregate SHA-256. [Dense rehearsal](eight-first-use.md) · [Frozen transfer protocol](eight-first-use-protocol.md) · [Combined receipt](measurements/eight-first-use-held.json.gz)

| Held DS30-0169 | Durable writer CPU / wall ms | First acquire CPU / wall ms | Complete signed output CPU / wall ms |
| --- | ---: | ---: | ---: |
| Packed 20/8, order 1 | 118.336 / 118.343 | 262.091 / 262.096 | 396.780 / 396.792 |
| Ordinary 20/8, order 1 | 152.234 / 152.238 | 325.456 / 325.467 | 481.595 / 481.609 |
| Ordinary named 20 ms, one reference | 153.564 / 153.574 | 576.715 / 576.735 | 731.103 / 731.133 |
| Ordinary 20/8, order 2 | 152.046 / 152.050 | 430.343 / 430.356 | 586.419 / 586.436 |
| Packed 20/8, order 2 | 119.336 / 119.339 | 247.699 / 247.704 | 370.973 / 370.981 |

The ordinary writer reproduced the original compressed digest exactly. The packed output stored 77,000,078 bytes including metadata and seek table, versus 79,029,549 conventional bytes. The uncompressed 102,400,000 bytes and original signed index were identical. The newly written manifests uniquely bind each corresponding signed acquisition and keep the exact original per-window data and actual RF/time metadata. Named 20 ms produced 15 factors on the same opportunities. Both detectors retained the original 13 invalid visits and decision reasons. The packed reader verified both parts of every stereo window, including the invalid visits and unused tails.

The reversed orders paid 32.710–33.898 ms less CPU for capture. The ordinary compressed descriptor and digest varied from 89.438 to 196.756 ms CPU. That range explains most of the between-order change in the ordinary acquisition and limits any extrapolation. Held arms saw zero major faults and input blocks. Fixture hydration took 286.559 CPU ms and is separate from the clock starting with already owned physical words. Adding it to the packed writer-through-first-output clock puts legacy migration at 657.533–683.339 CPU ms on this held member, above the earlier verified ordinary analysis. [Earlier acquisition-only study](seekable-eight-raw.md)

## Both physical members

| Sum of one physical member from each case | Ordinary 20/8 CPU / wall ms | Packed 20/8 CPU / wall ms | Same-detector speed ratio, wall |
| --- | ---: | ---: | ---: |
| First frozen order per case | 1,074.436 / 1,076.694 | 809.649 / 809.670 | 1.330× |
| Second frozen order per case | 1,122.272 / 1,122.315 | 778.013 / 778.029 | 1.443× |

The separately measured named 20 ms reference, one complete writer and reader per case, sums to **1,495.166 CPU ms and 1,496.046 elapsed ms**. The respective packed 20/8 sums are **1.848× and 1.923×** as fast as that reference through signed detection. Those ratios include changing the receiver. The same-detector comparison isolates the archive format and its readback. All cases and orders decode the whole member once as part of first-use verification. The subsequent EOF choice and native packet write are included when applicable. The measured scope ends at verified signed detections for two resident physical members on the same CPU.

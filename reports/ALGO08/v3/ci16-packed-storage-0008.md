# Measured-width CI16 transfer on dense DS30-0008

On the independent staged DS30-0008 first member, the unchanged packing codec saved **90.94 ms wall and 90.93 ms CPU** from capture through first mixed analysis. All three paired orders saved wall time, ranging from **26.24 to 97.67 ms**. Packed storage was **999,394 bytes smaller** than ordinary level-1 Zstandard, a **1.29%** reduction. This is separate from the weak DS30-0016 transfer, which saved 103.37 ms and 1,931,566 bytes. [Dense machine receipt](measurements/ci16-packed-storage-0008.json.gz) · [DS30-0016 report](ci16-packed-storage.md)

| Capture layout | Durable capture, wall / CPU | First mixed use, wall / CPU | Joint clock, wall / CPU | Stored bytes |
|---|---:|---:|---:|---:|
| Ordinary Zstandard level 1 | 151.00 / 148.92 ms | 287.67 / 287.63 ms | 440.21 / 437.09 ms | 77,618,763 |
| Aperture-split Zstandard level 1 | 179.61 / 179.56 ms | 262.78 / 262.71 ms | 442.20 / 442.02 ms | 77,639,261 |
| Aperture-split measured-width CI16 | 120.00 / 119.95 ms | 223.32 / 223.25 ms | 344.14 / 344.02 ms | 76,619,369 |

The table gives independent medians by scope. Paired savings use matching orders. Measured-width packing saved 98.06 ms on the paired joint clock against the same aperture layout with Zstandard. One packed capture spent 112.02 CPU ms in encoding and block hashing, compared with 49.32 and 49.70 ms in the other orders. The report retains that slower order and its 26.24 ms end-to-end saving against the ordinary writer.

All 64 visits passed the original quality gate. Each of the nine analyses ran eight full and 56 short-primary stereo visits and returned 67 factors. All matched the independently sealed DS30-0008 mixed probe digest and the fresh ordered timeline and index evidence. The first packed read authenticated all 128 encoded blocks including unused tails and decoded 66.56 MB. Independent readback recovered the complete 102.4 MB signed CI16 digest for each layout. [Earlier independent receiver and custody reference](seekable-member.md)

The signed words on this member ranged from −1911 to 1883. The encoder measured 120 blocks at 12 signed bits and eight at 11, all with zero common shift. The binary SHA-256 matched the DS30-0016 prototype. Its full-width raw fallback depends on the observed width and applies to blocks at arbitrary gain. The physical fixtures here used 11- and 12-bit encodings, and synthetic tests exercised the full signed CI16 range and left-aligned words. [Codec tests](../../../tests/pipeline_eval/test_ci16_packing.py)

The copy was already resident at 18,952 of 18,952 pages. The one-core CPU 2 trial under the low-priority Gauss lock recorded zero input blocks for every capture and first-use clock. The reader still consumed every encoded byte. At equal serial read and write rates of 200 MB/s, moving 999,394 fewer bytes on each leg would contribute about 10.0 ms to the 90.94 ms measured local saving. Cold device and complete-reader throughput remain unmeasured for this codec.

Legacy conversion of this same staged ordinary member cost 189.18 ms wall. Its actual first signed mixed analysis took 228.54 ms and full independent recovery another 95.53 ms. The conversion and full recovery would amortize at the fifth warm mixed analysis relative to the 287.67 ms ordinary analysis median on this member. Keeping the original adds a 76,622,953-byte sidecar. No archive or recording format changed. Twenty-six component and regression tests passed. [Frozen protocol](ci16-packed-storage-0008-protocol.md)

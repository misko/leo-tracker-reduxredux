# Grouped CI16 packing on resident native members

The grouped codec reproduced the exact v1 bytes for both signed members. Through the writer and verified first full readback, North saved **3.987 ms** wall (1.29%) and DS30-0008 took **2.599 ms longer** (1.15%). Grouping made the North encoder materially faster, but the new decoder cost more CPU. The combined codec does not advance to a complete publication trial. [Protocol](ci16-grouped-protocol.md) · [Receipts](measurements/ci16-grouped.json.gz)

## Ceiling before the prototype

| First signed 64-window member | Signed width counts, 8 ms prefix + 12 ms tail | Native census | Native pack | Native unpack |
| --- | --- | ---: | ---: | ---: |
| North | 104 × 13 bits, 24 × 14 bits | 7.298 ms | 34.924 ms | 41.560 ms |
| DS30-0008 | 7 × 11 bits, 121 × 12 bits | 6.779 ms | 4.876 ms | 5.657 ms |

These are process CPU medians across three passes of the existing private SSSE3 codec. Every block had zero common low-bit shift. At North's observed widths, making encode and decode free would save at most 76.484 ms on this member. An extrapolation to the complete 1,200 visits is about 1.43 s, conditional on the same width mix and cost. The already measured 13.580 s direct North publication needs 1.374 s to reach 1.6×, so that optimistic ceiling leaves almost no room for actual kernel cost. DS30-0008 had about 4.124 ms in generic width-11 encode and decode. Its 121 width-12 blocks already use the SSSE3 implementation. Width census is unchanged in the experiment. [Complete North writer and first publication](north-direct-multichunk.md)

## Measured transfer

| Scope | North original → grouped | DS30-0008 original → grouped |
| --- | ---: | ---: |
| Native pack CPU | 34.838 → 11.118 ms | 5.017 → 3.733 ms |
| Native unpack CPU | 42.057 → 75.284 ms | 5.646 → 7.905 ms |
| Actual durable writer wall | 137.338 → 111.871 ms | 103.615 → 102.196 ms |
| Actual verified readback wall | 172.164 → 193.645 ms | 123.074 → 127.090 ms |
| Actual writer through readback wall | 309.501 → 305.513 ms | 226.687 → 229.285 ms |
| Actual writer through readback CPU | 309.436 → 305.502 ms | 226.682 → 229.261 ms |

Native CPU medians use two executions per codec in opposite orders within each case. The one writer/readback pair starts with the original codec on North and with the grouped codec on DS30-0008. Every paid reader authenticated 128 encoded blocks, decoded and authenticated all 64 windows (102,400,000 bytes) and checked the complete original member SHA-256. The two codec builds produced identical seek and logical index hashes and output sizes at each site. The independent fresh capture roots identify their executable codec hashes. All timed capture and readback boundaries recorded zero major faults and zero input blocks.

The isolated writer saved 25.468 ms on North. A writer-only deployment would need a separate combined test with the original reader before claiming an end-to-end improvement. At the same cost per visit, its writer-only contribution would be about 0.48 s across 1,200 visits. The measured complete first-use gain is much smaller and the physical result changes sign. This trial used the fixed 200,000-sample window representation and did not test physically invalid or incomplete extents.

The portable specialization packs eight signed values per group with exact-width shifts, two bounded partial word copies and the original checked scalar tail. The decoder groups the same fields and restores the full signed scale. It emits scalar sign restoration and scale multiplies in the GCC build for widths such as 13 and 14. The synthetic all-width profile also shows large decode regressions at 5–7, 9–11 and 13–15. The current 12-bit SSSE3 path, 16-bit raw copy, historical codec source and original pins remain intact. The alternative build added 9,303 text bytes on Gauss. It is only available from the experiment. [Implementation](ci16_grouped.c)

## Validation

Sixty-seven focused tests passed across scalar and SSSE3 builds, including an independent little-endian bit reservoir, all signed widths and legal shifts, odd remainder sizes and unaligned encoded buffers. An ARM64 GCC build ran 139,264 width/shift/length/alignment cases under QEMU, matching the original native encoder byte for byte and recovering all signed words. QEMU was used for function checks. Gauss was the only timed hardware and used the shared low-priority single-core slot. The first attempted experiment checkout populated unrelated binary fixtures before its disk quota stopped it. Only that generated checkout was reduced to sparse source before measuring. [Component tests](../../../tests/pipeline_eval/test_ci16_grouped.py)

Run `python -Bm reports.ALGO08.v3.ci16_grouped_trial /dev/shm/<fresh-root>` for the ceiling and pass `--compare` with a different fresh root for the one-member pairs. Use the same installed Python, pinned resident inputs and Gauss CPU 2 lease as the earlier direct North experiment. Commit `626dfdd54` contains the measured source and paired protocol. The receipt includes exact commands and library digests, synthetic per-width observations, raw block commitments and all disjoint measurements.

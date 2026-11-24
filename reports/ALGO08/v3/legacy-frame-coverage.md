# Selective decoding on the original DS30-0016 files

Only **5 of the 13 original files** consist entirely of Huffman-coded literals. Those files account for **320 of 808 visits** and **393.1 of 991.7 MB** of compressed input. A decoder that falls back on the first Zstandard match can use the shortcut on 39.6% of this recording's compressed bytes. The previously studied first file qualified. Timing it alone would overstate coverage. [Complete per-file census](measurements/legacy-frame-coverage-0016.json) · [Frozen selection](legacy-frame-coverage-protocol.md)

| Original file layout | Files | Visits | Compressed bytes | Decoded bytes | Compressed blocks | Blocks containing matches |
|---|---:|---:|---:|---:|---:|---:|
| Literals only | 5 | 320 | 393,072,334 | 512,000,000 | 3,910 | 0 |
| Literals and occasional matches | 8 | 488 | 598,662,263 | 780,800,000 | 5,964 | 13 |

All 9,874 blocks use four-stream Huffman literals. The 13 exceptional blocks regenerate just 81 bytes through match instructions. Even saving the entire decoded exceptional blocks would add at most **1,703,936 bytes**, or 0.172% of the original compressed recording, before seek metadata. Four exceptional blocks introduce a new Huffman table. Only one such table is used by a later literal-only block. It has one consumer, in the recording's last member. A decoder that skips an exceptional block must establish the correct table before reading a dependent block. The frequency of exceptions and the cost of handling them can vary with the signal and encoder.

This census authenticated both original manifests and every complete encoded payload in the existing memory-backed copy. It checked residency and read only that copy. The parser classified frame headers against the declared decoded extent. It did not decode I/Q or calculate positions. The ordinary decoder's whole-frame checksum and decoded-sample checks are still required when certifying a seek map. [Census and reproduction command](legacy_frame_coverage.py)

### What the small receiver tests measured

On the first DS30-0016 file, the ordinary reader and detector took 393.4 and 371.8 ms in two opposite orders. Selective reads of the original compressed file reduced those times to 329.8 and 288.5 ms, saving **16.2% and 22.4%**. Both readers authenticated every encoded byte and produced all 116 ordered detector outputs. Original verification followed by writing the 34,319-byte index took 251.0 ms, including 10.2 ms to build and sync the index after verification. Both readers rejected a changed byte in an unused suffix. [Same-member timings, integrity and first use](legacy-block-seek.md)

The two runs saved an average of 73.4 ms per subsequent analysis. At that rate the 251.0 ms standalone preparation would pay for itself on the **fourth replay** of this member. Generating the index alongside a full verification that was already required would change that accounting. Neither figure measures a first capture-through-position run.

The first dense DS30-0008 file contained a four-byte match in one block. Its scheduled short visit ended before reaching the block. Saving that block's verified decoded bytes also allowed a subsequent request for the full visit. All 64 scheduled spans and all 64 full spans matched the ordinary reader. The sidecar occupied 165,269 bytes, including its 131,072-byte exception. The two ready comparisons timed sample acquisition and verification only. They saved 24 ms and 69 ms CPU, with considerable variation in how long it took to attach and authenticate the original input. [Dense rare-match proof](legacy-block-exception.md)

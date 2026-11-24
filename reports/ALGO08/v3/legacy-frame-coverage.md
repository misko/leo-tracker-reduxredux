# Selective decoding on the original DS30-0016 files

Only **5 of the 13 original files** consist entirely of Huffman-coded literals. Those files account for **320 of 808 visits** and **393.1 of 991.7 MB** of compressed input. A decoder that falls back on the first Zstandard match can use the shortcut on 39.6% of this recording's compressed bytes. The previously studied first file qualified. Timing it alone would overstate coverage. [Complete per-file census](measurements/legacy-frame-coverage-0016.json) · [Frozen selection](legacy-frame-coverage-protocol.md)

| Original file layout | Files | Visits | Compressed bytes | Decoded bytes | Compressed blocks | Blocks containing matches |
|---|---:|---:|---:|---:|---:|---:|
| Literals only | 5 | 320 | 393,072,334 | 512,000,000 | 3,910 | 0 |
| Literals and occasional matches | 8 | 488 | 598,662,263 | 780,800,000 | 5,964 | 13 |

All 9,874 blocks use four-stream Huffman literals. The 13 exceptional blocks regenerate just 81 bytes through match instructions. Even saving the entire decoded exceptional blocks would add at most **1,703,936 bytes**, or 0.172% of the original compressed recording, before seek metadata. Four exceptional blocks introduce a new Huffman table. Only one such table is used by a later literal-only block. It has one consumer, in the recording's last member. A decoder that skips an exceptional block must establish the correct table before reading a dependent block. The frequency of exceptions and the cost of handling them can vary with the signal and encoder.

This census authenticated both original manifests and every complete encoded payload in the existing memory-backed copy. It checked residency and read only that copy. The parser classified frame headers against the declared decoded extent. It did not decode I/Q or calculate positions. The ordinary decoder's whole-frame checksum and decoded-sample checks are still required when certifying a seek map. [Census and reproduction command](legacy_frame_coverage.py)

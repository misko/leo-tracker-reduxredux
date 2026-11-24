# Selective decode on unmodified DS30-0016 legacy IQ

The existing single-frame Zstandard file supports selective readback without
changing its bytes, original manifest, index, or recording identity. On
resident DS30-0016 member 0, a prebuilt 34,319-byte detached map reduced
whole verified 20/8 ms acquisition by **16.2% and 22.4%** in opposite orders.
This is one physical member. It establishes a ready path after independent
stock verification. A new map requires that full verification first.

| Final measured boundary | Stock wall / CPU, ms | Selective wall / CPU, ms |
| --- | ---: | ---: |
| Ready detector, stock first | 393.401 / 393.393 | 329.845 / 329.821 |
| Ready detector, selective first | 371.783 / 371.699 | 288.489 / 288.473 |
| One-time stock decoded authority | 240.813 / 239.601 | |
| Additional native map and 64 prefix pins through file sync | | 10.152 / 10.152 |
| Contiguous independent verification through map sync | | 250.973 / 249.760 |

Both paths authenticate the same 78,554,951 encoded bytes with the release's
bounded resident ingress. They check the original index and manifest, execute
the same signed detector and emit the same 116 ordered native lane tuples.
The strict arm also reads the detached map from tmpfs, checks its external
SHA-256 pin, and validates the map against the complete original frame headers.
The timed final arms make no extra in-memory comparison to the reference
CI16; the untimed parity pass compared every requested span byte for byte.
A preliminary same-member pair using the in-memory map had 271.579→207.273 ms
and 270.455→202.819 ms wall. Its encoded authentication took 32.8–33.6 ms
CPU versus 116.1–159.9 ms in the final run. The ready saving retained its sign
in all four pairs. The final table includes the actual file-backed map reads
and is the primary measurement. All original accesses stayed on the admitted
resident stage. The final one-time verification clock includes setup and
metadata and counted eight input blocks. The ready clocks counted zero.

## Why this original frame can be read selectively

The released reader first authenticated and decoded all 64 windows, checked
the Zstandard frame checksum, verified each window digest and verified the
102.4 MB whole decoded digest. The detached map is sealed after that complete
pass from the same authenticated compressed buffer. It binds the manifest,
member and index SHA-256 values, the compressed and decoded extents of every
block, each block's most recent new Huffman table, and the original 64 decoded
8 ms prefix SHA-256 values.

This original member has 782 compressed Huffman blocks, 304 new tables, and
zero match sequences. With no LZ matches, a treeless block requires the table
from its last table-defining block and no previous decoded sample history. The
prototype uses the system libzstd block API and retains a single decoded
128 KiB block between requests. When a needed reused table is inactive, the
reader decodes that table's defining block then the requested block. Raw,
RLE, dictionary, nonzero-sequence, malformed and alternative frame layouts
cannot qualify. A missing map or unsupported layout uses the ordinary full
reader. Independently pinned map and original integrity failures refuse
output.

| Count on both measured ready passes | Selective |
| --- | ---: |
| Full authenticated compressed file | 78,554,951 bytes |
| Requested / Huffman dependency blocks decoded | 391 / 10 |
| Encoded bytes fed to libzstd, including dependencies | 40,197,122 bytes |
| Whole decoded blocks, including dependencies | 52,559,872 bytes |
| Exact decoded samples admitted and checked | 44,800,000 bytes |
| Blocks never handed to libzstd | 381 |
| Native block buffer and decoder context | 227,080 bytes |
| Detached data per proved member | 34,319 bytes |

Both modes admitted eight full two-scan anchors and fifty short visits,
preserved six original exclusions, and emitted 43 positive lanes and four
residual candidates. The exact post-capture experiment changes the storage
read path only. The ordinary installed detector retains its original scientific
behavior. Replaying the ready path still reads and hashes all original encoded
bytes. The omitted decoded suffix checks are covered by the independently
established full verification of those exact encoded bytes and pins.

At byte 10,487,819 in encoded block 103, within the unrequested suffix of short
visit 8, a flipped bit in a privately owned ingress buffer was rejected by the
installed original compressed authentication on both routes before any visit
was issued. A changed map was independently rejected under its original pin.
No waveform was written or mutated on disk. Four focused component tests
passed, covering isolated Huffman predecessor replay, nonzero-match fallback,
detached map and compressed data corruption, and provisional fallback rules.

## Reproduce

Use the installed release interpreter with its storage module first on
`PYTHONPATH`. Run on CPU 2 with one numerical thread, nice 15, I/O priority
7 and the shared Gauss lock using
`python -Bm reports.ALGO08.v3.legacy_block_seek NEW_TMPFS_ROOT`.
The runner compiles the small libzstd adapter outside the acquisition clocks.
It opens no waveform outside DS30-0016 member 0. The initial receipt used an
in-memory map and injected suffix corruption after the installed file-read
method; the final receipt charges the external file-backed map and delivers
the fault to the reader below its real compressed hash check.

- [Frozen protocol](legacy-block-seek-protocol.md)
- [Final receipt](measurements/legacy-block-seek-0016.json), SHA-256
  `0b390a0b5815f06151d6b1ee641608764f059b2875756a71a2460af78d9ee5d6`
- [Preliminary receipt](measurements/legacy-block-seek-0016-initial.json),
  SHA-256 `36e97ea26101f776f47a209a8e22cd8e7f8a820a2297b39bab05b6ece404cebe`

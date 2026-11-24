# First verified acquisition and legacy map in one traversal

On original DS30-0016 member 3, one continuous full-history libzstd decode
both fed the ordinary signed 20/8 ms detector and wrote the detached map.
The map was byte-identical to the prior two-pass map, and its existing
selective reader reproduced the detector's exact requested sample digests
and ordered native lanes. The fused route measured close to ordinary first
acquisition while adding reusable map creation.

| Actual matched order | Ordinary first acquisition wall / CPU, ms | Fused first acquisition plus map wall / CPU, ms |
| --- | ---: | ---: |
| Ordinary then fused | 279.701 / 279.675 | 268.148 / 268.131 |
| Fused then ordinary | 266.320 / 266.310 | 265.596 / 265.587 |

The two wall differences were 11.553 and 0.724 ms. CPU outside the detector
improved by 10.255 ms in the first order and increased by 1.002 ms in the
reverse order. These clocks support removal of the second full decode for
map creation. They do not establish a reproducible first-acquisition
speedup. The prior independent verification performed a stock verification
in 208.088 ms, then 235.881 ms for its independent full-history decode and
map certification. Those earlier stage clocks belong to a separate
experiment with no detector and are not a matched baseline for the table.

## Original commitments and custody

The fused route authenticated all 78,317,175 original encoded bytes and
the original manifest and index. It decoded the whole 102,400,000-byte
member into logical visits while retaining libzstd history in a bounded
ring. It validated each original per-visit SHA-256, the complete decoded
member digest and the Zstandard checksum and end-of-file. At the same
time it recorded native block starts and decoded lengths, the 64 prefix
hashes, and only the exact decoded material for exception blocks 120,
135 and 676. It did not infer decoded block lengths from the nominal
maximum. The same paired SHA-256 implementation was used in both arms
for the original per-window and complete decoded hashes.

The detector received all 64 ordered rows under the original member-local
schedule. Seven original exclusions left eight two-scan full visits and
49 short visits on both antennas. The 44,160,000 bytes requested by
the detector, 114 ordered native lane tuples, 38 positive lanes and three
residual candidates matched ordinary acquisition and the map reader.
The timing includes common signed sample evidence checks. The schedule was
initialized within this member, with no previous waveform members read.

Both orders wrote the existing 427,753-byte map including 393,216 exact
exception bytes. Its independent SHA-256 was
`9c998a1c40c848ab8c28a82f497190e6ce105eb1ae366e64cce5deed59c88d9d`,
the pin from the separate history proof. The map serialized and synced in
0.839–0.888 ms CPU. Continuous native reads took 68.150–68.798 ms CPU,
decoded and prefix SHA took 32.740–33.031 ms, and original encoded
authentication took 32.035–32.644 ms. No complete decoded waveform was
written to disk or retained as a single allocation.

Measured data buffers include 882,648 bytes for libzstd history and context,
31,280 bytes for block workspace, and 393,216 bytes for retained exceptions.
The largest logical window is 1,600,000 bytes. Allowing two logical windows
in flight bounds these measured data buffers to 4.51 MB beyond the
authenticated encoded snapshot. This is a data-buffer bound, not process RSS.

## Failure checks and reproduction

Map publication follows complete native EOF and successful detector return.
The reader leaves unsupported map layouts on the ordinary verified path.
The resident original corruption test flipped a compressed tail byte in a
private ingress buffer. Released compressed authentication rejected the
member before the detector callback or map publication. Component tests
also cover cross-ring history, byte-identical independent map production,
late frame checksum and decoded digest failures, incomplete iterator
consumption, a detector error after full verification, and ordinary fallback.
All six component tests passed.

Run the installed release interpreter with its storage code first on
`PYTHONPATH` using
`python -Bm reports.ALGO08.v3.legacy_fused_map_trial NEW_TMPFS_ROOT`
under the shared Gauss lock, CPU 2, nice 15 and best-effort I/O priority 7.
No original storage outside the resident member, RF or complete recording
was run.

- [Protocol](legacy-fused-map-protocol.md)
- [Final receipt](measurements/legacy-fused-map-0016.json), SHA-256
  `ec07fce76da0ff251aac661028681e07df179de523ba8c8b7254155057b80e46`
